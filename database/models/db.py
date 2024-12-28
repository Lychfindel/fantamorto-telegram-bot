from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# DATABASE_URL = "postgresql://postgres:postgres@localhost:5432"
DATABASE_URL = "sqlite:///fantamorto.db"

# Database engine
engine = create_engine(DATABASE_URL)

# Session maker
SessionLocal: Session = sessionmaker(bind=engine, expire_on_commit=False)

# Base for models
Base = declarative_base()