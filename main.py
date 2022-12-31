import logging
import os
import random
import requests
from dotenv import load_dotenv
import ipdb

from telegram.ext import CallbackContext, PicklePersistence, Updater, CommandHandler, MessageHandler, Filters
from telegram import Update, ReplyKeyboardMarkup, ParseMode
from telegram.utils.helpers import escape_markdown

from functions.wikidata import get_person
from functions.fantamorto import Game, Team, GAME_STEPS


# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

# Make bot persistent
my_persistence = PicklePersistence(filename='fantamorto-persistence.ptb')

# Constants
FANTAMORTO_MAX_TEAM_SIZE = 3

# Global variables
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHAT_DATA_KEY = "game"

# Functions
def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    update.message.reply_text(
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
    # logging
    logger.debug(f'Chat {update.effective_chat.id} - Help') # type: ignore
    return

def start(update: Update, context: CallbackContext):
    """Start the Fantamorto game"""
    game = get_chat_game(context)
    if game:
        update.message.reply_text(
            "A game of Fantamorto is already in progress in this group.")
    else:
        context.chat_data[CHAT_DATA_KEY] = Game() # type: ignore
        update.message.reply_text(
            "Welcome to Fantamorto!\n"
            +f"Each player can add up to {FANTAMORTO_MAX_TEAM_SIZE} real, alive people with a page on wikidata.org.\n"
            +"To join the game send the command /join")


def stop(update: Update, context: CallbackContext):
    """Stop a Fantamorto game"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    end_msg = "The game has ended!\n"
    if game.ranking:
        end_msg += "Here the final ranking\n"
        for name, score in game.ranking:
            end_msg += f"{name}: {score}\n"
    end_msg += "To start a new game send /start"
    ipdb.set_trace()
    del context.chat_data[CHAT_DATA_KEY] # type: ignore
    update.message.reply_text(end_msg)


def join(update: Update, context: CallbackContext):
    """Join the Fantamorto game"""
    game = get_chat_game(context)
    if context.args:
        team_name = ' '.join(context.args)
    elif update.message.from_user.username:
        team_name = f"Team {update.message.from_user.username}"
    else:
        team_name = f"Team {update.message.from_user.first_name}"

    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return

    team = Team(team_name, owner=update.message.from_user)

    try:
        game.add_team(team)
    except ValueError as err:
        update.message.reply_text(str(err))
        return

    update.message.reply_text("You have successfully joined the game. When all the players have joined you can send the command /draft to start the draft")


def draft(update: Update, context: CallbackContext):
    """Start the draft for Fantamorto game"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return

    if len(game.teams) < 1:
        update.message.reply_text("There should be at least one player! To join the the game send the command /join")
        return

    # TODO: Start draft
    if game.status != GAME_STEPS["Starting"]:
        update.message.reply_text("You can start the draft only at the beginning of the game. If you want to start a new game send /stop and then /start again")
        return
    game.start_draft()
    next_drafter = game.next_drafter()
    if next_drafter.owner.username:
        mention = f"@{next_drafter.owner.username}"
    else:
        mention = f"[{next_drafter.owner.first_name}](tg://user?id={next_drafter.owner.id})"
    update.message.reply_markdown_v2(
        escape_markdown(
            f"{mention} it's your turn to draft!\n"
            +f"You still have {FANTAMORTO_MAX_TEAM_SIZE - len(next_drafter.players)} persons left!", version=2))
    return


def add(update: Update, context: CallbackContext):
    """Add a person to the player team"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not context.args:
        update.message.reply_text("You have to specify a name or a Wikimedia ID adter the command /add. For example `/add Silvio Berlusconi` or `/add Q11860`")
        return
    if game.status != GAME_STEPS["Draft"]:
        update.message.reply_text("You have to start the draft to add players")
        return

    team = game.get_team_from_owner(owner=update.message.from_user)
    if not team:
        update.message.reply_text("You are not part of the game :( Join with /join")
        return
    
    if len(team.players) >= FANTAMORTO_MAX_TEAM_SIZE:
        update.message.reply_text(f"You already have {FANTAMORTO_MAX_TEAM_SIZE} players")
        return
    
    current_drafter = game.get_current_drafter()
    
    if team != current_drafter:
        if team.owner.username:
            team_owner_mention = f"@{current_drafter.owner.username}"
        else:
            team_owner_mention = f"[{current_drafter.owner.name}](tg://user?id={current_drafter.owner.id})"
        update.message.reply_markdown_v2(f"Sorry, it is not your turn\.\nThe team {escape_markdown(team.name, version=2)} ({team_owner_mention}) must pick the next person")
        return

    person_name = ' '.join(context.args)
    try:
        persons = get_person(person_name)
        if len(persons) == 0:
            update.message.reply_text("I couldn't find any match. Try to send directly the Wikimedia ID")
            return
        if len(persons) > 1:
            msg = f"I found multiple persons for {person_name}\. Please send the WID of the one you want\n"
            msg += "WID\tAGE\tOCCUPATIONS\n"
            for idx, p in enumerate(persons):
                msg += f"{idx+1}: [{p.WID}](http://www.wikidata.org/entity/{p.WID})\t{p.age}y\t{', '.join(p.occupations)}\n"
            update.message.reply_markdown_v2(msg)
            return
        else:
            person = persons[0]
            game.add_player(team=team, player=person)

    except requests.ConnectionError:
        update.message.reply_text("There is a connection problem with wikidata. Try later!")
        return
    
    except ValueError as err:
        update.message.reply_text(str(err))
    
    # If all players are selected ask to select remaining captains!
    if all(len(t.players) == FANTAMORTO_MAX_TEAM_SIZE for t in game.teams):
        if all(t.has_captain() for t in game.teams):
            game.start_game()
            update.message.reply_text("All the teams are full! Let's start the game!")
            return
        else:
            game.start_captain()
            update.message.reply_text("Now select the captains with /captain [idx] where idx is the index of the player that you can get from /team")
            return
    else:
        next_drafter = game.next_drafter()
        if next_drafter.owner.username:
            mention = f"@{next_drafter.owner.username}"
        else:
            mention = f"[{next_drafter.owner.first_name}](tg://user?id={next_drafter.owner.id})"
        update.message.reply_markdown_v2(
            escape_markdown(
                f"{mention} it's your turn to draft!\n"
                +f"You still have {FANTAMORTO_MAX_TEAM_SIZE - len(next_drafter.players)} persons left!", version=2))
        return
    

def get_chat_game(context: CallbackContext) -> Game:
    return context.chat_data.get(CHAT_DATA_KEY, None) # type: ignore


def captain(update: Update, context: CallbackContext):
    """Set the captain for a given team"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not game.teams:
        update.message.reply_text("There are no teams in the game. Add one with /join TEAM_NAME.")
        return
    if not context.args:
        update.message.reply_text("You have to specify an index. You can find them with /team")
        return
    
    team_owner = update.message.from_user
    idx_player = ' '.join(context.args)
    idx_player = int(idx_player)
    team = game.get_team_from_owner(team_owner)
    if game.status not in [GAME_STEPS["Draft"], GAME_STEPS["Captain"]] or not team:
        update.message.reply_text("You must by in draft or right after to select a captain")
        return

    try:
        game.set_captain(team=team, idx=idx_player)
    except ValueError as err:
        update.message.reply_text(str(err))
        return
    remaining_captains = [t.has_captain() for t in game.teams if not t.has_captain()]
    if len(remaining_captains) == 0:
        game.start_game()
        update.message.reply_text("All the teams are full! Let's start the game!")
        return
    else:
        update.message.reply_text(f"There are still {len(remaining_captains)} teams without captain")
        return

def rename(update: Update, context: CallbackContext):
    """Rename the player team"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not context.args:
        update.message.reply_text("You have to specify a new name for your team")
        return
    team = game.get_team_from_owner(update.message.from_user)
    team_name = ' '.join(context.args)

    game.rename_team(team, team_name)

    update.message.reply_text(f"The name of your team is now: {team_name}")


def team(update: Update, context: CallbackContext):
    """Get the player team"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not game.teams:
        update.message.reply_text("There are no teams in the game. Add one with /join TEAM_NAME.")
        return
    team_name = None
    team_owner = update.message.from_user
    use_team_name = False
    if context.args:
        team_name = ' '.join(context.args)
        use_team_name = True
    
    if use_team_name:
        teams = game.get_team_from_name(team_name)
        msg = f"I found {len(teams)} teams called {team_name}\n"
    else:
        teams = [game.get_team_from_owner(team_owner)]
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
                    player_msg += f"😕 ({player.calculate_score()} pt)"
                else:
                    player_msg += f"💀 ({player.calculate_score()} pt)"
                msg += f"{player_msg}\n"
    update.message.reply_text(msg)
    return

def all_teams(update: Update, context: CallbackContext):
    """Get the player team"""
    game = get_chat_game(context)
    if not game:
        update.message.reply_text("There is no game of Fantamorto in progress in this group. Start a new game by using the /start command.")
        return
    if not game.teams:
        update.message.reply_text("There are no teams in the game. Add one with /join TEAM_NAME.")
        return
    msg = "These are the current teams:\n"
    for team in game.teams:
        if team.owner.username:
            owner = team.owner.username
        else:
            owner = team.owner.name
        msg += f"{owner}: {team.name}\n"
    update.message.reply_text(msg)
    return


def main() -> None:
    # Create the Updater and pass it your bot's token.
    updater = Updater(TOKEN, persistence=my_persistence) # type: ignore
    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("start", start, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("stop", stop, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("help", help_command, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("join", join, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("draft", draft, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("add", add, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("team", team, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("captain", captain, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("rename", rename, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CommandHandler("all_teams", all_teams, filters=~Filters.update.edited_message))

    # Start the Bot
    updater.start_polling()

    # Block until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
