import logging
import re
import subprocess
from pathlib import Path

from .. import config


logger = logging.getLogger(__name__)


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
        "-c", ".ecxr; kv 100; q",
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
    in_stack = False

    for line in lines:
        stripped = line.strip()
        if re.match(r"^[\da-fA-F]+`[\da-fA-F]+\s", stripped):
            in_stack = True
            stack_lines.append(stripped)
        elif re.match(r"^Child-SP\s+RetAddr", stripped):
            in_stack = True
            stack_lines.append(stripped)
        elif in_stack:
            if stripped == "" or stripped.startswith("quit:"):
                in_stack = False
            elif re.match(r"^[\da-fA-F]", stripped):
                stack_lines.append(stripped)
            else:
                in_stack = False

    if stack_lines:
        return "\n".join(stack_lines)

    return raw


def resolve_pdb_path(module_guids: list[dict], db) -> tuple[str, str | None]:
    from ..models import SymbolGuid, SymbolPackage

    if not module_guids:
        return config.PDB_SEARCH_PATH, None

    guid_values = [m["guid"] for m in module_guids if m.get("guid")]
    if not guid_values:
        return config.PDB_SEARCH_PATH, None

    match = (
        db.query(SymbolGuid)
        .join(SymbolPackage)
        .filter(
            SymbolGuid.guid.in_(guid_values),
            SymbolPackage.status == "ready",
        )
        .first()
    )

    if match:
        pkg = match.symbol_package
        return pkg.store_path, pkg.id

    return config.PDB_SEARCH_PATH, None
