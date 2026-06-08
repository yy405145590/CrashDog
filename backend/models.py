from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class CrashReport(Base):
    __tablename__ = "crash_reports"

    id = Column(String, primary_key=True)
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="uploaded")
    game_name = Column(String, nullable=True)
    build_version = Column(String, nullable=True)
    svn_revision = Column(String, nullable=True)
    platform = Column(String, nullable=True)
    engine_version = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    crash_type = Column(String, nullable=True)
    crashed_thread = Column(String, nullable=True)
    raw_callstack = Column(Text, nullable=True)
    symbolicated_callstack = Column(Text, nullable=True)
    crash_context_json = Column(Text, nullable=True)
    log_content = Column(Text, nullable=True)
    log_tail = Column(Text, nullable=True)
    source_dir = Column(String, nullable=True)
    zip_path = Column(String, nullable=True)
    extract_dir = Column(String, nullable=True)
    symbol_package_id = Column(String, ForeignKey("symbol_packages.id"), nullable=True)
    module_guids_json = Column(Text, nullable=True)

    analyses = relationship("AnalysisReport", back_populates="crash", cascade="all, delete-orphan")
    symbol_package = relationship("SymbolPackage", back_populates="crash_reports")


class SymbolPackage(Base):
    __tablename__ = "symbol_packages"
    __table_args__ = (
        UniqueConstraint("game_name", "build_version", "platform", name="uq_symbol_version"),
    )

    id = Column(String, primary_key=True)
    game_name = Column(String, nullable=True, default="")
    build_version = Column(String, nullable=True, default="")
    svn_revision = Column(String, nullable=True)
    platform = Column(String, nullable=False, default="Windows")
    description = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_list = Column(Text, nullable=True)
    store_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="uploading")
    upload_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    crash_reports = relationship("CrashReport", back_populates="symbol_package")
    guids = relationship("SymbolGuid", back_populates="symbol_package", cascade="all, delete-orphan")


class SymbolGuid(Base):
    __tablename__ = "symbol_guids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol_package_id = Column(String, ForeignKey("symbol_packages.id"), nullable=False)
    guid = Column(String(32), nullable=False, index=True)
    age = Column(Integer, nullable=True)
    pdb_filename = Column(String, nullable=True)
    source_file = Column(String, nullable=True)

    symbol_package = relationship("SymbolPackage", back_populates="guids")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    crash_id = Column(String, ForeignKey("crash_reports.id"), nullable=False)
    agent_type = Column(String, nullable=False)
    raw_response = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    severity = Column(String, nullable=True)
    confidence = Column(Integer, nullable=True)
    fix_suggestion = Column(Text, nullable=True)
    source_references = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    crash = relationship("CrashReport", back_populates="analyses")
