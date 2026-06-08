import json
import shutil
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..models import CrashReport, SymbolGuid, SymbolPackage
from ..schemas import (
    GuidEntry,
    SymbolFileEntry,
    SymbolListResponse,
    SymbolPackageDetail,
    SymbolPackageSummary,
)
from ..services.guid_extractor import scan_directory_for_guids

router = APIRouter(prefix="/api/symbols", tags=["symbols"])


@router.post("/upload", response_model=SymbolPackageSummary)
async def upload_symbol(
    file: UploadFile,
    game_name: str = Form(""),
    build_version: str = Form(""),
    platform: str = Form("Windows"),
    svn_revision: str | None = Form(None),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(400, "请上传 .zip 文件")

    for val in (game_name, build_version):
        if any(c in val for c in ("/", "\\", "..")):
            raise HTTPException(400, "名称中不能包含路径分隔符")

    sym_id = "sym_" + uuid.uuid4().hex[:12]
    if game_name and build_version:
        store_dir = config.SYMBOL_DIR / game_name / build_version
    else:
        store_dir = config.SYMBOL_DIR / sym_id

    sym = SymbolPackage(
        id=sym_id,
        game_name=game_name,
        build_version=build_version,
        svn_revision=svn_revision,
        platform=platform,
        description=description,
        store_path=str(store_dir),
        status="uploading",
    )
    db.add(sym)
    db.commit()

    config.SYMBOL_DIR.mkdir(parents=True, exist_ok=True)
    temp_zip = config.SYMBOL_DIR / f"_tmp_{sym_id}.zip"

    try:
        with open(temp_zip, "wb") as f:
            while chunk := await file.read(8 * 1024 * 1024):
                f.write(chunk)

        store_dir.mkdir(parents=True, exist_ok=True)
        file_entries = []
        total_size = 0
        with zipfile.ZipFile(temp_zip, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                target = (store_dir / info.filename).resolve()
                if not str(target).startswith(str(store_dir.resolve())):
                    raise ValueError("ZIP 包含非法路径")
                target.parent.mkdir(parents=True, exist_ok=True)
                zf.extract(info, store_dir)
                file_entries.append({"name": info.filename, "size": info.file_size})
                total_size += info.file_size

        guid_infos = scan_directory_for_guids(store_dir)

        if guid_infos:
            existing_guid_values = [gi.guid for gi in guid_infos]
            existing = db.query(SymbolGuid).filter(
                SymbolGuid.guid.in_(existing_guid_values),
                SymbolGuid.symbol_package_id != sym_id,
            ).first()
            if existing:
                old_pkg = db.query(SymbolPackage).filter_by(id=existing.symbol_package_id).first()
                if old_pkg:
                    old_path = Path(old_pkg.store_path)
                    if old_path.exists():
                        shutil.rmtree(old_path)
                    db.delete(old_pkg)
                    db.flush()

        for gi in guid_infos:
            db.add(SymbolGuid(
                symbol_package_id=sym_id,
                guid=gi.guid,
                age=gi.age,
                pdb_filename=gi.pdb_filename,
                source_file=gi.source_file,
            ))

        sym.file_size = total_size
        sym.file_list = json.dumps(file_entries, ensure_ascii=False)
        sym.status = "ready"
        db.commit()
        db.refresh(sym)
    except Exception as e:
        sym.status = "failed"
        db.commit()
        if store_dir.exists():
            shutil.rmtree(store_dir)
        raise HTTPException(500, f"处理符号包失败: {e}")
    finally:
        temp_zip.unlink(missing_ok=True)

    return SymbolPackageSummary(
        id=sym.id,
        game_name=sym.game_name,
        build_version=sym.build_version,
        svn_revision=sym.svn_revision,
        platform=sym.platform,
        file_size=sym.file_size,
        status=sym.status,
        upload_time=sym.upload_time,
        description=sym.description,
        linked_crash_count=0,
        guid_count=len(guid_infos),
    )


@router.get("", response_model=SymbolListResponse)
def list_symbols(
    game_name: str | None = None,
    platform: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(SymbolPackage)
    if game_name:
        query = query.filter_by(game_name=game_name)
    if platform:
        query = query.filter_by(platform=platform)
    if search:
        query = query.filter(
            or_(
                SymbolPackage.build_version.contains(search),
                SymbolPackage.svn_revision.contains(search),
            )
        )
    symbols = query.order_by(SymbolPackage.upload_time.desc()).all()

    items = []
    for sym in symbols:
        count = db.query(CrashReport).filter_by(symbol_package_id=sym.id).count()
        items.append(SymbolPackageSummary(
            id=sym.id,
            game_name=sym.game_name,
            build_version=sym.build_version,
            svn_revision=sym.svn_revision,
            platform=sym.platform,
            file_size=sym.file_size,
            status=sym.status,
            upload_time=sym.upload_time,
            description=sym.description,
            linked_crash_count=count,
            guid_count=len(sym.guids),
        ))

    return SymbolListResponse(total=len(items), items=items)


@router.get("/{symbol_id}", response_model=SymbolPackageDetail)
def get_symbol(symbol_id: str, db: Session = Depends(get_db)):
    sym = db.query(SymbolPackage).filter_by(id=symbol_id).first()
    if not sym:
        raise HTTPException(404, "符号包不存在")

    count = db.query(CrashReport).filter_by(symbol_package_id=sym.id).count()
    file_list = None
    if sym.file_list:
        try:
            raw = json.loads(sym.file_list)
            file_list = [SymbolFileEntry(**f) for f in raw]
        except (json.JSONDecodeError, TypeError):
            pass

    guids = [
        GuidEntry(guid=sg.guid, age=sg.age, pdb_filename=sg.pdb_filename, source_file=sg.source_file)
        for sg in sym.guids
    ]

    return SymbolPackageDetail(
        id=sym.id,
        game_name=sym.game_name,
        build_version=sym.build_version,
        svn_revision=sym.svn_revision,
        platform=sym.platform,
        file_size=sym.file_size,
        status=sym.status,
        upload_time=sym.upload_time,
        description=sym.description,
        store_path=sym.store_path,
        file_list=file_list,
        linked_crash_count=count,
        guid_count=len(sym.guids),
        guids=guids,
    )


@router.delete("/{symbol_id}")
def delete_symbol(symbol_id: str, db: Session = Depends(get_db)):
    sym = db.query(SymbolPackage).filter_by(id=symbol_id).first()
    if not sym:
        raise HTTPException(404, "符号包不存在")

    active = db.query(CrashReport).filter_by(
        symbol_package_id=sym.id, status="analyzing"
    ).count()
    if active > 0:
        raise HTTPException(409, "该符号包正在被使用，无法删除")

    db.query(CrashReport).filter_by(symbol_package_id=sym.id).update(
        {"symbol_package_id": None}
    )

    store = Path(sym.store_path)
    if store.exists():
        shutil.rmtree(store)

    db.delete(sym)
    db.commit()
    return {"detail": "符号包已删除"}
