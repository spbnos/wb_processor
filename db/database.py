import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

_engine = None
_SessionLocal = None

def _get_database_url():
    from config.settings import DATABASE_URL
    return DATABASE_URL

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _get_database_url(),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    return _engine

def SessionLocal():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from db import models  # noqa
    Base.metadata.create_all(bind=get_engine())
    print("[DB] Tables created / verified.")
