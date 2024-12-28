import logging
from logging.handlers import RotatingFileHandler
import os
import random
import requests
from dotenv import load_dotenv
import pdb
import re
import time
import os
from datetime import timedelta, date
from functools import wraps
from typing import TypedDict
from html import escape


from dotenv import load_dotenv

from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, Application ,ContextTypes, filters, PicklePersistence, CommandHandler
from telegram.helpers import escape_markdown
from telegram.constants import ParseMode

from database.models import Game, Team, Athlet, Bonus, Status
from database.models.db import SessionLocal
from database.models.wikidata import find_dead_athlets

from functions.utils import setupLogger
from functions.emoji import Emoji

from functions.commands import on_start, on_stop, on_help, on_join
from functions.commands import on_draft, on_draft_order, on_cancel_draft
from functions.commands import on_info, on_add, on_captain, on_ranking, on_team, on_allTeams, on_rename, on_export, on_kill 
from functions.commands import on_sendmessage

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
BAN_LIST_FILE = "ban_list.yaml"

# Constants
DEFAULT_FANTAMORTO_TEAM_SIZE = 10

# Logging
LOG_FOLDER = "logs"
LOG_FILENAME = "fantamorto_bot.log"
LOG_LEVEL = logging.DEBUG

# Persistency
PERSISTENCE_FILE = "fantamorto-persistence.ptb"

SUPERUSER_IDS = ["81855912"]

logger = setupLogger(LOG_FOLDER, LOG_FILENAME, LOG_LEVEL)


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

async def update_deads(context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
    logger.info(f"Updating deads")
    with SessionLocal() as session:
        with session.begin():
            try:
                alive_athlets = session.query(Athlet).where(Athlet.date_of_death == None).all()
                alive_athlets_ids = [
                    athlet.wiki_id for athlet in alive_athlets
                ]
                dead_athlets = find_dead_athlets(session, ids=list(alive_athlets_ids))
                all_games = []
                for athlet in dead_athlets:
                    for team in athlet.teams:
                        game = team.game
                        msg = "+++ MORTO +++\n"
                        msg += f"{athlet.name_escaped_html} ormai è solo un cadavere!\n"
                        msg += f"Gli unici a rallegrarsi sono i tifosi di {team.name_escaped_html} per i quali la morte porta {athlet.score} punti\n"
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
                session.commit()
            except:
                session.rollback()

async def post_init(application: Application) -> None:
    await application.updater.bot.set_my_commands([])
    await application.updater.bot.set_my_commands(commands=Commands.USER)

def main() -> None:
    print(f"{TOKEN}")

    # Get the application to register handlers
    application = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    job_queue = application.job_queue

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", on_start, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("stop", on_stop, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("help", on_help, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("join", on_join, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("draft", on_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["draftorder", "draft_order", "order"], on_draft_order, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["canceldraft", "cancel_draft"], on_cancel_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    # application.add_handler(CommandHandler(["pausedraft", "pause_draft"], on_pause_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("info", on_info, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("add", on_add, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("captain", on_captain, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["ranking", "table"], on_ranking, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("team", on_team, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler(["allteams", "all_teams"], on_allTeams, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("rename", on_rename, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("export", on_export, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("kill", on_kill, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("send", on_sendmessage, filters=~filters.UpdateType.EDITED_MESSAGE))

    # Job queue
    if job_queue:
        job_queue.run_repeating(update_deads, interval=timedelta(hours=1))

    # Start the Bot
    application.run_polling()



if __name__ == '__main__':
    main()
