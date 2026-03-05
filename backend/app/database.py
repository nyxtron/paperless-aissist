from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy.pool import StaticPool
from contextlib import contextmanager
from typing import Generator
import os
import pathlib

data_dir = os.environ.get("DATA_DIR", "/app/data")
pathlib.Path(data_dir).mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{data_dir}/paperless-aissist.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_db():
    with Session(engine) as session:
        yield session
