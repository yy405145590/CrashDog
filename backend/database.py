import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from . import config


logger = logging.getLogger(__name__)

engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    logger.info("Initializing database: %s", config.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    columns = [c["name"] for c in insp.get_columns("crash_reports")]
    if "symbol_package_id" not in columns:
        logger.info("Migrating database: add crash_reports.symbol_package_id")
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE crash_reports ADD COLUMN symbol_package_id TEXT REFERENCES symbol_packages(id)"
            ))
    if "module_guids_json" not in columns:
        logger.info("Migrating database: add crash_reports.module_guids_json")
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE crash_reports ADD COLUMN module_guids_json TEXT"
            ))
    logger.info("Database initialized")
