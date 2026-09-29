"""Engine and session factory. Callers outside this package use CoreRepository."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core_db.models import Base


def make_engine(database_url: str):
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url)


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = make_engine(database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def create_schema(database_url: str) -> sessionmaker[Session]:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
