import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal, get_db
from ..models import AnalysisReport, CrashReport
from ..schemas import AnalysisResponse, AnalyzeRequest
from ..services.agents.base import AnalysisResult, CrashAnalysisInput
from ..services.agents.factory import get_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crashes", tags=["analysis"])


def _build_crash_info(crash: CrashReport) -> CrashAnalysisInput:
    return CrashAnalysisInput(
        crash_id=crash.id,
        game_name=crash.game_name or "",
        engine_version=crash.engine_version or "",
        build_version=crash.build_version or "",
        crash_type=crash.crash_type or "",
        error_message=crash.error_message or "",
        crashed_thread=crash.crashed_thread or "",
        raw_callstack=crash.raw_callstack or "",
        symbolicated_callstack=crash.symbolicated_callstack or "",
        crash_context_summary=crash.crash_context_json or "",
        log_tail=crash.log_tail or "",
        source_dir=crash.source_dir,
        svn_revision=crash.svn_revision,
    )


def _save_report(crash_id: str, agent_type: str, result: AnalysisResult, db: Session) -> AnalysisReport:
    source_refs_str = None
    if result.source_references:
        source_refs_str = json.dumps(result.source_references, ensure_ascii=False)

    report = AnalysisReport(
        crash_id=crash_id,
        agent_type=agent_type,
        raw_response=result.raw_response,
        root_cause=result.root_cause,
        severity=result.severity,
        confidence=result.confidence,
        fix_suggestion=result.fix_suggestion,
        source_references=source_refs_str,
    )
    db.add(report)
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if crash:
        crash.status = "analyzed"
    db.commit()
    db.refresh(report)
    return report


def _run_analysis_background(crash_id: str, agent_type_name: str, crash_info: CrashAnalysisInput):
    db = SessionLocal()
    try:
        agent = get_agent(agent_type_name)
        result = agent.analyze(crash_info)
        _save_report(crash_id, agent.agent_type(), result, db)
    except Exception as e:
        logger.exception("Background analysis failed for crash %s", crash_id)
        crash = db.query(CrashReport).filter_by(id=crash_id).first()
        if crash:
            crash.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/{crash_id}/analyze")
def trigger_analysis(
    crash_id: str,
    req: AnalyzeRequest | None = None,
    db: Session = Depends(get_db),
):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")

    if crash.status == "analyzing":
        raise HTTPException(409, "该崩溃正在分析中，请勿重复提交")

    agent_type = req.agent_type if req else None
    try:
        agent = get_agent(agent_type)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not agent.is_available():
        raise HTTPException(503, f"Agent '{agent.agent_type()}' 不可用，请检查是否已安装")

    crash.status = "analyzing"
    db.commit()

    crash_info = _build_crash_info(crash)

    thread = threading.Thread(
        target=_run_analysis_background,
        args=(crash.id, agent_type, crash_info),
        daemon=True,
    )
    thread.start()

    return {"status": "analyzing"}


@router.get("/{crash_id}/log")
def get_analysis_log(crash_id: str, offset: int = 0):
    log_file = config.TEMP_DIR / crash_id / "copilot_log.txt"
    if not log_file.exists():
        return {"content": "", "offset": 0}

    with open(log_file, "rb") as f:
        f.seek(offset)
        data = f.read()
    content = data.decode("utf-8", errors="replace")
    return {"content": content, "offset": offset + len(data)}


@router.get("/{crash_id}/analysis", response_model=list[AnalysisResponse])
def get_analyses(crash_id: str, db: Session = Depends(get_db)):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")
    return crash.analyses
