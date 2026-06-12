import logging
import re
import subprocess
from pathlib import Path

from .. import config


logger = logging.getLogger(__name__)


def _build_cdb_command() -> str:
    return "; ".join([
        ".ecxr",
        "kv 200",
        "kP 200",
        "dps @rsp L300",
        "q",
    ])


def symbolicate_minidump(dmp_path: str, pdb_search_path: str | None = None) -> str | None:
    cdb = Path(config.CDB_PATH)
    if not cdb.exists():
        logger.warning("CDB not found: path=%s", cdb)
        return None

    dmp = Path(dmp_path)
    if not dmp.exists():
        logger.warning("Minidump not found: path=%s", dmp)
        return None

    pdb_path = pdb_search_path or config.PDB_SEARCH_PATH

    cmd = [
        str(cdb),
        "-z", str(dmp),
        "-y", pdb_path,
        "-c", _build_cdb_command(),
    ]

    try:
        logger.info("Running CDB: dmp=%s pdb_path=%s", dmp, pdb_path)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(dmp.parent),
        )
        raw_output = result.stdout
        if result.returncode != 0:
            logger.warning(
                "CDB exited with non-zero code: returncode=%s stderr=%s",
                result.returncode,
                result.stderr[-2000:] if result.stderr else "",
            )
        logger.info("CDB finished: returncode=%s stdout_chars=%s", result.returncode, len(raw_output))
        return _parse_cdb_output(raw_output)
    except subprocess.TimeoutExpired:
        logger.exception("CDB timed out: dmp=%s pdb_path=%s", dmp, pdb_path)
        return "符号化超时（120秒）"
    except Exception as e:
        logger.exception("CDB failed: dmp=%s pdb_path=%s", dmp, pdb_path)
        return f"符号化失败: {e}"


def _parse_cdb_output(raw: str) -> str:
    lines = raw.splitlines()
    stack_lines = []
    stack_texts = set()
    in_stack = False

    def append_stack_line(value: str):
        if value not in stack_texts:
            stack_texts.add(value)
            stack_lines.append(value)

    for line in lines:
        stripped = line.strip()
        if re.match(r"^[\da-fA-F]+`[\da-fA-F]+\s", stripped):
            in_stack = True
            append_stack_line(stripped)
        elif re.match(r"^Child-SP\s+RetAddr", stripped):
            in_stack = True
            append_stack_line(stripped)
        elif in_stack:
            if stripped == "" or stripped.startswith("quit:"):
                in_stack = False
            elif re.match(r"^[\da-fA-F]", stripped):
                append_stack_line(stripped)
            else:
                in_stack = False
        elif re.match(r"^[\da-fA-F]+`[\da-fA-F]+\s+[\da-fA-F]+`[\da-fA-F]+\s+.+!", stripped):
            append_stack_line(stripped)

    if stack_lines:
        return "\n".join(stack_lines)

    return raw


def find_symbol_package_matches(module_guids: list[dict], db) -> list[dict]:
    from ..models import SymbolGuid, SymbolPackage

    if not module_guids:
        return []

    normalized_modules = []
    for module in module_guids:
        guid = (module.get("guid") or "").upper()
        if not guid:
            continue
        normalized_modules.append({
            "guid": guid,
            "age": module.get("age"),
            "pdb_filename": (module.get("pdb_filename") or "").lower(),
            "module_name": module.get("module_name") or module.get("source_file") or "",
        })

    guid_values = [m["guid"] for m in normalized_modules]
    if not guid_values:
        return []

    rows = (
        db.query(SymbolGuid)
        .join(SymbolPackage)
        .filter(
            SymbolGuid.guid.in_(guid_values),
            SymbolPackage.status == "ready",
        )
        .all()
    )

    package_scores = {}
    seen_matches = set()
    for row in rows:
        row_guid = (row.guid or "").upper()
        row_age = row.age
        row_pdb = (row.pdb_filename or "").lower()

        for module in normalized_modules:
            if module["guid"] != row_guid:
                continue
            age_matches = module["age"] is None or row_age is None or module["age"] == row_age
            pdb_matches = not module["pdb_filename"] or not row_pdb or module["pdb_filename"] == row_pdb
            if not age_matches or not pdb_matches:
                continue

            package = row.symbol_package
            match_key = (package.id, module["guid"], module["age"], module["pdb_filename"])
            if match_key in seen_matches:
                continue
            seen_matches.add(match_key)

            current = package_scores.setdefault(package.id, {
                "symbol_package_id": package.id,
                "store_path": package.store_path,
                "game_name": package.game_name,
                "build_version": package.build_version,
                "platform": package.platform,
                "score": 0,
                "matched_guid_count": 0,
                "matched_modules": [],
            })
            score = 10
            if module["age"] == row_age:
                score += 3
            if module["pdb_filename"] and module["pdb_filename"] == row_pdb:
                score += 5
            current["score"] += score
            current["matched_guid_count"] += 1
            current["matched_modules"].append({
                "guid": row_guid,
                "age": row_age,
                "pdb_filename": row.pdb_filename,
                "module_name": module["module_name"],
            })

    return sorted(
        package_scores.values(),
        key=lambda item: (item["score"], item["matched_guid_count"]),
        reverse=True,
    )


def resolve_pdb_path(module_guids: list[dict], db) -> tuple[str, str | None]:
    matches = find_symbol_package_matches(module_guids, db)
    if matches:
        best = matches[0]
        return best["store_path"], best["symbol_package_id"]

    return config.PDB_SEARCH_PATH, None
