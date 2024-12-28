import datetime as dt
from typing import Optional, List
from html import escape
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Table, create_engine
from sqlalchemy.orm import relationship, declarative_base

from .db import Base
from .bonus import Bonus

class Team(Base):
    __tablename__ = 'teams'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    has_first_death = Column(Boolean, default=False)
    draft_order = Column(Integer, nullable=False, default=0)
    created_on = Column(DateTime, default=dt.datetime.utcnow)
    updated_on = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Many-to-many relationships
    athlets = relationship("Athlet", secondary="athlet_team", back_populates="teams")

    # One-to-many relationship
    captain_id = Column(Integer, ForeignKey("athlets.id"), nullable=True)
    captain = relationship("Athlet", back_populates="captain_of_teams", foreign_keys=[captain_id])
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="teams", foreign_keys=[owner_id])
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    game = relationship("Game", back_populates="teams", foreign_keys=[game_id])

    def __str__(self):
        return self.name_escaped_html
        
    @property
    def name_escaped_html(self):
        from html import escape
        return escape(self.name)

    @property
    def dead_athlets(self):
        return [athlet for athlet in self.athlets if athlet.is_dead]

    @property
    def all_citizenships(self) -> list[str]:
        main_citizenships = list(set([p.main_citizenship for p in self.athlets if p.main_citizenship]))
        return main_citizenships
    
    @property
    def globetrotter(self) -> list[str]:
        main_citizenships = list(set([p.main_citizenship for p in self.dead_athlets if p.main_citizenship]))
        return main_citizenships
    
    @property
    def globetrotter_score(self) -> int:
        return Bonus.GLOBETROTTER_MULT * self.len_min_0(self.globetrotter)
    
    @property
    def all_genders(self) -> list[str]:
        main_genders = list(set([p.main_gender for p in self.athlets if p.main_gender]))
        return main_genders
    
    @property
    def inclusivity(self) -> list[str]:
        main_genders = list(set([p.main_gender for p in self.dead_athlets if p.main_gender]))
        return main_genders
    
    @property
    def inclusivity_score(self) -> int:
        return Bonus.INCLUSIVITY_MULT * self.len_min_0(self.inclusivity)

    @property
    def all_occupations(self) -> list[str]:
        main_occupations = list(set([p.main_occupation for p in self.athlets if p.main_occupation]))
        return main_occupations

    @property
    def jack_of_all_trades(self) -> list[str]:
        main_occupations = list(set([p.main_occupation for p in self.dead_athlets if p.main_occupation]))
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
    def len_min_0(l):
        return max((len(l) - 1), 0)

    def _calculate_score(self):
        from .bonus import Bonus
        athlets_score = sum(athlet.score for athlet in self.athlets if athlet.is_dead)
        team_score = (
            self.globetrotter_score + self.inclusivity_score + self.jack_of_all_trades_score
        )
        captain_score = 0
        if self.has_captain():
            captain_score = (Bonus.CAPTAIN_MULT - 1) * self.captain.score
        first_death_score = Bonus.FIRST_DEATH if self.has_first_death else 0

        return athlets_score + team_score + captain_score + first_death_score

    def has_captain(self):
        return self.captain is not None

    def set_captain_from_idx(self, idx: int) -> None:
        captain = self.athlets[idx]
        self.captain = captain
        
    def add_athlet(self, athlet, allow_deads=False):
        if athlet in self.athlets:
            raise ValueError("The athlet is already part of this team")
        self.athlets.append(athlet)

    def remove_athlet(self, athlet):
        if athlet not in self.athlets:
            raise ValueError("The athlet is not part of this team")
        self.athlets.remove(athlet)
        if self.captain == athlet:
            self.captain = None

    def remove_all_athlets(self):
        self.captain = None
        self.athlets.clear()