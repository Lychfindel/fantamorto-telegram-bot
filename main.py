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
from datetime import timedelta


from telegram import Update
from telegram.ext import ApplicationBuilder ,ContextTypes, filters, PicklePersistence, CommandHandler
from telegram.helpers import escape_markdown

from functions.wikidata import get_person, update_persons
from functions.fantamorto import Game, Team, GAME_STEPS


# Enable logging
LOG_FOLDER = "logs"
LOG_FILENAME = "fantamorto_bot.log"
LOG_LEVEL = logging.DEBUG

if not os.path.exists(LOG_FOLDER):
    os.mkdir(LOG_FOLDER)
logfile = os.path.join(LOG_FOLDER, LOG_FILENAME)

stream_handler = logging.StreamHandler()
file_handler = RotatingFileHandler(logfile, maxBytes=100000, backupCount=10)

formatter = logging.Formatter('[%(asctime)s] [%(name)s:%(filename)s:%(lineno)d] [%(levelname)s] %(message)s')

stream_handler.setFormatter(formatter)
stream_handler.setLevel(LOG_LEVEL)
file_handler.setFormatter(formatter)
file_handler.setLevel(LOG_LEVEL)

logger = logging.getLogger(__name__)
logger.handlers.clear()
logger.setLevel(LOG_LEVEL)
logger.addHandler(stream_handler)
logger.addHandler(file_handler)


# Make bot persistent
my_persistence = PicklePersistence(filepath='fantamorto-persistence_v20.ptb')

# Constants
DEFAULT_FANTAMORTO_TEAM_SIZE = 10

# Global variables
load_dotenv()
TOKEN = os.getenv("TOKEN", "")
SUPERUSER = os.getenv("SUPERUSER", "")
CHAT_DATA_KEY = "game"
BAN_LIST_FILE = "ban_list.yaml"

# Functions
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    # logging
    logger.debug(f'Chat {update.effective_chat.id} - Help') # type: ignore

    await update.message.reply_text(
        "This bot allows to play Fantamorto in a group!\n"
        + "The rules of the game are taken from https://www.reddit.com/r/Fantamorto/comments/ylseuy/fantamorto_edizione_2023_iscrizioni_aperte/\n"
        + "1. To start a new game type `/start`\n"
        + "2. Use the command `/join TEAM_NAME` to join the game with your team\n"
        + "3. Once all the teams have joined, use the command `/draft` to start selecting the persons of the teams\n"
        + "4. When it's your turn you can pick a player with `/add NAME or ID` where ID is the wikimedia ID that you can find at https://www.wikidata.org\n"
        + "For example you can pick Silvio Berlusconi both with `/add Silvio Berlusconi` or `/add Q11860`\n"
        + "5. Once all the teams are full the game will start automatically\n"
        + "6. To check the current ranking use `/ranking`\n"
        + "\nEnjoy! But do not try to help the Death do his work!"
    )
    
    return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the Fantamorto game"""
    game = get_chat_game(context)
    if game:
        await update.message.reply_text(
            "A game of Fantamorto is already in progress in this group.")
        return
    else:
        chat_id = update.effective_chat
        logger.info(f"Chat {chat_id}: New game")
        with open(BAN_LIST_FILE, 'r') as f:
            ban_list = yaml.load(f, Loader=yaml.FullLoader)
        game = Game(team_size=DEFAULT_FANTAMORTO_TEAM_SIZE, ban_list=ban_list)
        context.chat_data[CHAT_DATA_KEY] = game # type: ignore
        await update.message.reply_text(
            "Welcome to Fantamorto!\n"
            +f"Each player can add up to {game.team_size} real, alive people with a page on wikidata.org.\n"
            +"To join the game send the command /join")
        return


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop a Fantamorto game"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    await update.message.reply_text("Ti ammazzo")
    chat_id = update.effective_chat
    logger.info(f"Chat {chat_id}: Stop game")
    return
    end_msg = "The game has ended!\n"
    if game.ranking:
        end_msg += "Here the final ranking\n"
        for name, score in game.ranking:
            end_msg += f"{name}: {score}\n"
    end_msg += "To start a new game send /start"
    del context.chat_data[CHAT_DATA_KEY] # type: ignore
    await update.message.reply_text(end_msg)


async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join the Fantamorto game"""
    game = get_chat_game(context)

    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    
    if game.status != GAME_STEPS["Starting"]:       
        await update.message.reply_text("You can add players only before the draft")
        return
    
    if not update.effective_user:
        return
    
    # Team name
    if context.args:
        team_name = ' '.join(context.args)
    elif update.effective_user.username:
        team_name = f"Team {update.effective_user.username}"
    else:
        team_name = f"Team {update.effective_user.first_name}"
        

    team = Team(team_name, owner=update.effective_user)

    try:
        game.add_team(team)
    except ValueError as err:
        await update.message.reply_text(str(err))
        return
    chat_id = update.effective_chat
    logging.info(f"Chat: {chat_id}: User {update.effective_user} joined the game with the team {team_name}")

    await update.message.reply_text("You have successfully joined the game. When all the players have joined you can send the command /draft to start the draft")


