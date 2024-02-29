import logging
from logging.handlers import RotatingFileHandler
import os
import random
import requests
from dotenv import load_dotenv
import pdb
import yaml
import re
import time
import os
from datetime import timedelta
from functools import wraps
from typing import TypedDict
from html import escape
import csv

from dotenv import load_dotenv

from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, Application ,ContextTypes, filters, PicklePersistence, CommandHandler
from telegram.helpers import escape_markdown
from telegram.constants import ParseMode

from fantamorto.wikidata import get_athlet, find_dead_athlets
from fantamorto.game import Game, Status
from fantamorto.team import Team
from fantamorto.athlet import Athlet
from fantamorto.bonus import Bonus

from functions.utils import setupLogger
from functions.emoji import Emoji

"""
How should work:
1. You have to add the bot to a chat
2. Someone must start the league. Who starts the league is the admin of the competition
3. People can join the bot until the admin starts the draft
4. During the draft each player can add persons to his team
5. The draft ends when all teams are completed
6. All players must select a captain
7. When all captains are set the game automatically starts
"""

load_dotenv()

# Global variables
TOKEN = os.getenv("TOKEN", "")
SUPERUSER = os.getenv("SUPERUSER", "")
CHAT_DATA_KEY = "game"
ATHLETS_POOL_KEY = "athlets"
CHAT_ARCHIVE_KEY = "archive"
BAN_LIST_FILE = "ban_list.yaml"

# Constants
DEFAULT_FANTAMORTO_TEAM_SIZE = 10

# Logging
LOG_FOLDER = "logs"
LOG_FILENAME = "fantamorto_bot.log"
LOG_LEVEL = logging.DEBUG

# Persistency
PERSISTENCE_FILE = "fantamorto-persistence.ptb"

logger = setupLogger(LOG_FOLDER, LOG_FILENAME, LOG_LEVEL)

# Make bot persistent
my_persistence = PicklePersistence(filepath=PERSISTENCE_FILE)

# Commands
class Commands:
    USER = [
        BotCommand("help", "welcome message"),
        BotCommand("start", "start a new fantamorto game in this chat"),
        BotCommand("stop", "end the current fantamorto game"),
        BotCommand("join", "join the game"),
        BotCommand("rename", "rename your team"),
        BotCommand("draft", "start the draft"),
        BotCommand("pausedraft", "pause the current draft"),
        BotCommand("canceldraft", "cancel the current draft"),
        BotCommand("draftorder", "get the next person during the draft"),
        BotCommand("info", "get info about an athlet"),
        BotCommand("captain", "add an athlet to your team"),
        BotCommand("add", "add an athlet to your team"),
        BotCommand("team", "get your team info"),
        BotCommand("ranking", "get the the current table of the game"),
        BotCommand("allteams", "get a list of the teams in the game"),
        BotCommand("export", "export a csv file with all the teams and athlets"),
        ]

# General functions
def get_or_add_athlet_to_bot(context: ContextTypes.DEFAULT_TYPE, athlet: Athlet) -> Athlet:
    if ATHLETS_POOL_KEY not in context.bot_data.keys():
        context.bot_data[ATHLETS_POOL_KEY] = {}
    athlets_pool: dict = context.bot_data[ATHLETS_POOL_KEY]
    if athlet.wiki_id not in athlets_pool.keys():
        athlets_pool[athlet.wiki_id] = athlet
    return athlets_pool[athlet.wiki_id]

