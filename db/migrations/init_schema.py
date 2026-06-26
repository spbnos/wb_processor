"""
Run once to initialize the database:
    python db/migrations/init_schema.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.database import engine, Base
from db import models  # noqa — side-effect: registers all models


def run():
    print("[migration] Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("[migration] Done.")

    # Print created tables
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"[migration] Tables in DB: {tables}")


if __name__ == "__main__":
    run()
