import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session, defer

from .. import config
from ..database import get_db
from ..models import CrashReport
from ..schemas import CrashDetail, CrashListResponse, CrashSummary, CrashUpdateRequest, GuidEntry, StatusResponse, SymbolMatchEntry
from ..services.crash_parser import extract_zip, parse_crash_directory
from ..services.guid_extractor import extract_guids_from_dmp
from ..services.symbolizer import find_symbol_package_matches, resolve_pdb_path, symbolicate_minidump

router = APIRouter(prefix="/api/crashes", tags=["crashes"])
logger = logging.getLogger(__name__)


def _normalize_resolution_status(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip().lower()
    # 兼容中文输入
    if v in ("已解决", "resolved", "solved", "done"):
        return "resolved"
    if v in ("未解决", "unresolved", "open", "pending"):
        return "unresolved"
    return None


@router.post("/upload", response_model=CrashSummary)
async def upload_crash(
    file: UploadFile,
    remark: str | None = Form(default=None),
    resolution_status: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 .zip 文件")

    normalized_resolution = _normalize_resolution_status(resolution_status) if resolution_status else None
    if resolution_status and normalized_resolution is None:
        raise HTTPException(400, "resolution_status 仅支持 unresolved(未解决)/resolved(已解决)")
    if remark is not None:
        remark = remark.strip() or None
        if remark and len(remark) > 2000:
            raise HTTPException(400, "备注过长，最多 2000 字符")

    logger.info("Crash upload started: filename=%s", file.filename)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    config.CRASH_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = config.UPLOAD_DIR / file.filename
    with open(zip_path, "wb") as f:
        content = await file.read()
        f.write(content)
    logger.info("Crash upload saved: filename=%s bytes=%s path=%s", file.filename, len(content), zip_path)

    try:
        extract_dir = extract_zip(zip_path, config.CRASH_DIR)
    except ValueError as e:
        logger.warning("Crash zip rejected: filename=%s reason=%s", file.filename, e)
        zip_path.unlink(missing_ok=True)
        raise HTTPException(400, str(e))

    try:
        parsed = parse_crash_directory(extract_dir)
    except Exception as e:
        logger.exception("Crash parse failed: filename=%s extract_dir=%s", file.filename, extract_dir)
        raise HTTPException(500, f"解析崩溃数据失败: {e}")

    logger.info(
        "Crash parsed: id=%s game=%s build=%s platform=%s has_minidump=%s",
        parsed.get("id"),
        parsed.get("game_name"),
        parsed.get("build_version"),
        parsed.get("platform"),
        parsed.get("has_minidump"),
    )

    existing = db.query(CrashReport).filter_by(id=parsed["id"]).first()
    if existing:
        db.delete(existing)
        db.flush()

    module_guids = []
    if parsed.get("has_minidump") and parsed.get("minidump_path"):
        guid_infos = extract_guids_from_dmp(parsed["minidump_path"])
        module_guids = [
            {
                "guid": gi.guid,
                "age": gi.age,
                "pdb_filename": gi.pdb_filename,
                "module_name": gi.source_file,
            }
            for gi in guid_infos
        ]

    crash = CrashReport(
        id=parsed["id"],
        status="parsed",
        resolution_status=normalized_resolution or "unresolved",
        remark=remark,
        game_name=parsed["game_name"],
        build_version=parsed["build_version"],
        platform=parsed["platform"],
        engine_version=parsed["engine_version"],
        error_message=parsed["error_message"],
        crash_type=parsed["crash_type"],
        crashed_thread=parsed["crashed_thread"],
        raw_callstack=parsed["raw_callstack"],
        crash_context_json=parsed["crash_context_json"],
        log_content=parsed["log_content"],
        log_tail=parsed["log_tail"],
        zip_path=str(zip_path),
        extract_dir=str(extract_dir),
        module_guids_json=json.dumps(module_guids, ensure_ascii=False) if module_guids else None,
    )

    if module_guids:
        pdb_path, sym_pkg_id = resolve_pdb_path(module_guids, db)
        logger.info(
            "Crash symbolication started: crash_id=%s module_guid_count=%s pdb_path=%s symbol_package_id=%s",
            parsed["id"],
            len(module_guids),
            pdb_path,
            sym_pkg_id,
        )
        sym_result = symbolicate_minidump(parsed["minidump_path"], pdb_search_path=pdb_path)
        if sym_result:
            crash.symbolicated_callstack = sym_result
            crash.symbol_package_id = sym_pkg_id
            logger.info("Crash symbolication finished: crash_id=%s result_chars=%s", parsed["id"], len(sym_result))
        else:
            logger.warning("Crash symbolication returned no result: crash_id=%s", parsed["id"])

    db.add(crash)
    db.commit()
    db.refresh(crash)
    logger.info("Crash upload completed: crash_id=%s", crash.id)
    return crash


@router.get("", response_model=CrashListResponse)
def list_crashes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    game_name: str | None = None,
    platform: str | None = None,
    status: str | None = None,
    resolution_status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    # 只查列表需要的轻量列：延迟加载 log/调用栈等大 TEXT 字段，
    # 否则每条记录几十 MB 的 log_content 都会被 SQLite 读进内存。
    base = db.query(CrashReport).options(
        defer(CrashReport.raw_callstack),
        defer(CrashReport.symbolicated_callstack),
        defer(CrashReport.crash_context_json),
        defer(CrashReport.log_content),
        defer(CrashReport.log_tail),
        defer(CrashReport.module_guids_json),
    )
    if game_name:
        base = base.filter(CrashReport.game_name == game_name)
    if platform:
        base = base.filter(CrashReport.platform == platform)
    if status:
        base = base.filter(CrashReport.status == status)
    if resolution_status:
        normalized = _normalize_resolution_status(resolution_status)
        if normalized is None:
            raise HTTPException(400, "resolution_status 仅支持 unresolved(未解决)/resolved(已解决)")
        base = base.filter(CrashReport.resolution_status == normalized)
    if search:
        like = f"%{search}%"
        base = base.filter(
            or_(
                CrashReport.id.like(like),
                CrashReport.error_message.like(like),
                CrashReport.build_version.like(like),
                CrashReport.crashed_thread.like(like),
                CrashReport.remark.like(like),
            )
        )
    total = base.order_by(None).count()
    items = (
        base.order_by(CrashReport.upload_time.desc(), CrashReport.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CrashListResponse(total=total, items=items)


@router.get("/{crash_id}", response_model=CrashDetail)
def get_crash(crash_id: str, db: Session = Depends(get_db)):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")

    raw_module_guids = []
    module_guids = []
    if crash.module_guids_json:
        try:
            raw_module_guids = json.loads(crash.module_guids_json)
            module_guids = [GuidEntry(**g) for g in raw_module_guids]
        except (json.JSONDecodeError, TypeError):
            pass

    detail = CrashDetail.model_validate(crash)
    detail.module_guids = module_guids
    detail.symbol_matches = [
        SymbolMatchEntry(**match)
        for match in find_symbol_package_matches(raw_module_guids, db)
    ]
    return detail


@router.patch("/{crash_id}", response_model=CrashDetail)
def update_crash(crash_id: str, payload: CrashUpdateRequest, db: Session = Depends(get_db)):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")

    updated_fields = payload.model_fields_set
    if not updated_fields:
        raise HTTPException(400, "没有可更新的字段")

    if "remark" in updated_fields:
        remark = payload.remark.strip() if payload.remark else None
        if remark and len(remark) > 2000:
            raise HTTPException(400, "备注过长，最多 2000 字符")
        crash.remark = remark or None

    if "resolution_status" in updated_fields:
        normalized = _normalize_resolution_status(payload.resolution_status) if payload.resolution_status else None
        if normalized is None:
            raise HTTPException(400, "resolution_status 仅支持 unresolved(未解决)/resolved(已解决)")
        crash.resolution_status = normalized

    db.commit()
    db.refresh(crash)
    logger.info("Crash updated: crash_id=%s fields=%s", crash_id, sorted(updated_fields))
    # 复用详情组装逻辑，保证返回 module_guids / symbol_matches
    return get_crash(crash_id, db)


@router.get("/{crash_id}/status", response_model=StatusResponse)
def get_status(crash_id: str, db: Session = Depends(get_db)):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")
    return StatusResponse(status=crash.status)


@router.delete("/{crash_id}")
def delete_crash(crash_id: str, db: Session = Depends(get_db)):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")

    logger.info("Deleting crash: crash_id=%s", crash_id)
    if crash.extract_dir:
        p = Path(crash.extract_dir)
        if p.exists():
            shutil.rmtree(p)
    if crash.zip_path:
        Path(crash.zip_path).unlink(missing_ok=True)

    db.delete(crash)
    db.commit()
    logger.info("Crash deleted: crash_id=%s", crash_id)
    return {"detail": "已删除"}


@router.post("/{crash_id}/resymbolicate")
def resymbolicate(
    crash_id: str,
    symbol_package_id: str | None = None,
    db: Session = Depends(get_db),
):
    from ..models import SymbolPackage

    logger.info("Crash resymbolication requested: crash_id=%s symbol_package_id=%s", crash_id, symbol_package_id)
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")

    if not crash.extract_dir:
        raise HTTPException(400, "该崩溃缺少解压目录，无法重新符号化")

    extract = Path(crash.extract_dir)
    dmp_files = list(extract.glob("*.dmp"))
    if not dmp_files:
        raise HTTPException(400, "该崩溃无 minidump 文件")

    if symbol_package_id:
        sym = db.query(SymbolPackage).filter_by(id=symbol_package_id).first()
        if not sym:
            raise HTTPException(404, "指定的符号包不存在")
        if sym.status != "ready":
            raise HTTPException(400, "符号包状态非就绪")
        pdb_path = sym.store_path
        pkg_id = sym.id
    else:
        module_guids = []
        if crash.module_guids_json:
            try:
                module_guids = json.loads(crash.module_guids_json)
            except (json.JSONDecodeError, TypeError):
                pass

        if not module_guids:
            guid_infos = extract_guids_from_dmp(str(dmp_files[0]))
            module_guids = [
                {"guid": gi.guid, "age": gi.age,
                 "pdb_filename": gi.pdb_filename, "module_name": gi.source_file}
                for gi in guid_infos
            ]
            crash.module_guids_json = json.dumps(module_guids, ensure_ascii=False)

        pdb_path, pkg_id = resolve_pdb_path(module_guids, db)

    result = symbolicate_minidump(str(dmp_files[0]), pdb_search_path=pdb_path)
    if result:
        crash.symbolicated_callstack = result
        crash.symbol_package_id = pkg_id
        db.commit()
        logger.info("Crash resymbolication completed: crash_id=%s symbol_package_id=%s", crash_id, pkg_id)
        return {
            "detail": "重新符号化完成",
            "symbol_package_id": pkg_id,
            "symbolicated_callstack": result,
        }
    else:
        logger.warning("Crash resymbolication failed with empty CDB result: crash_id=%s pdb_path=%s", crash_id, pdb_path)
        raise HTTPException(500, "符号化失败，CDB 未返回结果")
