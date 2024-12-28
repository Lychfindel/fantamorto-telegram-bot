import datetime as dt
import dateutil.parser as dp
from typing import Optional, List
from html import escape
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Table, create_engine
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.orm import Session

from .db import Base
from .bonus import Bonus

PRINT_DATE_FORMAT = r"%d-%m-%Y"
WIKIDATA_URL = "http://www.wikidata.org/entity/"

# Association tables for many-to-many relationships
firstdeath_game = Table(
    'firstdeath_game', Base.metadata,
    Column('athlet_id', Integer, ForeignKey('athlets.id'), primary_key=True),
    Column('game_id', Integer, ForeignKey('games.id'), primary_key=True)
)

athlet_team = Table(
    'athlet_team', Base.metadata,
    Column('athlet_id', Integer, ForeignKey('athlets.id'), primary_key=True),
    Column('team_id', Integer, ForeignKey('teams.id'), primary_key=True)
)

athlet_gender = Table(
    'athlet_gender', Base.metadata,
    Column('athlet_id', Integer, ForeignKey('athlets.id'), primary_key=True),
    Column('gender_id', Integer, ForeignKey('genders.id'), primary_key=True)
)

athlet_citizenship = Table(
    'athlet_citizenship', Base.metadata,
    Column('athlet_id', Integer, ForeignKey('athlets.id'), primary_key=True),
    Column('citizenship_id', Integer, ForeignKey('citizenships.id'), primary_key=True)
)

athlet_occupation = Table(
    'athlet_occupation', Base.metadata,
    Column('athlet_id', Integer, ForeignKey('athlets.id'), primary_key=True),
    Column('occupation_id', Integer, ForeignKey('occupations.id'), primary_key=True)
)

# Basic tables
class Gender(Base):
    __tablename__ = 'genders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    wiki_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    athlets = relationship("Athlet", secondary=athlet_gender, back_populates="genders")

    # One-to-many relationships
    gender_of_athlets = relationship("Athlet", back_populates="main_gender", foreign_keys="[Athlet.main_gender_id]", cascade="all")
    
    def __repr__(self):
        return f"<Gender(name='{self.name}')>"
    
    def __str__(self):
        return f"{self.name}"
    
    @staticmethod
    def get_or_create(session: Session, wiki_id: str, name: str):
        gender = session.query(Gender).filter_by(wiki_id=wiki_id).one_or_none()
        if not gender:
            gender = Gender(wiki_id=wiki_id, name=name)
            session.add(gender)
        return gender

class Occupation(Base):
    __tablename__ = 'occupations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    wiki_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    athlets = relationship("Athlet", secondary=athlet_occupation, back_populates="occupations")

    # One-to-many relationships
    occupation_of_athlets = relationship("Athlet", back_populates="main_occupation", foreign_keys="[Athlet.main_occupation_id]", cascade="all")
    
    def __repr__(self):
        return f"<Occupation(name='{self.name}')>"
    
    def __str__(self):
        return f"{self.name}"
    
    @staticmethod
    def get_or_create(session: Session, wiki_id: str, name: str):
        occupation = session.query(Occupation).filter_by(wiki_id=wiki_id).one_or_none()
        if not occupation:
            occupation = Occupation(wiki_id=wiki_id, name=name)
            session.add(occupation)
        return occupation

class Citizenship(Base):
    __tablename__ = 'citizenships'

    id = Column(Integer, primary_key=True, autoincrement=True)
    wiki_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    athlets = relationship("Athlet", secondary=athlet_citizenship, back_populates="citizenships")

    # One-to-many relationships
    citizenship_of_athlets = relationship("Athlet", back_populates="main_citizenship", foreign_keys="[Athlet.main_citizenship_id]", cascade="all")
    
    def __repr__(self):
        return f"<Citizenship(name='{self.name}')>"
    
    def __str__(self):
        return f"{self.name}"
    
    @staticmethod
    def get_or_create(session: Session, wiki_id: str, name: str):
        citizenship = session.query(Citizenship).filter_by(wiki_id=wiki_id).one_or_none()
        if not citizenship:
            citizenship = Citizenship(wiki_id=wiki_id, name=name)
            session.add(citizenship)
        return citizenship