async def draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the draft for Fantamorto game"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return

    if game.status != GAME_STEPS["Starting"]:
        await update.message.reply_text("You can start the draft only at the beginning of the game. If you want to start a new game send /stop and then /start again")
        return

    if len(game.teams) < 1:
        await update.message.reply_text("There should be at least one player! To join the the game send the command /join")
        return

    game.start_draft()

    current_drafter = game.get_current_drafter()

    chat_id = update.effective_chat
    logging.info(f"Chat: {chat_id}: Draft Started") 
    logging.info(f"Chat: {chat_id}: Current drafter {current_drafter.name}")

    if current_drafter.owner.username:
        current_drafter_owner_mention = f"@{current_drafter.owner.username}"
    else:
        current_drafter_owner_mention = f"[{current_drafter.owner.name}](tg://user?id={current_drafter.owner.id})"

    await update.message.reply_markdown_v2(
            f"The team {escape_markdown(current_drafter.name, version=2)} \({current_drafter_owner_mention}\) must pick the next person"
            +f"You still have {game.team_size - len(current_drafter.players)} persons left\!")
    return


async def draft_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the draft order for Fantamorto game"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if game.status != GAME_STEPS["Draft"]:
        await update.message.reply_text("You have to start the draft to get the draft order")
        return
    
    current_drafter = game.get_current_drafter()
    msg = f"Current drafter is {current_drafter.name} ({current_drafter.owner.name})\n"
    msg += f"He still has {game.team_size - len(current_drafter.players)} persons left!"
    msg += f"The draft order is:\n"
    for idx, t in enumerate(game.draft_order):
        msg += f"{idx}. {t.name} ({t.owner.name})\n"
    await update.message.reply_text(msg)


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add a person to the player team"""
    game = get_chat_game(context)
    if not update.effective_message:
        return
    if not game:
        await update.effective_message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if game.status != GAME_STEPS["Draft"]:
        await update.effective_message.reply_text("You have to start the draft to add players")
        return
    if not context.args:
        await update.effective_message.reply_text("You have to specify a name or a Wikimedia ID adter the command /add. For example `/add Silvio Berlusconi` or `/add Q11860`")
        return
    
    team = game.get_team_from_user(user=update.effective_user)
    if not team:
        await update.effective_message.reply_text("You are not part of the game :( Join with /join")
        return

    if len(team.players) >= game.team_size:
        await update.effective_message.reply_text(f"You already have {game.team_size} players")
        return

    current_drafter = game.get_current_drafter()

    if team != current_drafter:
        if current_drafter.owner.username:
            current_drafter_owner_mention = f"@{current_drafter.owner.username}"
        else:
            current_drafter_owner_mention = f"[{current_drafter.owner.name}](tg://user?id={current_drafter.owner.id})"
        await update.effective_message.reply_markdown_v2(
            f"Sorry, it is not your turn\.\nThe team {escape_markdown(current_drafter.name, version=2)} \({current_drafter_owner_mention}\) must pick the next person\n"
            +f"He still has {game.team_size - len(current_drafter.players)} persons left\!")
        return

    person_name = ' '.join(context.args)

    try:
        persons = get_person(person_name)
        if len(persons) == 0:
            await update.effective_message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(persons) > 1:
            msg = f"I found multiple persons for {escape_markdown(person_name, version=2)}\. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\tPOINTS\n"
            for idx, p in enumerate(persons):
                msg += f"{idx+1}: [{p.WID}](http://www.wikidata.org/entity/{p.WID})\t{p.age}y\t{', '.join(p.occupations)}\t{p.calculate_score()}pt\n"
            await update.effective_message.reply_markdown_v2(msg)
            return
        else:
            person = persons[0]
            added_person = game.add_player(team=team, player=person)

    except requests.ConnectionError:
        await update.effective_message.reply_text("There is a connection problem with wikidata. Try later!")
        return

    except ValueError as err:
        await update.effective_message.reply_text(f"There was an error: {err}")
        return
    
    # This should never happen
    if not added_person:
        await update.effective_message.reply_text(f"For some reason I couldn't add any person. Sorry :(")
        return
    
    chat_id = update.effective_chat
    logging.info(f"Chat: {chat_id}: Team {team.name} added {person.name}") 
    
    await update.effective_message.reply_markdown_v2(
        f"{escape_markdown(team.name, version=2)} has as a new player\!\n"
        +f"[{escape_markdown(person.name, version=2)}](http://www.wikidata.org/entity/{person.WID}) "
        +f"\({escape_markdown(', '.join(person.genders), version=2)}\) "
        +f"a famous {escape_markdown(', '.join(person.occupations), version=2)}\. "
        +f"Born in {person.dob.year}, "
        +f"holds the passport of {escape_markdown(', '.join(person.citizenships), version=2)}\.\n"
        +f"In the event of a tragic fatality he will bring {person.calculate_score()} points to the team\.\n"
        )

    # If all players are selected ask to select remaining captains!
    if all(len(t.players) >= game.team_size for t in game.teams):
        logging.info(f"Chat: {chat_id}: All teams complete") 
        await update.effective_message.reply_text("All the teams are complete!")
        if all(t.has_captain() for t in game.teams):
            game.start_game()
            logging.info(f"Chat: {chat_id}: Game starts") 
            await update.effective_message.reply_text("All the teams have a captain! Let's start the game!")
            return
        else:
            game.start_captain()
            await update.effective_message.reply_text("Now select the captains with /captain [idx] where idx is the index of the player that you can get from /team")
            return
    else:
        next_drafter_ok = False
        next_drafter = None
        while not next_drafter_ok:
            next_drafter = game.next_drafter()
            if len(next_drafter.players) < game.team_size:
                next_drafter_ok = True
        if next_drafter.owner.username:
            mention = f"@{next_drafter.owner.username}"
        else:
            mention = f"[{next_drafter.owner.first_name}](tg://user?id={next_drafter.owner.id})"
        logging.info(f"Chat: {chat_id}: Current drafter {next_drafter.name}")
        await update.effective_message.reply_markdown_v2(
            escape_markdown(
                f"{mention} it's your turn to draft!\n"
                +f"You still have {game.team_size - len(next_drafter.players)} persons left!", version=2))
        return

async def fix_draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_chat_game(context)
    if not game:
        await update.effective_message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if game.status != GAME_STEPS["Draft"]:
        await update.effective_message.reply_text("You have to start the draft to fix it")
        return
    drafter = game.get_current_drafter()

    if len(drafter.players) < game.team_size:
        await update.effective_message.reply_text("Draft order is already ok")
        return
    

    while len(drafter.players) >= game.team_size:
        drafter = game.next_drafter()
    
    chat_id = update.effective_chat
    logging.info(f"Chat: {chat_id}: Draft is fixed") 

    if drafter.owner.username:
        mention = f"@{drafter.owner.username}"
    else:
        mention = f"[{drafter.owner.first_name}](tg://user?id={drafter.owner.id})"
    await update.effective_message.reply_markdown_v2(
        escape_markdown(
            f"Probably I did something wrong... \n"
            +f"{mention} it's your turn to draft!\n"
            +f"You still have {game.team_size - len(drafter.players)} persons left!", version=2))
    return
    

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.effective_message.reply_text("You have to specify a name or a Wikimedia ID after the command /info. For example `/info Silvio Berlusconi` or `/info Q11860`")
        return
    
    person_name = ' '.join(context.args)

    try:
        persons = get_person(person_name)
        if len(persons) == 0:
            await update.effective_message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(persons) > 1:
            msg = f"I found multiple persons for {escape_markdown(person_name, version=2)}\. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\tPOINTS\n"
            for idx, p in enumerate(persons):
                msg += f"{idx+1}: [{p.WID}](http://www.wikidata.org/entity/{p.WID})\t{p.age}y\t{escape_markdown(', '.join(p.occupations), version=2)}\t{p.calculate_score()}pt\n"
            await update.effective_message.reply_markdown_v2(msg)
            return
        else:
            person = persons[0]

    except requests.ConnectionError:
        await update.effective_message.reply_text("There is a connection problem with wikidata. Try later!")
        return

    except ValueError as err:
        await update.effective_message.reply_text(f"There was an error: {err}")
        return
    
    await update.effective_message.reply_markdown_v2(
        f"[{escape_markdown(person.name, version=2)}](http://www.wikidata.org/entity/{person.WID}) "
        +f"\({escape_markdown(', '.join(person.genders), version=2)}\) "
        +f"a famous {escape_markdown(', '.join(person.occupations), version=2)}\. "
        +f"Born in {person.dob.year}, "
        +f"holds the passport of {escape_markdown(', '.join(person.citizenships), version=2)}\.\n"
        +f"In the event of a tragic fatality he will bring {person.calculate_score()} points to the team\.\n"
        )

def get_chat_game(context: ContextTypes.DEFAULT_TYPE) -> Game:
    game = context.chat_data.get(CHAT_DATA_KEY, None) # type: ignore
    if game:
        game.update_structure()
    return game


async def cancel_draft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the draft"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if game.status != GAME_STEPS["Draft"]:
        await update.message.reply_text("You can cancel the draft only when you are in the draft")
        return
    
    game.cancel_draft()
    await update.message.reply_text("The draft has been canceled. Send /draft to start again")


async def all_persons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get all the persons playing the game"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    all_persons = game.all_players
    alive = all_persons["alive"]
    dead = all_persons["dead"]
    if not alive and not dead:
        await update.message.reply_text("Noone is playing in this game.")
        return
    msg = "Here all the persons playing this game\n"
    if alive:
        msg += "\> Playing and still alive\n"
        for k, p in alive.items():
            msg += f"[{escape_markdown(p.name, version=2)}](http://www.wikidata.org/entity/{k})\n"
    if dead:
        msg += "\> Playing and already dead\n"
        for k, p in dead.items():
            msg += f"[{escape_markdown(p.name, version=2)}](http://www.wikidata.org/entity/{k})\n"
    await update.message.reply_markdown_v2(msg)
    return

async def update_ban_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update the ban list"""
    # TODO: make it an automatic job
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    with open(BAN_LIST_FILE, 'r') as f:
        ban_list = yaml.load(f, Loader=yaml.FullLoader)
    if game.ban_list == ban_list:
        await update.message.reply_text("Ban list is already up to date")
        return
    game.update_ban_list(ban_list=ban_list)
    msg = "Ban list is updated\! Currently you can not select these players: \n"
    for wid, name in game.ban_list.items():
        msg += f"[{name}](http://www.wikidata.org/entity/{wid})\n"
    await update.message.reply_markdown_v2(msg)
    return


