"""Database connection. Every other file gets a DB session from here."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# check_same_thread=False is needed only for SQLite with FastAPI
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """All database tables (models) inherit from this."""
    pass


def get_db():
    """Gives a DB session to an API endpoint and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
