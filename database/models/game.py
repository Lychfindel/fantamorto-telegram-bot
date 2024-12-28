from typing import Optional
import random
import uuid
import enum
import datetime as dt
from typing import Optional, List
from html import escape
from sqlalchemy import Enum, Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Table, create_engine
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.orm import Session

from telegram import User as TgUser

from .db import Base
from .team import Team
from .athlet import Athlet
from .user import User
from . import utils

class Status(enum.Enum):
    START   = 0
    DRAFT   = 1
    CAPTAIN = 2
    RUN     = 3
    END     = 4

class Game(Base):
    __tablename__ = 'games'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, nullable=False)
    team_size = Column(Integer, default=10)
    status = Column(Enum(Status), default=Status.START)
    draft_number = Column(Integer, nullable=False, default=0)
    created_on = Column(DateTime, default=dt.datetime.utcnow)
    updated_on = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Many-to-many relationships
    first_deaths = relationship("Athlet", secondary="firstdeath_game", back_populates="firstdeathgames")
    # One-to-many relationship
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    creator = relationship("User", back_populates="games", foreign_keys=[creator_id])
    
    teams = relationship("Team", back_populates="game", foreign_keys="[Team.game_id]", cascade="all, delete-orphan")

    @property
    def ranking(self) -> list[Team]:
        return sorted(self.teams, key=lambda x: x.score, reverse=True)

    @property 
    def athlets(self) -> list[Athlet]:
        return [athlet for team in self.teams for athlet in team.athlets]
        
    @property
    def athlets_alive(self) -> list[Athlet]:
        return [athlet for athlet in self.athlets if not athlet.is_dead]
    
    @property
    def athlets_dead(self) -> list[Athlet]:
        return [athlet for athlet in self.athlets if athlet.is_dead]

    @property
    def num_teams(self) -> int:
        return len(self.teams)
    
    @property
    def num_athlets(self) -> int:
        return len(self.athlets)

    def get_team_from_owner(self, owner: User, session: Session) -> Team:
        team = session.query(Team).filter_by(game=self, owner=owner).one_or_none()
        return team
    
    def start_draft(self) -> None:
        draft_order = list(range(self.num_teams))
        random.shuffle(draft_order)

        for team, order in zip(self.teams, draft_order):
            team.draft_order = order
        
        self.draft_number = 0
        
        self.status = Status.DRAFT
    
    def advance_draft(self) -> Team:
        self.draft_number += 1
        return self.get_current_drafter()
    
    def get_current_drafter(self) -> Team:
        # draft order alternate after every round
        order_reverse = int(self.draft_number / self.num_teams) % 2 == 1
        draft_index = self.draft_number % self.num_teams
        if order_reverse:
            draft_index = self.num_teams - draft_index - 1
        for team in self.teams:
            if team.draft_order == draft_index:
                return team
    
    def cancel_draft(self) -> None:
        for team in self.teams:
            team.remove_all_athlets()
        self.current_drafter_idx = None
        self.status = Status.START
    
    def get_draft_order(self):
        order_reverse = int(self.draft_number / self.num_teams) % 2 == 1
        teams = sorted(self.teams, key=lambda x: x.draft_order, reverse=order_reverse)
        return teams
    # def pause_draft(self) -> None:
    #     self.status = Status.START
    
    def start_game(self):
        self.status = Status.RUN

    def end_game(self):
        self.status = Status.END
    
    def start_captain(self):
        self.status = Status.CAPTAIN
    
    def set_captain(self, team: Team, idx: int) -> None:
        if self.status not in [Status.DRAFT, Status.CAPTAIN]:
            raise ValueError("You have to be in the draft or right after to set a captain")
        
        if team not in self.teams:
            raise ValueError("The team is not part of the game")
        elif idx >= team.num_athlets:
            raise ValueError(f"There is no athlet with index {idx}.")

        team.set_captain_from_idx(idx)
    
    def rename_team(self, team: Team, name: str) -> None:
        if team not in self.teams:
            raise ValueError("The team is not part of the game")
        team.name = name
    
    def add_athlet(self, team: Team, athlet: Athlet, allow_deads: bool = False) -> None:
        if self.status != Status.DRAFT:
            raise ValueError("You have to start the draft before adding athlets")
        
        if team not in self.teams:
            raise ValueError("The team is not part of the game!")
        
        # if athlet in self.ban_list:
        #     raise ValueError("The athlet is in the ban list")
        
        if athlet in self.athlets:
            raise ValueError("The athlet is already part of a team")
        
        if athlet.is_dead and not allow_deads:
            raise ValueError("The athlet is already dead :(")

        team.add_athlet(athlet)
    
    def get_teams_with_athlet(self, athlet: Athlet) -> list[Team]:
        return [t for t in self.teams if athlet in t.athlets]

    def update_first_death(self, new_dead_athlets: list[Athlet]) -> list[Team]:
        if self.first_deaths:
            return []
        
        athlets_in_game = [ath for ath in new_dead_athlets if ath in self.athlets]
        # remove alive athlets (this should never happen)
        athlets_in_game = [ath for ath in athlets_in_game if ath.is_dead]

        if not athlets_in_game:
            return []

        dates_of_death = sorted(set([ath.date_of_death for ath in athlets_in_game]))

        first_date = dates_of_death[0]

        first_dead_athlets = [ath for ath in athlets_in_game if ath.date_of_death == first_date]
        
        self.first_deaths = first_dead_athlets

        first_death_teams = []

        for ath in first_dead_athlets:
            for team in self.get_teams_with_athlet(ath):
                team.has_first_death = True
                if team not in first_dead_athlets:
                    first_death_teams.append(team)

        return first_death_teams
    
    # def add_to_banlist(self, athlet: Athlet) -> None:
    #     self.ban_list.append(athlet)

    def is_creator(self, user: int|TgUser) -> bool:
        user_id = utils.user_id(user)
        return user_id == self.creator.telegram_id
    
        