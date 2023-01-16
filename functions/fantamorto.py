import datetime as dt
import dateutil.parser
import random

GAME_STEPS = {
    "Starting": 0,
    "Draft": 1, 
    "Captain": 2,
    "Running": 3,
    "Close": 4}

PRINT_DATE_FORMAT = r"%d-%m-%Y"

class Player:
    def __init__(self, id=0, first_name="", last_name="", name="", username=""):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.name = name
        self.username = username
    
    def __repr__(self):
        string = ""
        if self.username:
            string += f"{self.username}"
        else:
            string += f"{self.name}"
        return f"Player({string})"

    def __str__(self):
        string = ""
        if self.username:
            string += f"{self.username}"
        else:
            string += f"{self.name}"
        return f"{string}"
    
    def mention(self):
        if self.username:
            return f"@{self.username}"
        else:
            return f"[{self.name}](tg://user?id={self.id})"

    def from_ptb(self, user):
        self.id = user.id
        self.first_name = user.first_name
        self.last_name = user.last_name
        self.name = user.name
        self.username = user.username

def player_from_ptb(user):
    p = Player()
    p.from_ptb(user)
    return p

class Person:
    def __init__(self, name, dob, dod=None, WID=None, citizenships=[], genders=[], occupations=[]):
        self.name = name
        self.dob = self._parse_date(dob)
        self.dod = self._parse_date(dod)
        self.WID = WID
        self.citizenships = citizenships
        self.genders = genders
        self.occupations = occupations
        self.is_captain = False
        self.is_first_death = False

    def __eq__(self, other):
        return self.WID == other.WID
    
    def __repr__(self):
        string = f"{self.name} ({dt.datetime.strftime(self.dob, PRINT_DATE_FORMAT)}"
        if self.dod:
            string += f" - {dt.datetime.strftime(self.dod, PRINT_DATE_FORMAT)}"
        string += ")"
        return f"Person({string})"

    def __str__(self):
        string = f"{self.name} ({dt.datetime.strftime(self.dob, PRINT_DATE_FORMAT)}"
        if self.dod:
            string += f" - {dt.datetime.strftime(self.dod, PRINT_DATE_FORMAT)}"
        string += ")"
        return string

    def _parse_date(self, date):
        if isinstance(date, dt.datetime):
            return date
        elif isinstance(date, str):
            return dateutil.parser.parse(date)
        return None

    @property
    def age(self):
        if self.dod is not None:
            recent_date = self.dod
        else:
            recent_date = dt.datetime.now()
        return self._calculate_age(self.dob, recent_date)

    def _calculate_age(self, date1, date2):
        years = date2.year - date1.year
        months = date2.month - date1.month
        days = date2.day - date1.day
        if months >= 0 and days >= 0:
            return years + 1
        else:
            return years
    
    @property
    def gonzales(self):
        gonzales = False
        if self.dod is not None and self.dod.month == 1:
            gonzales = True
        return gonzales
    
    @property
    def cesarini(self):
        cesarini = False
        if self.dod is not None and self.dod.month == 12 and self.dod.day >= 25:
            cesarini = True
        return cesarini
    
    @property
    def club27(self):
        return self.age == 27
    
    @property
    def birthday(self):
        birthday = False
        if self.dod is not None and self.dob is not None and self.dod.month == self.dob.month and self.dod.day == self.dob.day:
            birthday = True
        return birthday
    
    @property
    def score(self):
        return self.calculate_score()

    def calculate_score(self):
        basic_score = 100 - self.age

        # Primo sangue
        first = 5 if self.is_first_death else 0

        # Speedy gonzales
        gonzales = 3 if self.gonzales else 0

        # Zona cesarini
        cesarini = 5 if self.cesarini else 0

        # 27 club
        club27 = 27 if self.club27 else 0

        # Globetrotter
        globetrotter = max(0, 2 * (len(self.citizenships) - 1))

        # Inclusivity
        inclusivity = max(0, 5 * (len(self.genders) - 1))

        # Happy birthday
        birthday = 10 if self.birthday else 0

        # Jack of all trades
        jack = max(0, 2 * (len(self.occupations) - 1))

        total_score = basic_score + first + gonzales + cesarini + club27 + globetrotter + inclusivity + birthday + jack

        if self.is_captain:
            return total_score * 2
        else:
            return total_score

    def add_occupation(self, occupation):
        self.occupations.append(occupation)

    def add_citizienship(self, citizienship):
        self.citizenships.append(citizienship)

    def add_gender(self, gender):
        self.genders.append(gender)