# Wrappers
def get_chat_game(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        game = context.chat_data.get(CHAT_DATA_KEY, None)
        await func(update, context, game, *args, **kwargs)
    return wrapped

def active_game(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
        if not game:
            await update.message.reply_html("There is no game of Fantamorto in progress in this group. Start a new game by using the <code>/start</code> command.")
            return
        await func(update, context, game, *args, **kwargs)
    return wrapped

def team_owner(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
        team = game.get_team_from_owner(update.effective_user)
        if not team:
            await update.message.reply_text("You don't have a team in this game :(")
            return
        await func(update, context, game, team, *args, **kwargs)
    return wrapped

def game_creator(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
        is_game_creator = game.check_creator(update.effective_user)
        if not is_game_creator:
            await update.message.reply_text("You are not the creator of this Fantamorto game")
            return
        await func(update, context, game, *args, **kwargs)
    return wrapped

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

@get_chat_game
async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Start the fantamorto game in the chat"""
    if game:
        await update.message.reply_text(
            "A game of Fantamorto is already in progress in this group.")
        return
    
    chat_id = update.effective_chat
    creator = update.effective_user
    logger.info(f"New game - Chat {chat_id}")
    # with open(BAN_LIST_FILE, 'r') as f:
        # ban_list = yaml.load(f, Loader=yaml.FullLoader)
    game = Game(
        chat_id=update.effective_chat.id,
        creator=creator,
        team_size=DEFAULT_FANTAMORTO_TEAM_SIZE
        )
    context.chat_data[CHAT_DATA_KEY] = game # type: ignore
    await update.message.reply_text(
        "Welcome to Fantamorto!\n"
        +f"Each player can add up to {game.team_size} real, alive people with a page on wikidata.org.\n"
        +"To join the game send the command /join")
    return

@get_chat_game
@active_game
@game_creator
async def on_stop(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Start the fantamorto game in the chat"""    
    chat_id = update.effective_chat
    logger.info(f"End game - Chat {chat_id}")
    # with open(BAN_LIST_FILE, 'r') as f:
        # ban_list = yaml.load(f, Loader=yaml.FullLoader)

    if game.creator_id != update.effective_user.id:
        await update.message.reply_html(
        f"You are not the creator of this game. Only {game.creator_name} can stop the game.")
        return
    
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
    if CHAT_ARCHIVE_KEY in context.chat_data:
        context.chat_data[CHAT_ARCHIVE_KEY].append(game)
    else:
        context.chat_data[CHAT_ARCHIVE_KEY] = [game]

    del context.chat_data[CHAT_DATA_KEY] # type: ignore
    await update.message.reply_html(end_msg)

@get_chat_game
@active_game
async def on_join(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    """Join the fantamorto game in the chat"""
    if game.status != Status.START:
        await update.message.reply_text("You can join the game only before the draft")
        return
    
    # Team name
    if context.args:
        team_name = ' '.join(context.args)
    elif update.effective_user.username:
        team_name = f"Team {update.effective_user.username}"
    else:
        team_name = f"Team {update.effective_user.first_name}"
    
    team = Team(
        chat_id=update.effective_chat.id,
        name=team_name,
        owner=update.effective_user
    )
    try:
        game.add_team(team)
    except ValueError as e:
        await update.message.reply_html(str(e))
        return
    logger.debug(f"Join - Chat: {update.effective_chat} > User: {update.effective_user} > Name: {team_name}")
    
    await update.message.reply_html(f"{team.name_escaped_html} is now part of the game.\nWhen all the players have joined you can send the command <code>/draft</code> to start the draft")


@get_chat_game
@active_game
@game_creator
async def on_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
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
            f"The team {current_drafter} ({current_drafter.owner_mention}) must pick the next person\n"
            +f"You still have {game.team_size - current_drafter.num_athlets} athlets left!")

@get_chat_game
@active_game
@game_creator
async def on_pause_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    if game.status != Status.DRAFT:
        await update.message.reply_text("You can pause the draft only when you are drafting")
        return
    pass

    game.pause_draft()
    logger.debug(f"Draft pause - Chat: {update.effective_chat}")

    await update.message.reply_html("The draft is paused!\nNow new teams can join the game with /join.\nTo restart the draft send /draft")

@get_chat_game
@active_game
@game_creator
async def on_cancel_draft(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs) -> None:
    if game.status != Status.DRAFT:
        await update.message.reply_text("You can cancel the draft only when you are drafting")
        return
    pass

    game.cancel_draft()
    logger.debug(f"Draft cancel - Chat: {update.effective_chat}")

    await update.message.reply_html("The draft is cancelled!\nAll athlets have been dismissed!\nNow new teams can join the game with /join.\n To start a new draft send /draft")

@get_chat_game
@active_game
async def on_draft_order(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    """Get the draft order for Fantamorto game"""
    if game.status != Status.DRAFT:
        await update.message.reply_text("The game is not in the draft!")
        return
    
    current_drafter = game.get_current_drafter()
    msg = f"Current drafter is {current_drafter.name_escaped_html} ({escape(current_drafter.owner_name)})\n"
    msg += f"He still has {game.team_size - current_drafter.num_athlets} athlets left!\n"
    msg += f"The draft order is:\n"
    for idx, t in enumerate(game.draft_order):
        msg += f"{idx+1}. {t.name_escaped_html} ({escape(t.owner_name)})\n"
    await update.message.reply_html(msg)

async def on_info(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    if not context.args:
        await update.effective_message.reply_html("You have to specify a name or a Wikimedia ID adter the command <code>/add</code>. For example <code>/add Silvio Berlusconi</code> or <code>/add Q11860</code>")
        return
    athlet_name = ' '.join(context.args)
    try:
        athlets = get_athlet(athlet_name)
        if len(athlets) == 0:
            await update.effective_message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(athlets) > 1:
            msg = f"I found multiple persons for {escape(athlet_name)}. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\tPOINTS\n"
            for idx, p in enumerate(athlets):
                msg += f"{idx+1}: <a href=\"{p.url}\">{p.wiki_id}</a>\t{p.age}y\t{escape(', '.join(p.occupations))}\t{p.theoretical_score}pt\n"
            await update.effective_message.reply_html(msg)
            return
        else:
            athlet = athlets[0]

    except requests.ConnectionError:
        await update.effective_message.reply_text("There is a connection problem with wikidata. Try later!")
        return

    except ValueError as err:
        await update.effective_message.reply_html(f"There was an error: {escape(err)}")
        return
    
    await update.effective_message.reply_html(str(athlet.get_description()))

@get_chat_game
@active_game
@team_owner
async def on_add(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
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
            f"Sorry, it is not your turn.\nThe team {current_drafter} ({current_drafter.owner_mention}) must pick the next person\n"
            +f"He still has {game.team_size - current_drafter.num_athlets} persons left!")
        return
    
    athlet_name = ' '.join(context.args)

    try:
        athlets = get_athlet(athlet_name)
        if len(athlets) == 0:
            await update.effective_message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(athlets) > 1:
            msg = f"I found multiple athlets for {escape(athlet_name)}. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\tPOINTS\n"
            for idx, p in enumerate(athlets):
                msg += f"{idx+1}: <a href=\"{p.url}\">{p.wiki_id}</a>\t{p.age}y\t{escape(', '.join(p.occupations))}\t{p.theoretical_score}pt\n"
            await update.effective_message.reply_html(msg)
            return
        else:
            athlet = get_or_add_athlet_to_bot(context, athlets[0])
            game.add_athlet(team=team, athlet=athlet)
            await update.effective_message.reply_html(str(athlet.get_description()))

    except requests.ConnectionError:
        await update.effective_message.reply_text("There is a connection problem with wikidata. Try later!")
        return

    except ValueError as err:
        await update.effective_message.reply_text(f"There was an error: {err}")
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
                f"{next_drafter.owner_mention} it's your turn to draft!\n"
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

@get_chat_game
@active_game
@team_owner
async def on_captain(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
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
        return
    
    remaining_captains = [not t.has_captain() for t in game.teams]
    if sum(remaining_captains) == 0:
        game.start_game()
        await update.message.reply_text("All the teams are full! Let's start the game!")
        return
    else:
        await update.message.reply_text(f"There are still {sum(remaining_captains)} teams without captain")
        return


@get_chat_game
@active_game
async def on_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    msg = "RANKING\n"
    for idx, team in enumerate(game.ranking):
        msg += f"{idx+1}. {team.score} - {team.name_escaped_html}\n"
    await update.message.reply_html(msg)

@get_chat_game
@active_game
@team_owner
async def on_team(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
    msg = f"NAME: {team.name_escaped_html}\n"
    msg += f"OWNER: {team.owner_name}\n"
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
    gender_alive = [g for g in team.all_genders if g not in team.inclusivity]
    msg += f"({', '.join(gender_dead + gender_alive)})\n"
    msg += f"{Emoji.GLOBETROTTER} Globetrotter: {team.globetrotter_score} pt\n"
    citizienship_dead = [f"<b>{c}</b>" for c in team.globetrotter]
    citizienship_alive = [c for c in team.all_citizienships if c not in team.globetrotter]
    msg += f"({', '.join(citizienship_dead + citizienship_alive)})\n"
    msg += f"{Emoji.JACK_OF_ALL_TRADES} Jack of all Trades: {team.jack_of_all_trades_score} pt\n"
    occupation_dead = [f"<b>{o}</b>" for o in team.jack_of_all_trades]
    occupation_alive = [o for o in team.all_occupations if o not in team.jack_of_all_trades]
    msg += f"({', '.join(occupation_dead + occupation_alive)})\n"
    await update.message.reply_html(msg)

@get_chat_game
@active_game
async def on_allTeams(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    msg = f"There are {game.num_teams} teams in game:\n"
    for team in game.teams:
        msg += f"{team.name_escaped_html} ({team.owner_name})\n"
    
    await update.message.reply_html(msg)

@get_chat_game
@active_game
@team_owner
async def on_rename(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, team: Team, *args, **kwargs):
    if not context.args:
        await update.message.reply_text("You have to specify a new name for your team")
        return

    team_name = ' '.join(context.args)
    game.rename_team(team, team_name)

    await update.message.reply_html(f"The name of your team is now: {team.name_escaped_html}")

@get_chat_game
@active_game
async def on_export(update: Update, context: ContextTypes.DEFAULT_TYPE, game: Game, *args, **kwargs):
    csv_file = f'game_{game.chat_id}.csv'
    with open(csv_file, 'w') as f:
        csv_writer = csv.writer(f, delimiter=',')
        for team in game.teams:
            for athlet in team.athlets:
                csv_writer.writerow([team.owner_id, team.name, athlet.wiki_id, athlet.name])
    await context.bot.send_document(
        chat_id=game.chat_id,
        document=csv_file
        )
    os.remove(csv_file)
    

async def update_deads(context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    logger.info(f"Updating deads")
    athlets_dict: dict[str, Athlet] = context.application.bot_data[ATHLETS_POOL_KEY]
    alive_athlets_dict = {
        wiki_id: athlet for wiki_id, athlet in athlets_dict.items() if not athlet.is_dead
    }
    dead_athlets = find_dead_athlets(ids = list(alive_athlets_dict.keys()))
    all_games = []
    for athlet in dead_athlets:
        ath_in_dict = athlets_dict[athlet.wiki_id]
        ath_in_dict.date_of_death = athlet.date_of_death
        # ath_in_dict.date_of_death = athlet.date_of_death
        for game in ath_in_dict.games:
            game: Game
            teams = game.get_teams_with_athlet(ath_in_dict)
            teams_names = [t.name_escaped_html for t in teams]
            msg = "+++ MORTO +++\n"
            msg += f"{ath_in_dict.name_escaped_html} ormai è solo un cadavere!\n"
            msg += f"Gli unici a rallegrarsi sono i tifosi di {', '.join(teams_names)} per i quali la morte porta {ath_in_dict.score} punti\n"
            msg += "È MORTO! MORTO MORTO MORTO!"
    
            await context.bot.send_message(
                chat_id = game.chat_id,
                text= msg,
                parse_mode=ParseMode.HTML
            )
            all_games.append(game)
    
    for game in set(all_games):
        first_death_teams = game.update_first_death(dead_athlets)
        if first_death_teams:
            teams_names = [t.name_escaped_html for t in first_death_teams]
            msg = f"FIRST DEATH! {Emoji.FIRST_DEATH}\n"
            msg += f"I punti per il primo sangue versato vanno a {', '.join(teams_names)}"
            await context.bot.send_message(
                chat_id = game.chat_id,
                text= msg,
                parse_mode=ParseMode.HTML
            )
    logger.info("End update deads")

async def post_init(application: Application) -> None:
    await application.updater.bot.set_my_commands([])
    await application.updater.bot.set_my_commands(commands=Commands.USER)

def main() -> None:
    print(f"{TOKEN}")

    # Get the application to register handlers
    application = ApplicationBuilder().token(TOKEN).persistence(persistence=my_persistence).post_init(post_init).build()
    job_queue = application.job_queue

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", on_start, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("stop", on_stop, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("help", on_help, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("join", on_join, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("draft", on_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["draftorder", "draft_order", "order"], on_draft_order, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["canceldraft", "cancel_draft"], on_cancel_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["pausedraft", "pause_draft"], on_pause_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("info", on_info, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("add", on_add, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("captain", on_captain, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["ranking", "table"], on_ranking, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("team", on_team, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["allteams", "all_teams"], on_allTeams, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("rename", on_rename, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("export", on_export, filters=~filters.UpdateType.EDITED_MESSAGE))

    # Job queue
    if job_queue:
        job_queue.run_repeating(update_deads, interval=timedelta(hours=1))

    # Start the Bot
    application.run_polling()



if __name__ == '__main__':
    main()
