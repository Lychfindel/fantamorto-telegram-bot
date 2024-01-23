from typing import Optional
import random
import uuid

from telegram import User

from .team import Team
from .athlet import Athlet
from . import utils

class Status:
    START   = 0
    DRAFT   = 1
    CAPTAIN = 2
    RUN     = 3
    END     = 4

class Game:
    def __init__(
            self,
            chat_id: int,
            creator: User,
            teams: Optional[list[Team]] = None,
            ban_list: Optional[list[Athlet]] = None,
            team_size: Optional[int] = 10
            ) -> None:
        self.chat_id = chat_id
        self.creator_id = utils.user_id(creator)
        self.creator_mention = utils.mention_user(creator)
        self.creator_name = creator.name
        self.teams = teams or []
        self.ban_list = ban_list or []
        self.team_size = team_size
        self.status = Status.START
        self.draft_order: list[Team] = None
        self.current_drafter_idx: int = None
        self.first_deaths: list[Athlet] = []
        self.id = str(uuid.uuid4())
    
    @property
    def ranking(self) -> list[Team]:
        return sorted(self.teams, key=lambda x: x.score, reverse=True)
        
    @property
    def athlets_alive(self) -> list[Athlet]:
        return [athlet for athlet in self.athlets if not athlet.is_dead]
    
    @property
    def athlets_dead(self) -> list[Athlet]:
        return [athlet for athlet in self.athlets if athlet.is_dead]

    @property 
    def athlets(self) -> list[Athlet]:
        return [athlet for team in self.teams for athlet in team.athlets]
    
    @property
    def num_teams(self) -> int:
        return len(self.teams)
    
    @property
    def num_athlets(self) -> int:
        return len(self.athlets)
    
    def add_team(self, team: Team) -> None:
        if team.owner_id in [t.owner_id for t in self.teams]:
            raise ValueError(f"There is already a team owned by {team.owner_mention}")
        if team in self.teams:
            raise ValueError("The team is already part of the game!")
        if self.status != Status.START:
            raise ValueError("Is not possible to add teams when the game is running")
        self.teams.append(team)
        team.game = self.id
    
    def start_draft(self) -> None:
        self.draft_order = [t for t in self.teams] # We copy the array so we can shuffle only the new one
        random.shuffle(self.draft_order)
        self.current_drafter_idx = 0
        self.status = Status.DRAFT
    
    def advance_draft(self) -> Team:
        self.current_drafter_idx += 1
        if self.current_drafter_idx >= len(self.draft_order):
            self.current_drafter_idx = 0
            self.draft_order.reverse()
        return self.get_current_drafter()
    
    def get_current_drafter(self) -> Team:
        return self.draft_order[self.current_drafter_idx]
    
    def cancel_draft(self) -> None:
        for team in self.teams:
            team.remove_all_athlets
        self.status = Status.START
    
    def start_game(self):
        self.status = Status.RUN

    def end_game(self):
        self.status = Status.END
    
    def start_captain(self):
        self.status = Status.CAPTAIN
    
    def get_team_from_owner(self, owner: User) -> Team:
        owner_id = utils.user_id(owner)
        team = [t for t in self.teams if owner_id == t.owner_id]
        if team:
            return team[0]
        else:
            return None
    
    def set_captain(self, team: Team, idx: int) -> None:
        if self.status not in [Status.DRAFT, Status.CAPTAIN]:
            raise ValueError("You have to be in the draft or right after to set a captain")
        
        if team not in self.teams:
            raise ValueError("The team is not part of the game")
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
        
        if athlet in self.ban_list:
            raise ValueError("The athlet is in the ban list")
        
        if athlet in self.athlets:
            raise ValueError("The athlet is already part of a team")
        
        if athlet.is_dead and not allow_deads:
            raise ValueError("The athlet is already dead :(")
        
        athlet.games.append(self)

        team.add_athlet(athlet)
        self.athlets.append(athlet)
    
    def get_teams_with_athlet(self, athlet: Athlet) -> list[Team]:
        return [t for t in self.teams if athlet in t.athlets]

    def update_first_death(self, new_dead_athlets: list[Athlet]) -> None:
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

        for ath in first_dead_athlets:
            for team in self.get_teams_with_athlet(ath):
                team.has_first_death = True
        
        self.first_deaths = first_dead_athlets
    
    def add_to_banlist(self, athlet: Athlet) -> None:
        self.ban_list.append(athlet)

    def check_creator(self, user: int|User) -> bool:
        user_id = utils.user_id(user)
        return user_id == self.creator_id
    
    def remove_from_athlet(self, athlet: Athlet) -> None:
        athlet.games.remove(self)

    def remove_from_all_athlets(self) -> None:
        for athlet in self.athlets:
            self.remove_from_athlet(athlet)
        