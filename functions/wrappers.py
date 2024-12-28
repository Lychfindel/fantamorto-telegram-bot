from functools import wraps

from sqlalchemy import and_
from sqlalchemy.orm import Session

from telegram import Update
from telegram.ext import ContextTypes

from database.models.db import SessionLocal
from database.models import Game, Status, User


# Wrappers
def get_session(func):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        with SessionLocal() as session:
            with session.begin():
                try:
                    await func(session, *args, **kwargs)
                    session.commit()
                except:
                    session.rollback()
    return wrapped

def get_chat_game(func):
    @wraps(func)
    async def wrapped(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        game = session.query(Game).where(
            and_(Game.chat_id == update.effective_chat.id,
                Game.status != Status.END)
            ).one_or_none()
        await func(session, update, context, game, *args, **kwargs)
    return wrapped

def active_game(func):
    @wraps(func)
    async def wrapped(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
        if not game:
            await update.message.reply_html("There is no game of Fantamorto in progress in this group. Start a new game by using the <code>/start</code> command.")
            return
        await func(session, update, context, game, *args, **kwargs)
    return wrapped

def team_owner(func):
    @wraps(func)
    async def wrapped(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
        user = User.get_or_create_user(update.effective_user, session)
        team = game.get_team_from_owner(user, session)
        if not team:
            await update.message.reply_text("You don't have a team in this game :(")
            return
        await func(session, update, context, game, team, *args, **kwargs)
    return wrapped

def game_creator(func):
    @wraps(func)
    async def wrapped(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
        is_game_creator = game.is_creator(update.effective_user)
        if not is_game_creator:
            await update.message.reply_text("You are not the creator of this Fantamorto game")
            return
        await func(session, update, context, game, *args, **kwargs)
    return wrapped

def superuser(func):
    @wraps(func)
    async def wrapped(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = session.query(User).filter_by(telegram_id = update.effective_user.id).one_or_none()
        if user and user.superuser:
            await update.message.reply_text('You are a superuser!')
            await func(session, update, context, *args, **kwargs)

    return wrapped
