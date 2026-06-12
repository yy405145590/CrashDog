from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CrashSummary(BaseModel):
    id: str
    upload_time: datetime
    status: str
    game_name: Optional[str] = None
    build_version: Optional[str] = None
    error_message: Optional[str] = None
    crash_type: Optional[str] = None
    crashed_thread: Optional[str] = None
    platform: Optional[str] = None
    symbol_package_id: Optional[str] = None

    model_config = {"from_attributes": True}


class CrashDetail(CrashSummary):
    engine_version: Optional[str] = None
    svn_revision: Optional[str] = None
    raw_callstack: Optional[str] = None
    symbolicated_callstack: Optional[str] = None
    crash_context_json: Optional[str] = None
    log_content: Optional[str] = None
    log_tail: Optional[str] = None
    source_dir: Optional[str] = None
    symbol_package_id: Optional[str] = None
    module_guids: list[GuidEntry] = []
    symbol_matches: list[SymbolMatchEntry] = []
    analyses: list[AnalysisResponse] = []


class AnalysisResponse(BaseModel):
    id: int
    crash_id: str
    agent_type: str
    raw_response: Optional[str] = None
    root_cause: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[int] = None
    fix_suggestion: Optional[str] = None
    source_references: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyzeRequest(BaseModel):
    agent_type: Optional[str] = None


class StatusResponse(BaseModel):
    status: str


class GuidEntry(BaseModel):
    guid: str
    age: Optional[int] = None
    pdb_filename: Optional[str] = None
    source_file: Optional[str] = None
    module_name: Optional[str] = None


class SymbolMatchEntry(BaseModel):
    symbol_package_id: str
    store_path: str
    game_name: Optional[str] = None
    build_version: Optional[str] = None
    platform: Optional[str] = None
    score: int = 0
    matched_guid_count: int = 0
    matched_modules: list[GuidEntry] = []


class SymbolFileEntry(BaseModel):
    name: str
    size: int


class SymbolPackageSummary(BaseModel):
    id: str
    game_name: Optional[str] = None
    build_version: Optional[str] = None
    svn_revision: Optional[str] = None
    platform: str
    file_size: Optional[int] = None
    status: str
    upload_time: datetime
    description: Optional[str] = None
    linked_crash_count: int = 0
    guid_count: int = 0

    model_config = {"from_attributes": True}


class SymbolPackageDetail(SymbolPackageSummary):
    store_path: str
    file_list: Optional[list[SymbolFileEntry]] = None
    guids: list[GuidEntry] = []

    model_config = {"from_attributes": True}


class SymbolListResponse(BaseModel):
    total: int
    items: list[SymbolPackageSummary]
