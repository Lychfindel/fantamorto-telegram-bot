import requests
from html import escape
from datetime import date
import csv

from telegram import Update
from telegram.ext import ContextTypes

from sqlalchemy.orm import Session

from database.models import User, Game, Team, Status, Athlet, Bonus
from database.models.wikidata import get_athlet

from .wrappers import get_session, get_chat_game, active_game, team_owner, game_creator, superuser

import logging
from logging.handlers import RotatingFileHandler
from .utils import setupLogger
from .constants import DEFAULT_FANTAMORTO_TEAM_SIZE
from .emoji import Emoji

# Logging
LOG_FOLDER = "logs"
LOG_FILENAME = "fantamorto_bot.log"
LOG_LEVEL = logging.DEBUG

logger = setupLogger(LOG_FOLDER, LOG_FILENAME, LOG_LEVEL)

# Functions
async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    # logging
    logger.debug(f'Help - Chat {update.effective_chat.id}')

    await update.message.reply_html(
        "This bot allows to play Fantamorto in a group!\n"
        + "The rules of the game are taken from https://www.reddit.com/r/Fantamorto/comments/ylseuy/fantamorto_edizione_2023_iscrizioni_aperte/\n"
        + "1. To start a new game type <code>/start</code>\n"
        + "2. Use the command <code>/join TEAM_NAME</code> to join the game with your team\n"
        + "3. Once all the teams have joined, use the command <code>/draft</code> to start selecting the persons of the teams\n"
        + "4. When it's your turn you can pick a player with <code>/add NAME or ID</code> where ID is the wikimedia ID that you can find at https://www.wikidata.org\n"
        + "For example you can pick Silvio Berlusconi both with <code>/add Silvio Berlusconi</code> or <code>/add Q11860</code>\n"
        + "5. Once all the teams are full the game will start automatically\n"
        + "6. To check the current ranking use <code>/ranking</code>\n"
        + "\nEnjoy! But do not try to help the Death do his work!"
    )
    
    return

