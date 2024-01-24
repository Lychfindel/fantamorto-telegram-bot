import datetime as dt
from typing import Optional
from html import escape

import dateutil.parser as dp

from .bonus import Bonus
# from .game import Game
# from .team import Team

PRINT_DATE_FORMAT = r"%d-%m-%Y"
WIKIDATA_URL = "http://www.wikidata.org/entity/"

class Athlet:
    def __init__(
            self,
            WID: str,
            name: str,
            dob: str|dt.date,
            dod: Optional[str|dt.date] = None,
            citizienships: Optional[list[str]] = None,
            genders: Optional[list[str]] = None,
            occupations: Optional[list[str]] = None,
            is_banned: Optional[bool] = False,
            created_on: Optional[dt.datetime] = None,
            updated_on: Optional[dt.datetime] = None,
            ) -> None:
        
        now = dt.datetime.now()

        self.wiki_id = WID # ID of wikimedia
        self.url = f"{WIKIDATA_URL}{WID}"
        self.name = name
        self.is_dead = False
        self.date_of_birth = self._parse_date(dob)
        self.date_of_death = dod
        self.citizienships = citizienships or []
        self.genders = genders or []
        self.occupations = occupations or []
        self.is_banned = is_banned
        #self.is_dead = True if self.date_of_death else False
        self.created_on = created_on or now
        self.updated_on = updated_on or now

        self.teams: list[Team] = []
        self.games: list[Game] = []
    
    def __eq__(self, other):
        if type(other) == Athlet:
            return self.wiki_id == other.wiki_id
        else:
            return False
    
    def __repr__(self):
        string = f"{self.name} ({dt.datetime.strftime(self.date_of_birth, PRINT_DATE_FORMAT)}"
        if self.date_of_death:
            string += f" - {dt.datetime.strftime(self.date_of_death, PRINT_DATE_FORMAT)}"
        string += ")"
        return f"Athlet({string})"

    def __str__(self):
        string = f"{self.name_escaped_html} ({dt.datetime.strftime(self.date_of_birth, PRINT_DATE_FORMAT)}"
        if self.date_of_death:
            string += f" - {dt.datetime.strftime(self.date_of_death, PRINT_DATE_FORMAT)}"
        string += ")"
        return string
    
    @property
    def name_escaped_html(self) -> str:
        return escape(self.name)
    
    @property
    def date_of_death(self) -> dt.date:
        return self._date_of_death
    
    @date_of_death.setter
    def date_of_death(self, dod: [str|dt.date]) -> None:
        self._date_of_death = self._parse_date(dod) if dod else None
        self.is_dead = True if self._date_of_death else False
    
    @property
    def age(self) -> int:
        recent_date = dt.datetime.now().date()
        if self.is_dead:
            recent_date = self.date_of_death
        return self.calculate_age(self.date_of_birth, recent_date)
    
    @property
    def gonzales(self) -> bool:
        gonzales = False
        if self.is_dead and self.date_of_death.month == 1:
            gonzales = True
        return gonzales
    
    @property
    def cesarini(self) -> bool:
        cesarini = False
        if self.is_dead and self.date_of_death.month == 12 and self.date_of_death.day >= 25:
            cesarini = True
        return cesarini
    
    @property
    def club27(self) -> bool:
        return self.age == 27
    
    @property
    def birthday(self) -> bool:
        birthday = False
        if self.is_dead and self.month_and_day(self.date_of_death) == self.month_and_day(self.date_of_birth):
            birthday = True
        return birthday
    
    @property
    def score(self) -> int:
        return self.calculate_score()
    
    @property
    def theoretical_score(self) -> int:
        return self.calculate_theoretical_score()

    @staticmethod
    def calculate_age(date1: dt.date, date2: dt.date) -> int:
        years   = date2.year - date1.year
        months  = date2.month - date1.month
        days    = date2.day - date1.day
        
        age = years - 1
        
        if months >= 0 and days >= 0:
            age += + 1
        return age
    
    @staticmethod
    def month_and_day(date: dt.date):
        return (date.month, date.day)

    def _parse_date(self, date) -> dt.date|None:
        if isinstance(date, dt.date):
            return date
        elif isinstance(date, str):
            return dp.parse(date).date()
        return None
    
    def calculate_theoretical_score(self) -> int:
        basic_score = 100 - self.age

        # Speedy Gonzales
        gonzales = Bonus.SPEEDY_GONZALES if self.gonzales else 0

        # Zona Cesarini
        cesarini = Bonus.ZONA_CESARINI if self.cesarini else 0

        # Club 27
        club27 = Bonus.CLUB_27 if self.club27 else 0

        # Happy Birthday
        birthday = Bonus.HAPPY_BIRTHDAY if self.birthday else 0

        return basic_score + gonzales + cesarini + club27 + birthday
    
    def calculate_score(self) -> int:
        if self.is_banned:
            return 0
        if not self.is_dead:
            return 0
        return self.theoretical_score

    def update_from_other(self, other) -> None:
        if not isinstance(other, Athlet):
            return
        self.date_of_birth = other.date_of_birth
        self.date_of_death = other.date_of_death
        self.occupations = other.occupations
        self.genders = other.genders
        self.citizienships = other.citizienships
    
    def get_description(self) -> str:
        if len(self.genders) < 1:
            gender_desc = "No gender"
        else:
            desc1 = f"<u>{escape(self.genders[0])}</u>"
            desc2 = escape(", ".join(self.genders[1:]))
            gender_desc = ", ".join([desc1, desc2]) if desc2 else desc1

        if len(self.citizienships) < 1:
            citizienship_desc = "No citizienship"
        else:
            desc1 = f"<u>{escape(self.citizienships[0])}</u>"
            desc2 = escape(", ".join(self.citizienships[1:]))
            citizienship_desc = ", ".join([desc1, desc2]) if desc2 else desc1
        
        if len(self.occupations) < 1:
            occupation_desc = "No occupation"
        else:
            desc1 = f"<u>{escape(self.occupations[0])}</u>"
            desc2 = escape(", ".join(self.occupations[1:]))
            occupation_desc = ", ".join([desc1, desc2]) if desc2 else desc1
        
        
        desc = f"<a href=\"{self.url}\">{self.name_escaped_html}</a> "\
        +f"({gender_desc}) "\
        +f"a famous {occupation_desc}. "\
        +f"Born on {self.date_of_birth} ({self.age} years), "\
        +f"holds the passport of {citizienship_desc}.\n"\
        +f"In the event of a tragic fatality he will bring {self.theoretical_score} points to the team.\n"
        
        return desc