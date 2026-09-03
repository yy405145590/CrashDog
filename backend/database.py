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
    # create_all 不会给已存在的表补索引，这里显式创建（幂等）。
    _new_indexes = [
        ("ix_crash_upload_time", "crash_reports", "upload_time"),
        ("ix_crash_game_name", "crash_reports", "game_name"),
        ("ix_crash_platform", "crash_reports", "platform"),
        ("ix_crash_status", "crash_reports", "status"),
        ("ix_crash_symbol_package_id", "crash_reports", "symbol_package_id"),
        ("ix_symbol_game_name", "symbol_packages", "game_name"),
        ("ix_symbol_platform", "symbol_packages", "platform"),
        ("ix_symbol_upload_time", "symbol_packages", "upload_time"),
        ("ix_symbol_guid_package_id", "symbol_guids", "symbol_package_id"),
    ]
    with engine.begin() as conn:
        for name, table, column in _new_indexes:
            conn.execute(text(
                f'CREATE INDEX IF NOT EXISTS "{name}" ON "{table}" ("{column}")'
            ))
    logger.info("Database initialized")
