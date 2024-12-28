from html import escape
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Table, create_engine
from sqlalchemy.orm import relationship, declarative_base

from telegram import User as TgUser

from .db import Base
from .utils import mention_user

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=False)
    mention = Column(String, nullable=False)
    superuser = Column(Boolean, nullable=False, default=False)

    # One-to-many relationships
    teams = relationship("Team", back_populates="owner", foreign_keys="[Team.owner_id]", cascade="all, delete-orphan")
    games = relationship("Game", back_populates="creator", foreign_keys="[Game.creator_id]", cascade="all, delete-orphan")

    # def __init__(self, telegram_user:TgUser):
    #     self.telegram_id = telegram_user.id
    #     self.name = telegram_user.first_name
    #     self.mention = mention_user(telegram_user)
    #     self.superuser = False
    
    def __str__(self):
        return self.name

    @staticmethod
    def get_or_create_user(telegram_user, session):
        user = session.query(User).filter_by(telegram_id=telegram_user.id).one_or_none()
        if not user:
            user = User(telegram_user)
            session.add(user)
        return user