async def captain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the captain for a given team"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not game.teams:
        await update.message.reply_text("There are no teams in the game. Add one with /join TEAM_NAME.")
        return
    if not context.args:
        await update.message.reply_text("You have to specify an index. You can find them with /team")
        return

    team_owner = update.effective_user
    idx_player = ' '.join(context.args)
    try:
        idx_player = int(idx_player)
    except ValueError:
        await update.message.reply_text("You have to specify an index. Like 0, 1, 2... You can find them with /team")
        return
    if idx_player < 0:
        await update.message.reply_text("You have to specify a positive index. Like 0, 1, 2... You can find them with /team")
        return

    team = game.get_team_from_user(team_owner)
    if game.status not in [GAME_STEPS["Draft"], GAME_STEPS["Captain"]] or not team:
        await update.message.reply_text("You must by in draft or right after to select a captain")
        return

    try:
        game.set_captain(team=team, idx=idx_player)
    except ValueError as err:
        await update.message.reply_text(str(err))
        return
    remaining_captains = [t.has_captain() for t in game.teams if not t.has_captain()]
    if len(remaining_captains) == 0:
        game.start_game()
        await update.message.reply_text("All the teams are full! Let's start the game!")
        return
    else:
        await update.message.reply_text(f"There are still {len(remaining_captains)} teams without captain")
        return