@get_session
@get_chat_game
async def on_start(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Start the fantamorto game in the chat"""
    
    if game:
        await update.message.reply_text(
            "A game of Fantamorto is already in progress in this group.")
        return
    
    chat_id = update.effective_chat
    tg_user = update.effective_user
    logger.info(f"New game - Chat {chat_id}")
    # with open(BAN_LIST_FILE, 'r') as f:
        # ban_list = yaml.load(f, Loader=yaml.FullLoader)
    creator = User.get_or_create_user(tg_user, session)
    game = Game(
        chat_id=update.effective_chat.id,
        creator=creator,
        team_size=DEFAULT_FANTAMORTO_TEAM_SIZE
        )
    session.add(game)
    await update.message.reply_text(
        "Welcome to Fantamorto!\n"
        +f"Each player can add up to {game.team_size} real, alive people with a page on wikidata.org.\n"
        +"To join the game send the command /join")
    return

@get_session
@get_chat_game
@active_game
@game_creator
async def on_stop(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Stop the fantamorto game in the chat"""    
    end_msg = "The game has ended!\n"
    if game.ranking:
        end_msg += f"And the winner is......\n<b>{game.ranking[0]}</b>\n"
        
        end_msg += "Here the final ranking\n"
        for idx, team in enumerate(game.ranking):
            if idx == 0:
                end_msg += f"{Emoji.FIRST_PLACE}\t"
            elif idx == 1:
                end_msg += f"{Emoji.SECOND_PLACE}\t"
            elif idx == 2:
                end_msg += f"{Emoji.THIRD_PLACE}\t"
            else:
                end_msg += f"{idx+1}.\t"
            end_msg += f"{team.name_escaped_html}: {team.score}\n"

    end_msg += "\nTo start a new game send <code>/start</code>"
    
    game.status = Status.END

    await update.message.reply_html(end_msg)

@get_session
@get_chat_game
@active_game
async def on_join(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Join the fantamorto game in the chat"""
    if game.status != Status.START:
        await update.message.reply_text("You can join the game only before the draft")
        return
    
    tg_user = update.effective_user
    
    # Team name
    if context.args:
        team_name = ' '.join(context.args)
    elif tg_user.username:
        team_name = f"Team {tg_user.username}"
    else:
        team_name = f"Team {tg_user.first_name}"
    
    owner = User.get_or_create_user(tg_user, session)

    team = game.get_team_from_owner(owner, session)
    if team:
        await update.message.reply_html(f"There is already a team owned by {team.owner.mention}")
        return

    team = Team(
        name=team_name,
        owner=owner,
        game=game
    )
    session.add(team)

    logger.debug(f"Join - Chat: {update.effective_chat} > User: {update.effective_user} > Name: {team_name}")
    
    await update.message.reply_html(f"{team.name_escaped_html} is now part of the game.\nWhen all the players have joined you can send the command <code>/draft</code> to start the draft")

@get_session
@get_chat_game
@active_game
@game_creator
async def on_draft(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Start the draft"""
    if game.status != Status.START:
        await update.message.reply_text("You can start the draft only once after all teams joined the game")
        return
    
    if game.num_teams < 1:
        await update.message.reply_html("There should be at least one team to play! To join the the game send the command <code>/join</code>")
        return
    
    game.start_draft()
    logger.debug(f"Draft start - Chat: {update.effective_chat}")

    current_drafter = game.get_current_drafter()
    logger.debug(f"Draft - Chat: {update._effective_chat} Current drafter: {current_drafter}")

    await update.message.reply_html(
            f"The team {current_drafter} ({current_drafter.owner.mention}) must pick the next person\n"
            +f"You still have {game.team_size - current_drafter.num_athlets} athlets left!")

# @get_chat_game
# @active_game
# @game_creator
# async def on_pause_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
#     if game.status != Status.DRAFT:
#         await update.message.reply_text("You can pause the draft only when you are drafting")
#         return
#     pass

#     game.pause_draft()
#     logger.debug(f"Draft pause - Chat: {update.effective_chat}")

#     await update.message.reply_html("The draft is paused!\nNow new teams can join the game with /join.\nTo restart the draft send /draft")

@get_session
@get_chat_game
@active_game
@game_creator
async def on_cancel_draft(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    if game.status != Status.DRAFT:
        await update.message.reply_text("You can cancel the draft only when you are drafting")
        return
    pass

    game.cancel_draft()
    logger.debug(f"Draft cancel - Chat: {update.effective_chat}")

    await update.message.reply_html("The draft is cancelled!\nAll athlets have been dismissed!\nNow new teams can join the game with /join.\n To start a new draft send /draft")

@get_session
@get_chat_game
@active_game
async def on_draft_order(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):

    """Get the draft order for Fantamorto game"""
    if game.status != Status.DRAFT:
        await update.message.reply_text("The game is not in the draft!")
        return
    
    current_drafter = game.get_current_drafter()
    msg = f"Current drafter is {current_drafter.name_escaped_html} ({escape(current_drafter.owner.name)})\n"
    msg += f"He still has {game.team_size - current_drafter.num_athlets} athlets left!\n"
    msg += f"The draft order is:\n"
    for idx, t in enumerate(game.get_draft_order()):
        msg += f"{idx+1}. {t.name_escaped_html} ({escape(t.owner.name)})\n"
    await update.message.reply_html(msg)

@get_session
async def on_info(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    if not context.args:
        await update.effective_message.reply_html("You have to specify a name or a Wikimedia ID adter the command <code>/add</code>. For example <code>/add Silvio Berlusconi</code> or <code>/add Q11860</code>")
        return
    athlet_name = ' '.join(context.args)
    
    try:
        athlets = get_athlet(session, athlet_name)
        if len(athlets) == 0:
            await update.effective_message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(athlets) > 1:
            msg = f"I found multiple persons for {escape(athlet_name)}. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\tPOINTS\n"
            for idx, p in enumerate(athlets):
                msg += f"{idx+1}: <a href=\"{p.url}\">{p.wiki_id}</a>\t{p.age}y\t{escape(', '.join(x.name for x in p.occupations))}\t{p.theoretical_score}pt\n"
            await update.effective_message.reply_html(msg)
            session.rollback()
            return
        else:
            athlet = athlets[0]

    except requests.ConnectionError:
        await update.effective_message.reply_text("There is a connection problem with wikidata. Try later!")
        session.rollback()
        return

    except ValueError as err:
        await update.effective_message.reply_html(f"There was an error: {escape(err)}")
        session.rollback()
        return
    
    await update.effective_message.reply_html(str(athlet.get_description()))
    session.rollback()

@get_session
@get_chat_game
@active_game
@team_owner
async def on_add(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
    if game.status != Status.DRAFT:
        await update.message.reply_text("The game is not in the draft!")
        return
    if not context.args:
        await update.effective_message.reply_html("You have to specify a name or a Wikimedia ID adter the command <code>/add</code>. For example <code>/add Silvio Berlusconi</code> or <code>/add Q11860</code>")
        return

    if team.num_athlets >= game.team_size:
        await update.effective_message.reply_text(f"You already have {team.num_athlets} players")
        return
    
    current_drafter = game.get_current_drafter()
    if team != current_drafter:
        await update.effective_message.reply_html(
            f"Sorry, it is not your turn.\nThe team {current_drafter} ({current_drafter.owner.mention}) must pick the next person\n"
            +f"He still has {game.team_size - current_drafter.num_athlets} persons left!")
        return
    
    athlet_name = ' '.join(context.args)

    try:
        athlets = get_athlet(session, athlet_name, alive=False)
        if len(athlets) == 0:
            await update.effective_message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(athlets) > 1:
            msg = f"I found multiple athlets for {escape(athlet_name)}. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\tPOINTS\n"
            for idx, p in enumerate(athlets):
                msg += f"{idx+1}: <a href=\"{p.url}\">{p.wiki_id}</a>\t{p.age}y\t{escape(', '.join(x.name for x in p.occupations))}\t{p.theoretical_score}pt\n"
            await update.effective_message.reply_html(msg)
            session.rollback()
            return
        else:
            athlet = athlets[0]
            game.add_athlet(team=team, athlet=athlet, allow_deads=True)
            await update.effective_message.reply_html(str(athlet.get_description()))

    except requests.ConnectionError:
        await update.effective_message.reply_text("There is a connection problem with wikidata. Try later!")
        session.rollback()
        return

    except ValueError as err:
        await update.effective_message.reply_text(f"There was an error: {err}")
        session.rollback()
        return
    
    # Chekc if draft is over
    
    if any(t.num_athlets < game.team_size for t in game.teams):
        next_drafter_ok = False
        next_drafter = None
        while not next_drafter_ok:
            next_drafter = game.advance_draft()
            if next_drafter.num_athlets < game.team_size:
                next_drafter_ok = True
        
        await update.effective_message.reply_html(
                f"{next_drafter.owner.mention} it's your turn to draft!\n"
                +f"You still have {game.team_size - next_drafter.num_athlets} persons left!")
        return
    else:
        await update.effective_message.reply_text("All the teams are complete!")
        if all(t.has_captain() for t in game.teams):
            game.start_game()
            await update.effective_message.reply_text("All the teams have a captain! Let's start the game!")
            return
        else:
            game.start_captain()
            await update.effective_message.reply_html("Now select the captains with <code>/captain idx</code> where idx is the index of the player that you can get from <code>/team</code>")
            return

@get_session
@get_chat_game
@active_game
@team_owner
async def on_captain(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
    if not context.args:
        await update.effective_message.reply_html("You have to specify the index of the athlet. Like 0, 1, 2... You can find them with <code>/team</code>")
        return

    if game.status not in [Status.DRAFT, Status.CAPTAIN]:
        await update.effective_message.reply_text("You must be in the draft or immediately after to set the captain")
        return

    idx_athlet = ' '.join(context.args)
    try:
        idx_athlet = int(idx_athlet)
    except ValueError:
        await update.message.reply_html("You have to specify an index. Like 0, 1, 2... You can find them with <code>/team</code>")
        return
    if idx_athlet < 0:
        await update.message.reply_html("You have to specify a positive index. Like 0, 1, 2... You can find them with <code>/team</code>")
        return

    try:
        game.set_captain(team, idx_athlet)
    except ValueError as err:
        await update.message.reply_text(str(err))
        session.rollback()
        return
    if all(t.num_athlets >= game.team_size and t.has_captain() for t in game.teams):
        game.start_game()
        await update.message.reply_text("All the teams are complete! Let's start the game!")
        return
    else:
        remaining_captains = [not t.has_captain() for t in game.teams]
        await update.message.reply_text(f"There are still {sum(remaining_captains)} teams without captain")
        return

@get_session
@get_chat_game
@active_game
async def on_ranking(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    msg = "RANKING\n"
    for idx, team in enumerate(game.ranking):
        msg += f"{idx+1}. {team.score} - {team.name_escaped_html}\n"
    await update.message.reply_html(msg)

@get_session
@get_chat_game
@active_game
@team_owner
async def on_team(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
    msg = f"NAME: {team.name_escaped_html}\n"
    msg += f"OWNER: {team.owner.name}\n"
    msg += f"SCORE: {team.score if team.score else 0}\n"
    msg += f"**** ATHLETS ****\n"
    for idx, athlet in enumerate(team.athlets):
        athlet_msg = f"{idx}: "
        if athlet == team.captain:
            athlet_msg += f"{Emoji.CAPTAIN} "
        athlet_msg += f"{athlet.name} - {athlet.age}y "
        
        if not athlet.is_dead:
            athlet_msg += f"{Emoji.ALIVE} "
        else:
            athlet_msg += f"{Emoji.DEAD} "
            if athlet in game.first_deaths:
                athlet_msg += f"{Emoji.FIRST_DEATH} "
            if athlet.gonzales:
                athlet_msg += f"{Emoji.SPEEDY_GONZALES} "
            if athlet.cesarini:
                athlet_msg += f"{Emoji.ZONA_CESARINI} "
            if athlet.club27:
                athlet_msg += f"{Emoji.CLUB_27} "
            if athlet.birthday:
                athlet_msg += f"{Emoji.HAPPY_BIRTHDAY} "

        athlet_msg += f"({athlet.score} pt)"
        msg += f"{athlet_msg}\n"
    
    msg += f"**** BONUS *****\n"
    if team.has_first_death:
        msg += f"{Emoji.FIRST_DEATH} First death: {Bonus.FIRST_DEATH} pt\n"
        msg += f"({', '.join([a.name_escaped_html for a in team.athlets if a in game.first_deaths])})\n"
    msg += f"{Emoji.INCLUSIVITY} Inclusivity: {team.inclusivity_score} pt\n"
    gender_dead = [f"<b>{g}</b>" for g in team.inclusivity]
    gender_alive = [g.name for g in team.all_genders if g not in team.inclusivity]
    msg += f"({', '.join(gender_dead + gender_alive)})\n"
    msg += f"{Emoji.GLOBETROTTER} Globetrotter: {team.globetrotter_score} pt\n"
    citizenship_dead = [f"<b>{c}</b>" for c in team.globetrotter]
    citizenship_alive = [c.name for c in team.all_citizenships if c not in team.globetrotter]
    msg += f"({', '.join(citizenship_dead + citizenship_alive)})\n"
    msg += f"{Emoji.JACK_OF_ALL_TRADES} Jack of all Trades: {team.jack_of_all_trades_score} pt\n"
    occupation_dead = [f"<b>{o}</b>" for o in team.jack_of_all_trades]
    occupation_alive = [o.name for o in team.all_occupations if o not in team.jack_of_all_trades]
    msg += f"({', '.join(occupation_dead + occupation_alive)})\n"
    await update.message.reply_html(msg)

@get_session
@get_chat_game
@active_game
async def on_allTeams(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    msg = f"There are {game.num_teams} teams in game:\n"
    for team in game.teams:
        msg += f"{team.name_escaped_html} ({team.owner.name})\n"
    
    await update.message.reply_html(msg)

@get_session
@get_chat_game
@active_game
@team_owner
async def on_rename(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
    if not context.args:
        await update.message.reply_text("You have to specify a new name for your team")
        return

    team_name = ' '.join(context.args)
    game.rename_team(team, team_name)

    await update.message.reply_html(f"The name of your team is now: {team.name_escaped_html}")

@get_session
@get_chat_game
@active_game
async def on_export(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    csv_file = f'game_{game.chat_id}.csv'
    with open(csv_file, 'w') as f:
        csv_writer = csv.writer(f, delimiter=',')
        csv_writer.writerow(["Owner ID", "Team", "Athlet ID", "Athlet", "Captain"])
        for team in game.teams:
            for athlet in team.athlets:
                csv_writer.writerow([team.owner.telegram_id, team.name, athlet.wiki_id, athlet.name, team.captain == athlet])

    await context.bot.send_document(
        chat_id=game.chat_id,
        document=open(csv_file, 'rb')
        )
    os.remove(csv_file)

@get_session
@superuser
@get_chat_game
async def on_kill(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    if not context.args:
        await update.message.reply_text("You have to specify a athlet id")
        return
    athlet_id = context.args
    athlet = session.query(Athlet).filter_by(wiki_id=athlet_id[0]).one_or_none()
    if not athlet:
        await update.message.reply_text("Athlet is not present")
        return
    athlet.date_of_death = date.today()
    game.update_first_death([athlet])

@get_session
@superuser
async def on_sendmessage(session: Session, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    if not context.args:
        await update.message.reply_text("chatid seguita da messaggio")
        return
    chat = context.args[0]
    msg = ' '.join(context.args[1:])
    await context.bot.send_message(
        chat_id = chat,
        text = msg
    )