class Team:
    def __init__(self, name="", owner=Player(), players=[], captain=None):
        self.name = name
        self.owner = owner
        self.players = players
        self.captain = self._set_captain(captain)

    def __eq__(self, other):
        return self.owner.id == other.owner.id and self.name == other.name

    def _set_captain(self, captain):
        self.captain = None
        for idx, player in enumerate(self.players):
            if captain == player:
                self.captain = captain
                self.players[idx].is_captain = True
            else:
                self.players[idx].is_captain = False

    @property
    def score(self):
        self._calculate_score()

    def _calculate_score(self):
        scores = [p.score if p.dod else 0 for p in self.players]
        return sum(scores)

    def set_captain(self, captain):
        self._set_captain(captain)
        return self.captain

    def has_captain(self):
        if self.captain:
            return True
        else:
            return False

    def add_player(self, player):
        if player in self.players:
            raise ValueError("The player is already part of this team")
        self.players.append(player)

    def update_player(self, player):
        if player not in self.players:
            raise ValueError("The player is not part of this team")
        for p in self.players:
            p.dod = player.dod
            p.citizenships = player.citizenships
            p.genders = player.genders
            p.occupations = player.occupations
            p.is_first_death = player.is_first_death


class Game:
    def __init__(self, teams=[], ban_list={}, team_size=10):
        self.teams = teams
        self.all_players = {'alive': {}, 'dead': {}}
        self.ban_list = ban_list
        self.first_death = None
        self.status = GAME_STEPS["Starting"]
        self.draft_order = []
        self.current_drafter = 0
        self.team_size = team_size
    
    def update_structure(self):
        if not hasattr(self, "team_size"):
            self.team_size = 10

    def add_team(self, team):
        if team.owner in [t.owner for t in self.teams]:
            raise ValueError(f"There is already a team owned by {team.owner}")
        if team in self.teams:
            raise ValueError("The team is already part of the game!")
        self.teams.append(team)
    
    def start_draft(self):
        self.draft_order = [t for t in self.teams]
        random.shuffle(self.draft_order)
        self.current_drafter = 0
        self.status = GAME_STEPS["Draft"]
    
    def next_drafter(self):
        self.current_drafter += 1
        if self.current_drafter >= len(self.draft_order):
            self.current_drafter = 0
            self.draft_order.reverse()
        next_drafter = self.draft_order[self.current_drafter]
        return next_drafter
    
    def get_current_drafter(self):
        return self.draft_order[self.current_drafter]
    
    def cancel_draft(self):
        for team in self.teams:
            team.players = []
            team.captain = None
            team.score = 0
        self.all_players = {'alive': {}, 'dead': {}}
        self.status = GAME_STEPS["Starting"]

    
    def start_game(self):
        self.status = GAME_STEPS["Running"]

    def close_game(self):
        self.status = GAME_STEPS["Close"]
    
    def start_captain(self):
        self.status = GAME_STEPS["Captain"]
    
    def get_team_from_owner(self, owner):
        team = [t for t in self.teams if t.owner == owner]
        if team:
            return team[0]
        else:
            return None
    
    def get_team_from_user(self, user):
        team = [t for t in self.teams if t.owner.id == user.id]
        if team:
            return team[0]
        else:
            return None
    
    def set_captain(self, team, idx):
        if self.status not in [GAME_STEPS["Draft"], GAME_STEPS["Captain"]]:
            raise ValueError("You have to be in the draft or right after to set a captain")
        try:
            idx_team = self.teams.index(team)
        except ValueError:
            raise ValueError("The team is not part of the game!")

        self.teams[idx_team].set_captain(team.players[idx])
    
    def rename_team(self, team, name):
        try:
            idx_team = self.teams.index(team)
        except ValueError:
            raise ValueError("The team is not part of the game!")
        self.teams[idx_team].name = name
    
    def get_team_from_name(self, name):
        return [t for t in self.teams if t.name == name]

    def add_player(self, team, player, if_dead=False):
        if self.status != GAME_STEPS["Draft"]:
            raise ValueError("You have to start the draft before adding players")
        try:
            idx = self.teams.index(team)
        except ValueError:
            raise ValueError("The team is not part of the game!")
        if player.dod and not if_dead:
            raise ValueError("The player is already dead :(")
        if player.WID in self.ban_list:
            raise ValueError("The player is in the ban list")
        if player.WID in self.all_players['alive']:
            raise ValueError("The player is already part of a team")
        self.all_players['alive'][player.WID] = player
        self.teams[idx].add_player(player)
        return player

    def update_alive_players(self, updated_players):
        if not self.first_death:
            update_first_death = True
            self.first_death = []
        else:
            update_first_death = False
        for player in updated_players.items():
            if player.WID in self.all_players['alive']:
                del self.all_players['alive'][player.WID]
                if update_first_death:
                    player.is_first_death = True
                    self.first_death.append(player)
                self.all_players['dead'][player.WID] = player
                for t in self.teams:
                    if player in t.players:
                        t.update_player(player)
    
    def update_ban_list(self, ban_list):
        self.ban_list = ban_list
    
    def get_player(self, player):
        info = {"team": None, "player": None}
        if player.WID not in self.all_players['alive'] and player.id not in self.all_players['dead']:
            raise ValueError("The player is not part of the game!")
        elif player.WID in self.all_players['alive']:
            p = self.all_players["alive"][player.WID]
        else:
            p = self.all_players["dead"][player.WID]
        
        for team in self.teams:
            if p in team.players:
                info["team"] = team
                info["player"] = p
                return info

    @property
    def ranking(self):
        return sorted(self.teams, key=lambda x: x.score, reverse=True)
