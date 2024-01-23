from typing import Optional
import datetime as dt
import uuid
from html import escape

from telegram import User
from telegram.helpers import escape_markdown

from .athlet import Athlet
from .bonus import Bonus
from . import utils


class Team:
    def __init__(
            self,
            chat_id: int,
            name: str,
            owner: User,
            athlets: Optional[list[Athlet]] = None,
            captain: Optional[Athlet] = None,
            created_on: Optional[dt.datetime] = None,
            updated_on: Optional[dt.datetime] = None
            ) -> None:
        
        now = dt.datetime.now()
        
        self.chat_id = chat_id
        self.name = name
        self.owner_id = utils.user_id(owner)
        self.owner_mention = utils.mention_user(owner)
        self.owner_name = owner.name
        self.athlets = athlets or []
        self._captain = captain
        self.has_first_death = False
        self.created_on = created_on or now
        self.updated_on = updated_on or now
        self.game = None
        self.id = str(uuid.uuid4())

    def __eq__(self, other):
        if type(other) == Team:
            return self.id == other.id
        else:
            return False
    
    def __str__(self):
        return self.name_escaped_html

    @property
    def name_escaped_html(self) -> str:
        return escape(self.name)

    @property 
    def captain(self) -> Athlet:
        return self._captain
    
    @captain.setter
    def captain(self, new_captain: Athlet) -> None:
        if new_captain in self.athlets:
            self._captain = new_captain
    
    @captain.deleter
    def captain(self):
        self._captain = None
    
    @property
    def dead_athlets(self) -> list[Athlet]:
        return [a for a in self.athlets if a.is_dead]
    
    @property
    def all_citizienships(self) -> list[str]:
        main_citizienships = list(set([p.citizienships[0] for p in self.athlets if p.citizienships]))
        return main_citizienships
    
    @property
    def globetrotter(self) -> list[str]:
        main_citizienships = list(set([p.citizienships[0] for p in self.dead_athlets if p.citizienships]))
        return main_citizienships
    
    @property
    def globetrotter_score(self) -> int:
        return Bonus.GLOBETROTTER_MULT * self.len_min_0(self.globetrotter)
    
    @property
    def all_genders(self) -> list[str]:
        main_genders = list(set([p.genders[0] for p in self.athlets if p.genders]))
        return main_genders
    
    @property
    def inclusivity(self) -> list[str]:
        main_genders = list(set([p.genders[0] for p in self.dead_athlets if p.genders]))
        return main_genders
    
    @property
    def inclusivity_score(self) -> int:
        return Bonus.INCLUSIVITY_MULT * self.len_min_0(self.inclusivity)

    @property
    def all_occupations(self) -> list[str]:
        main_occupations = list(set([p.occupations[0] for p in self.athlets if p.occupations]))
        return main_occupations

    @property
    def jack_of_all_trades(self) -> list[str]:
        main_occupations = list(set([p.occupations[0] for p in self.dead_athlets if p.occupations]))
        return main_occupations
        
    @property
    def jack_of_all_trades_score(self) -> int:
        return Bonus.JACK_OF_ALL_TRADES_MULT * self.len_min_0(self.jack_of_all_trades)

    @property
    def score(self) -> int:
        return self._calculate_score()
    
    @property
    def num_athlets(self) -> int:
        return len(self.athlets)
    
    @staticmethod
    def len_min_0(l: list) -> int:
        return max((len(l) - 1), 0)

    def _calculate_score(self) -> int:
        athlets_score = sum(p.score if p.is_dead else 0 for p in self.athlets)
        team_score = self.globetrotter_score + self.inclusivity_score + self.jack_of_all_trades_score

        captain_score = 0
        if self.has_captain():
            captain_score = (Bonus.CAPTAIN_MULT - 1) * self.captain.score
        
        first_death_score = 0
        if self.has_first_death:
            first_death_score = Bonus.FIRST_DEATH
            
        return athlets_score + team_score + captain_score + first_death_score

    def has_captain(self) -> bool:
        if self.captain:
            return True
        else:
            return False
    
    def set_captain_from_idx(self, idx: int) -> None:
        captain = self.athlets[idx]
        self.captain = captain

    def add_athlet(self, athlet: Athlet, allow_deads: bool = False) -> None:
        if athlet in self.athlets:
            raise ValueError("The athlet is already part of this team")
        
        self.athlets.append(athlet)
    
    def remove_athlet(self, athlet: Athlet) -> None:
        if athlet not in self.athlets:
            raise ValueError("The athlet is not part of this team")
        
        self.athlets.remove(athlet)

    def has_all_athlets(self, max_num_athlets) -> bool:
        return self.num_athlets == max_num_athlets
    
    def remove_all_athlets(self) -> None:
        del self.captain
        self.athlets = []
    
    def has_citizienship(self, citizenship: str) -> bool:
        return citizenship in self.all_citizienships
    
    def has_gender(self, gender: str) -> bool:
        return gender in self.all_genders
    
    def has_occupation(self, occupation: str) -> bool:
        return occupation in self.all_occupations
    
    
    