async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rename the player team"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not context.args:
        await update.message.reply_text("You have to specify a new name for your team")
        return
    team = game.get_team_from_user(update.effective_user)
    team_name = ' '.join(context.args)

    game.rename_team(team, team_name)

    await update.message.reply_text(f"The name of your team is now: {team_name}")

async def team(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the player team"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not game.teams:
        await update.message.reply_text("There are no teams in the game. Add one with /join TEAM_NAME.")
        return
    team_name = None
    team_owner = update.effective_user
    use_team_name = False
    if context.args:
        team_name = ' '.join(context.args)
        use_team_name = True

    if use_team_name:
        teams = game.get_team_from_name(team_name)
        msg = f"I found {len(teams)} teams called {team_name}\n"
    else:
        teams = [game.get_team_from_user(team_owner)]
        msg = f"Here is your team!\n"
    if not teams:
        msg = "I couldn't find any team :("
    else:
        for team in teams:
            msg += f"NAME: {team.name}\n"
            msg += f"OWNER: {team.owner.username if team.owner.username else team.owner.name}\n"
            msg += f"SCORE: {team.score if team.score else 0}\n"
            msg += f"**** PLAYERS ****\n"
            for idx, player in enumerate(team.players):
                player_msg = f"{idx}: "
                if player.is_captain:
                    player_msg += "* "
                player_msg += f"{player.name} - {player.age}y "
                if not player.dod:
                    if str(player.WID) == "Q9671":
                        player_msg += f"🌱 "
                    else:
                        player_msg += f"🙂 "
                else:
                    player_msg += f"💀 "
                    if player.is_first_death:
                        player_msg += "🩸 "
                    if player.gonzales:
                        player_msg += "❄️ "
                    if player.cesarini:
                        player_msg += "⛄️ "
                    if player.club27:
                        player_msg += "🤙 "
                    if player.birthday:
                        player_msg += "🎂 "

                player_msg += f"({player.calculate_score()} pt)"
                msg += f"{player_msg}\n"
    await update.message.reply_text(msg)
    return

async def all_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the player team"""
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not game.teams:
        await update.message.reply_text("There are no teams in the game. Add one with /join TEAM_NAME.")
        return
    msg = "These are the current teams:\n"
    for team in game.teams:
        if team.owner.username:
            owner = team.owner.username
        else:
            owner = team.owner.name
        msg += f"{owner}: {team.name}\n"
    await update.message.reply_text(msg)
    return

async def test_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = ""
    if context.args:
        msg = ' '.join(context.args)
    await update.message.reply_text(msg)
    return

async def superuser_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.username != SUPERUSER:
        await update.message.reply_text(f"Only my dad can do this. You are {update.effective_user.username}, my dad is {SUPERUSER}")
        return
    
    msg = ""
    if context.args:
        msg = ' '.join(context.args)
    pattern_command = r"-chat (?P<chat>-?\d+) -team (?P<team>.+) -list (?P<list>.+)"
    pattern_list = r"(Q\d+)"
    m = re.match(pattern_command, msg)
    if not m or not m.group("chat") or not m.group("team") or not m.group("list"):
        await update.message.reply_text("Use /superuser_add -chat CHATID -team TEAMNAME -list Q123 Q456")
        return
    persons = re.findall(pattern_list, m.group("list"))
    if not persons:
        await update.message.reply_text(f"I couldn't find any Wikimedia ids in {m.group('list')}")
        return
    
    chat = int(m.group("chat"))
    game = context.application.chat_data[chat].get("game")
    if not game:
        await update.message.reply_text(f"No game for chat {chat}")
        return
    
    team_name = m.group("team")
    team = game.get_team_from_name(team_name)
    if not team:
        await update.message.reply_text(f"No team for {team_name}")
        return
    elif len(team) > 1:
        await update.message.reply_text(f"Multiple teams for {team_name}")
        return
    else:
        team = team[0]
    
    old_status = game.status
    game.status = GAME_STEPS["Draft"]

    for p in team.players:
        if p.WID in game.all_players["alive"]:
            del game.all_players["alive"][p.WID]
        elif p.WID in game.all_players["dead"]:
            del game.all_players["dead"][p.WID]

    team.players = []
    added_persons = []
    players = get_person(persons)
    time.sleep(5)
    for player in players:
        added_person = game.add_player(team=team, player=player, if_dead=True)
        added_persons.append(added_person)
    # for person in persons:
    #     try:
    #         players = get_person(person)
    #         time.sleep(5)
    #     except requests.exceptions.ConnectionError:
    #         logging.info("SUPERUSER_ADD: Sleep a little bit for Wikidata")
    #         time.sleep(20)
    #         players = get_person(person)
    #         time.sleep(5)
    #     players = get_person(person)
    #     if len(players) == 0:
    #         continue
    #     elif len(players) > 1:
    #         continue

    #     player = players[0]
    #     added_person = game.add_player(team=team, player=player, if_dead=True)
    #     added_persons.append(added_person)

    msg = f"Added {len(added_persons)} persons to team {team_name}\n"
    for idx, p in enumerate(added_persons):
        msg += f"{idx}: {p.name} ({p.WID})\n"
    await update.message.reply_text(msg)

    game.status = old_status

    # await context.bot.send_message(
    #     chat_id=chat,
    #     text="My good creator fixed your mess.\n"+msg)

    return 

async def superuser_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.username != SUPERUSER:
        await update.message.reply_text(f"Only my dad can do this. You are {update.effective_user.username}, my dad is {SUPERUSER}")
        return
    
    msg = ""
    if context.args:
        msg = ' '.join(context.args)
    pattern_command = r"-chat (?P<chat>-?\d+) -msg (?P<msg>.+)"
    m = re.match(pattern_command, msg)
    if not m or not m.group("chat") or not m.group("msg"):
        await update.message.reply_text("Use /superuser_add -chat CHATID -msg TEXT")
        return
    
    chat = int(m.group("chat"))
    msg = m.group("msg")

    await context.bot.send_message(
        chat_id=chat,
        text=msg)

    return 

async def superuser_substitute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.username != SUPERUSER:
        await update.message.reply_text(f"Only my dad can do this. You are {update.effective_user.username}, my dad is {SUPERUSER}")
        return
    
    msg = ""
    if context.args:
        msg = ' '.join(context.args)
    pattern_command = r"-chat (?P<chat>-?\d+) -team (?P<team>.+) -old (?P<old>Q\d+) -new (?P<new>Q\d+)"
    m = re.match(pattern_command, msg)
    if not m or not m.group("chat") or not m.group("team") or not m.group("old") or not m.group("new"):
        await update.message.reply_text("Use /superuser_add -chat CHATID -team TEAMNAME -old WID -new WID")
        return

    chat = int(m.group("chat"))

    game = context.application.chat_data[chat].get("game")
    if not game:
        await update.message.reply_text(f"No game for chat {chat}")
        return
    
    team_name = m.group("team")
    team = game.get_team_from_name(team_name)
    if not team:
        await update.message.reply_text(f"No team for {team_name}")
        return
    elif len(team) > 1:
        await update.message.reply_text(f"Multiple teams for {team_name}")
        return
    else:
        team = team[0]
    
    old = m.group("old")
    new = m.group("new")

    if old not in team.players:
        await update.message.reply_text(f"Person {old} is not in {team_name}")
        return
    
    players = get_person(new)
    if len(players) != 1:
        await update.message.reply_text(f"None or multiple persons with id {new}")
        return
    player = players[0]

    if old in game.all_players["alive"]:
        del game.all_players["alive"][old]
    elif old in game.all_players["dead"]:
        del game.all_players["dead"][old]
    
    old_person = [p for p in team.players if p.WID == old]
    old_person = old_person[0]

    team.players = [p for p in team.players if p.WID != old]

    msg = f"Removed {old_person} from team {team_name}\n"
    await update.message.reply_text(msg)

    old_status = game.status
    game.status = GAME_STEPS["Draft"]

    added_person = game.add_player(team=team, player=player, if_dead=True)

    msg = f"Added {added_person} persons to team {team_name}\n"
    await update.message.reply_text(msg)

    game.status = old_status

    msg = f"My good creator substituted {old_person} with {added_person} for team {team_name}"

    await context.bot.send_message(
        chat_id=chat,
        text=msg)
    return 

async def update_deads(context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Updating deads")
    for chat in context.application.chat_data:
        game = context.application.chat_data[chat].get("game")
        if not game:
            continue
        alive_players = list(game.all_players['alive'].keys())
        dead_players = update_persons(ids = alive_players)
        if dead_players:
            game.update_alive_players(dead_players)
        for p in dead_players:
            info = game.get_player(p)
            msg = "+++ MORTO +++\n"
            msg += f"{info['player'].name} ormai è solo un cadavere!\n"
            msg += f"Gli unici a rallegrarsi sono i tifosi di {info['team'].name} per i quali la morte porta {info['player'].score}\n"
            msg += "È MORTO! MORTO MORTO MORTO!"
            await context.bot.send_message(
                chat_id=chat,
                text=msg)


async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    game = get_chat_game(context)
    if not game:
        await update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    
    msg = "RANKING\n"
    for idx, team in enumerate(game.ranking):
        msg += f"{idx+1}. {team.score} - {team.name}\n"
    await update.message.reply_text(msg)

def main() -> None:

    # Get the application to register handlers
    application = ApplicationBuilder().token(TOKEN).persistence(persistence=my_persistence).build()
    job_queue = application.job_queue

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("stop", stop, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("help", help_command, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("join", join, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("draft", draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("team", team, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("captain", captain, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("rename", rename, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("all_teams", all_teams, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("update_ban", update_ban_list, filters=~filters.UpdateType.EDITED_MESSAGE))
    # application.add_handler(CommandHandler("cancel_draft", cancel_draft, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("draft_order", draft_order, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("all_persons", all_persons, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("test_msg", test_msg))
    application.add_handler(CommandHandler("fix_draft", fix_draft))
    application.add_handler(CommandHandler("superuser_add", superuser_add, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("superuser_send", superuser_send, filters=~filters.UpdateType.EDITED_MESSAGE))
    application.add_handler(CommandHandler("ranking", ranking, filters=~filters.UpdateType.EDITED_MESSAGE))

    if job_queue:
        job_queue.run_repeating(update_deads, interval=timedelta(hours=1))

    # Start the Bot
    application.run_polling()



if __name__ == '__main__':
    main()