# Main class

class Athlet(Base):
    __tablename__ = 'athlets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    wiki_id = Column(String, unique=True, nullable=False)  # ID of Wikimedia
    name = Column(String, nullable=False)
    date_of_birth = Column(Date, nullable=False)
    date_of_death = Column(Date, nullable=True)
    is_banned = Column(Boolean, default=False)
    created_on = Column(DateTime, default=dt.datetime.utcnow)
    updated_on = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    # Many-to-many relationships
    teams = relationship('Team', secondary=athlet_team, back_populates='athlets')
    genders = relationship('Gender', secondary=athlet_gender, back_populates='athlets')
    citizenships = relationship('Citizenship', secondary=athlet_citizenship, back_populates='athlets')
    occupations = relationship('Occupation', secondary=athlet_occupation, back_populates='athlets')
    firstdeathgames = relationship('Game', secondary=firstdeath_game, back_populates='first_deaths')

    # One-to-many relationships
    captain_of_teams = relationship("Team", back_populates="captain", foreign_keys="[Team.captain_id]", cascade="all")
    main_gender_id = Column(Integer, ForeignKey("genders.id"), nullable=True)
    main_gender = relationship("Gender", back_populates="gender_of_athlets", foreign_keys=[main_gender_id])
    main_citizenship_id = Column(Integer, ForeignKey("citizenships.id"), nullable=True)
    main_citizenship = relationship("Citizenship", back_populates="citizenship_of_athlets", foreign_keys=[main_citizenship_id])
    main_occupation_id = Column(Integer, ForeignKey("occupations.id"), nullable=True)
    main_occupation = relationship("Occupation", back_populates="occupation_of_athlets", foreign_keys=[main_occupation_id])

    def __init__(self, 
                session: Session,
                name: str,
                dob: str,
                dod: str|None,
                WID: str,
                genders, citizenships, occupations):
        self.wiki_id = WID
        self.name = name
        self.date_of_birth = self.parse_date(dob)
        self.date_of_death = self.parse_date(dod)
        session.add(self)
        if genders:
            self.main_gender = Gender.get_or_create(session, genders[0][0], genders[0][1])
            for g_id, g_name in genders:
                self.genders.append(Gender.get_or_create(session, g_id, g_name))
        if citizenships:
            self.main_citizenship = Citizenship.get_or_create(session, citizenships[0][0], citizenships[0][1])
            for c_id, c_name in citizenships:
                self.citizenships.append(Citizenship.get_or_create(session, c_id, c_name))
        if occupations:
            self.main_occupation = Occupation.get_or_create(session, occupations[0][0], occupations[0][1])
            for o_id, o_name in occupations:
                self.occupations.append(Occupation.get_or_create(session, o_id, o_name))
        
    @staticmethod
    def get_or_create(session: Session,
                name: str,
                dob: str,
                dod: str|None,
                WID: str,
                genders, citizenships, occupations):
        athlet = session.query(Athlet).filter_by(wiki_id=WID).one_or_none()
        if not athlet:
            athlet = Athlet(
                session=session,
                name=name,
                dob=dob,
                dod=dod,
                WID=WID,
                genders=genders,
                citizenships=citizenships,
                occupations=occupations)
            session.add(athlet)
        else:
            # Update values
            athlet.date_of_death = Athlet.parse_date(dod)
            if genders:
                athlet.genders = []
                athlet.main_gender = Gender.get_or_create(session, genders[0][0], genders[0][1])
                for g_id, g_name in genders:
                    athlet.genders.append(Gender.get_or_create(session, g_id, g_name))
            if citizenships:
                athlet.citizenships = []
                athlet.main_citizenship = Citizenship.get_or_create(session, citizenships[0][0], citizenships[0][1])
                for c_id, c_name in citizenships:
                    athlet.citizenships.append(Citizenship.get_or_create(session, c_id, c_name))
            if occupations:
                athlet.occupations = []
                athlet.main_occupation = Occupation.get_or_create(session, occupations[0][0], occupations[0][1])
                for o_id, o_name in occupations:
                    athlet.occupations.append(Occupation.get_or_create(session, o_id, o_name))
            session.add(athlet)
        return athlet

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

    # Properties and methods
    @property
    def url(self) -> str:
        return f"{WIKIDATA_URL}{self.wiki_id}"

    @property
    def name_escaped_html(self) -> str:
        return escape(self.name)

    @property
    def is_dead(self) -> bool:
        return self.date_of_death is not None
    @property
    def age(self) -> int:
        recent_date = dt.datetime.now().date()
        if self.is_dead and self.date_of_death:
            recent_date = self.date_of_death
        return self.calculate_age(self.date_of_birth, recent_date)

    @property
    def gonzales(self) -> bool:
        return self.is_dead and self.date_of_death and self.date_of_death.month == 1

    @property
    def cesarini(self) -> bool:
        return self.is_dead and self.date_of_death and self.date_of_death.month == 12 and self.date_of_death.day >= 25

    @property
    def club27(self) -> bool:
        return self.age == 27

    @property
    def birthday(self) -> bool:
        return (
            self.is_dead and 
            self.date_of_death and 
            self.month_and_day(self.date_of_death) == self.month_and_day(self.date_of_birth)
        )

    @property
    def score(self) -> int:
        return self.calculate_score()

    @property
    def theoretical_score(self) -> int:
        return self.calculate_theoretical_score()

    @staticmethod
    def calculate_age(date1: dt.date, date2: dt.date) -> int:
        years = date2.year - date1.year
        months = date2.month - date1.month
        days = date2.day - date1.day
        age = years - 1
        if months >= 0 and days >= 0:
            age += 1
        return age

    @staticmethod
    def month_and_day(date: dt.date):
        return (date.month, date.day)
    
    @staticmethod
    def parse_date(date) -> dt.date|None:
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
        if self.is_banned or not self.is_dead:
            return 0
        return self.theoretical_score

    def update_from_other(self, other) -> None:
        if not isinstance(other, Athlet):
            return
        self.date_of_birth = other.date_of_birth
        self.date_of_death = other.date_of_death
        self.occupations = other.occupations
        self.genders = other.genders
        self.citizenships = other.citizenships

    def get_description(self) -> str:
        gender_desc = (
            "No gender" if not self.genders 
            else f"<u>{escape(self.genders[0].name)}</u>" + (f", {escape(', '.join(x.name for x in self.genders[1:]))}" if len(self.genders) > 1 else "")
        )
        citizenship_desc = (
            "No citizenship" if not self.citizenships 
            else f"<u>{escape(self.citizenships[0].name)}</u>" + (f", {escape(', '.join(x.name for x in self.citizenships[1:]))}" if len(self.citizenships) > 1 else "")
        )
        occupation_desc = (
            "No occupation" if not self.occupations 
            else f"<u>{escape(self.occupations[0].name)}</u>" + (f", {escape(', '.join(x.name for x in self.occupations[1:]))}" if len(self.occupations) > 1 else "")
        )
        desc = (
            f"<a href=\"{self.url}\">{self.name_escaped_html}</a> ({gender_desc}) "
            f"a famous {occupation_desc}. Born on {self.date_of_birth} ({self.age} years), "
            f"holds the passport of {citizenship_desc}.\n"
            f"In the event of a tragic fatality he will bring {self.theoretical_score} points to the team.\n"
        )
        return desc


