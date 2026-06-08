import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import CrashReport
from ..schemas import CrashDetail, CrashSummary, GuidEntry, StatusResponse
from ..services.crash_parser import extract_zip, parse_crash_directory
from ..services.guid_extractor import extract_guids_from_dmp
from ..services.symbolizer import resolve_pdb_path, symbolicate_minidump

router = APIRouter(prefix="/api/crashes", tags=["crashes"])


@router.post("/upload", response_model=CrashSummary)
async def upload_crash(file: UploadFile, db: Session = Depends(get_db)):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 .zip 文件")

    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    config.CRASH_DIR.mkdir(parents=True, exist_ok=True)

    zip_path = config.UPLOAD_DIR / file.filename
    with open(zip_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        extract_dir = extract_zip(zip_path, config.CRASH_DIR)
    except ValueError as e:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(400, str(e))

    try:
        parsed = parse_crash_directory(extract_dir)
    except Exception as e:
        raise HTTPException(500, f"解析崩溃数据失败: {e}")

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
        sym_result = symbolicate_minidump(parsed["minidump_path"], pdb_search_path=pdb_path)
        if sym_result:
            crash.symbolicated_callstack = sym_result
            crash.symbol_package_id = sym_pkg_id

    db.add(crash)
    db.commit()
    db.refresh(crash)
    return crash


@router.get("", response_model=list[CrashSummary])
def list_crashes(db: Session = Depends(get_db)):
    return db.query(CrashReport).order_by(CrashReport.upload_time.desc()).all()


@router.get("/{crash_id}", response_model=CrashDetail)
def get_crash(crash_id: str, db: Session = Depends(get_db)):
    crash = db.query(CrashReport).filter_by(id=crash_id).first()
    if not crash:
        raise HTTPException(404, "崩溃记录不存在")

    module_guids = []
    if crash.module_guids_json:
        try:
            raw = json.loads(crash.module_guids_json)
            module_guids = [GuidEntry(**g) for g in raw]
        except (json.JSONDecodeError, TypeError):
            pass

    detail = CrashDetail.model_validate(crash)
    detail.module_guids = module_guids
    return detail


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

    if crash.extract_dir:
        p = Path(crash.extract_dir)
        if p.exists():
            shutil.rmtree(p)
    if crash.zip_path:
        Path(crash.zip_path).unlink(missing_ok=True)

    db.delete(crash)
    db.commit()
    return {"detail": "已删除"}


@router.post("/{crash_id}/resymbolicate")
def resymbolicate(
    crash_id: str,
    symbol_package_id: str | None = None,
    db: Session = Depends(get_db),
):
    from ..models import SymbolPackage

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
        return {
            "detail": "重新符号化完成",
            "symbol_package_id": pkg_id,
            "symbolicated_callstack": result,
        }
    else:
        raise HTTPException(500, "符号化失败，CDB 未返回结果")
