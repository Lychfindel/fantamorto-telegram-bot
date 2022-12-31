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
        self.score = None

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

    def calculate_score(self):
        basic_score = 100 - self.age

        # Primo sangue
        first = 5 if self.is_first_death else 0

        # Speedy gonzales
        gonzales = 0
        if self.dod is not None and self.dod.month == 1:
            gonzales = 3

        # Zona cesarini
        cesarini = 0
        if self.dod is not None and self.dod.month == 12 and self.dod.day >= 25:
            cesarini = 5

        # 27 club
        club27 = 27 if self.age == 27 else 0

        # Globetrotter
        globetrotter = max(0, 2 * (len(self.citizenships) - 1))

        # Inclusivity
        inclusivity = max(0, 5 * (len(self.genders) - 1))

        # Happy birthday
        birthday = 0
        if self.dod is not None and self.dob is not None and self.dod.month == self.dob.month and self.dod.day == self.dob.day:
            birthday = 10

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
    def __init__(self, name="", owner=None, players=[], captain=None):
        self.name = name
        self.owner = owner
        self.players = players
        self.captain = self._set_captain(captain)
        self.score = self._calculate_score()

    def __eq__(self, other):
        return self.owner == other.owner and self.name == other.name

    def _set_captain(self, captain):
        self.captain = None
        for idx, player in enumerate(self.players):
            if captain == player:
                self.captain = captain
                self.players[idx].is_captain = True
            else:
                self.players[idx].is_captain = False

    def _calculate_score(self):
        scores = [p.score if p.dod else 0 for p in self.players]
        self.score = sum(scores)

    def calculate_score(self):
        self._calculate_score()
        return self.score

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
    def __init__(self, teams=[], ban_list=[]):
        self.teams = teams
        self.all_players = {'alive': {}, 'dead': {}}
        self.ban_list = ban_list
        self.first_death = None
        self.status = GAME_STEPS["Starting"]
        self.draft_order = []
        self.current_drafter = 0

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
        next_drafter = self.draft_order[self.current_drafter]
        self.current_drafter += 1
        if self.current_drafter >= len(self.draft_order):
            self.current_drafter = 0
            self.draft_order.reverse()
        return next_drafter
    
    def get_current_drafter(self):
        return self.draft_order[self.current_drafter]
    
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

    def add_player(self, team, player):
        if self.status != GAME_STEPS["Draft"]:
            raise ValueError("You have to start the draft before adding players")
        try:
            idx = self.teams.index(team)
        except ValueError:
            raise ValueError("The team is not part of the game!")
        if player.dod:
            raise ValueError("The player is already dead :(")
        if player.WID in self.all_players['alive']:
            raise ValueError("The player is already part of a team")
        self.all_players['alive'][player.WID] = player
        self.teams[idx].add_player(player)

    def update_alive_players(self, updated_players):
        if not self.first_death:
            update_first_death = True
            self.first_death = []
        else:
            update_first_death = False
        for id, player in updated_players.items():
            if id in self.all_players['alive']:
                del self.all_players['alive'][id]
                if update_first_death:
                    player.is_first_death = True
                    self.first_death.append(player)
                self.all_players['dead'][id] = player
                for t in self.teams:
                    if player in t.players:
                        t.update_player(player)

    @property
    def ranking(self):
        return ((t.name, t.score) for t in self.teams)
