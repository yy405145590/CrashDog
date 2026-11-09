import logging
import os
import platform
import re
import shutil
import struct
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from .. import config
from . import crash_parser, guid_extractor


logger = logging.getLogger(__name__)

_cached_cdb_path: Path | None = None


def _preferred_cdb_architectures(configured_path: Path) -> list[str]:
    configured_arch = configured_path.parent.name.lower()
    if configured_arch == "x64":
        configured_arch = "amd64"

    machine_arch = platform.machine().lower()
    if machine_arch in {"x86_64", "x64"}:
        machine_arch = "amd64"
    elif machine_arch in {"i386", "i686"}:
        machine_arch = "x86"

    supported = ["amd64", "x86", "arm64"]
    preferred = configured_arch if configured_arch in supported else machine_arch
    return ([preferred] if preferred in supported else []) + [
        arch for arch in supported if arch != preferred
    ]


def _windows_sdk_cdb_candidates(architectures: list[str]) -> list[Path]:
    debugger_dir = Path(r"C:\Program Files (x86)\Windows Kits\10\Debuggers")
    sdk_arch_names = {"amd64": "x64", "x86": "x86", "arm64": "arm64"}
    return [debugger_dir / sdk_arch_names[arch] / "cdb.exe" for arch in architectures]


def _windbg_package_install_locations() -> list[Path]:
    if platform.system() != "Windows":
        return []

    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "Get-AppxPackage -Name Microsoft.WinDbg | "
        "Sort-Object Version -Descending | "
        "ForEach-Object { $_.InstallLocation }"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.exception("Failed to query the Microsoft.WinDbg package")
        return []

    if result.returncode != 0:
        logger.warning(
            "Microsoft.WinDbg package query failed: returncode=%s stderr=%s",
            result.returncode,
            result.stderr[-1000:] if result.stderr else "",
        )
        return []

    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def resolve_cdb_path() -> Path | None:
    """Find CDB without relying on a versioned Microsoft Store package path."""
    global _cached_cdb_path

    if _cached_cdb_path and _cached_cdb_path.is_file():
        return _cached_cdb_path

    configured = Path(config.CDB_PATH)
    if configured.is_file():
        _cached_cdb_path = configured
        return configured

    architectures = _preferred_cdb_architectures(configured)
    candidates = _windows_sdk_cdb_candidates(architectures)

    path_cdb = shutil.which("cdb.exe")
    if path_cdb:
        candidates.append(Path(path_cdb))

    for install_location in _windbg_package_install_locations():
        candidates.extend(install_location / arch / "cdb.exe" for arch in architectures)

    for candidate in candidates:
        if candidate.is_file():
            _cached_cdb_path = candidate
            logger.info("CDB auto-resolved: configured=%s resolved=%s", configured, candidate)
            return candidate

    _cached_cdb_path = None
    logger.warning("CDB not found: configured_path=%s", configured)
    return None


@dataclass
class DumpModule:
    name: str          # dump 里记录的镜像文件名，如 QingCheng-Win64-Shipping.exe
    base: int
    size: int
    guid: str          # CodeView GUID（与 guid_extractor 格式一致）
    age: int | None
    pdb_filename: str


def read_dump_modules(dmp_path: str | Path) -> list[DumpModule]:
    """读 minidump 的 ModuleListStream：模块名、基址、大小、CodeView。"""
    data = Path(dmp_path).read_bytes()
    if len(data) < 32 or data[:4] != b"MDMP":
        return []
    _, _, num_streams, stream_dir_rva, _ = struct.unpack_from("<4sIIII", data, 0)
    module_rva = 0
    for i in range(num_streams):
        off = stream_dir_rva + i * 12
        if off + 12 > len(data):
            break
        stream_type, _, rva = struct.unpack_from("<III", data, off)
        if stream_type == 4:
            module_rva = rva
            break
    if module_rva == 0:
        return []

    modules = []
    num_modules, = struct.unpack_from("<I", data, module_rva)
    for i in range(num_modules):
        mod_off = module_rva + 4 + i * 108
        if mod_off + 108 > len(data):
            break
        base, size = struct.unpack_from("<QI", data, mod_off)
        name_rva, = struct.unpack_from("<I", data, mod_off + 20)
        cv_size, cv_rva = struct.unpack_from("<II", data, mod_off + 76)
        name = ""
        if name_rva + 4 <= len(data):
            str_len, = struct.unpack_from("<I", data, name_rva)
            try:
                name = data[name_rva + 4: name_rva + 4 + str_len].decode("utf-16-le")
            except UnicodeDecodeError:
                pass
            name = name.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        guid, age, pdb = "", None, ""
        if cv_size >= 24:
            info = guid_extractor._parse_cv_info_pdb70(data, cv_rva)
            if info:
                guid, age, pdb = info.guid, info.age, info.pdb_filename
        modules.append(DumpModule(name, base, size, guid, age, pdb))
    return modules


def _pe_size_of_image(pe_path: Path) -> int | None:
    try:
        with open(pe_path, "rb") as f:
            head = f.read(4096)
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if head[pe:pe + 4] != b"PE\x00\x00":
            return None
        return struct.unpack_from("<I", head, pe + 24 + 56)[0]
    except (OSError, struct.error):
        return None


def _link_or_copy(src: Path, dst: Path):
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _prepare_game_images(modules: list[DumpModule], store_dirs: list[Path], alias_dir: Path) -> list[DumpModule]:
    """在符号目录里按 CodeView GUID 找到与 dump 模块对应的 exe/dll。

    打包出来的 exe 常被改名（QingChengSteam-Win64-Shipping.exe → 玩家机上是
    QingCheng-Win64-Shipping.exe），cdb 按 dump 里的名字找镜像，找不到就没有展开表。
    所以以 dump 里的名字建硬链接到 alias_dir，返回需要显式 .reload 的模块。
    """
    by_guid = {(m.guid, m.age): m for m in modules if m.guid}
    if not by_guid:
        return []

    matched: list[DumpModule] = []
    seen = set()
    for store in store_dirs:
        if not store.is_dir():
            continue
        for pe in list(store.rglob("*.exe")) + list(store.rglob("*.dll")):
            try:
                infos = guid_extractor.extract_guids_from_pe(pe)
            except OSError:
                continue
            for info in infos:
                mod = by_guid.get((info.guid, info.age))
                if mod is None or mod.name.lower() in seen:
                    continue
                if _pe_size_of_image(pe) not in (None, mod.size):
                    continue
                alias_dir.mkdir(parents=True, exist_ok=True)
                _link_or_copy(pe, alias_dir / mod.name)
                seen.add(mod.name.lower())
                matched.append(mod)
                logger.info("Game image matched: dump_module=%s file=%s", mod.name, pe)
    return matched


def _symbol_dirs(pdb_path: str) -> list[Path]:
    """符号包解压后可能有子目录，把含 pdb/exe/dll 的目录都加进搜索路径。"""
    dirs: list[Path] = []
    for part in pdb_path.split(";"):
        part = part.strip()
        if not part or "*" in part:
            continue
        root = Path(part)
        if not root.is_dir():
            continue
        found = {p.parent for ext in ("*.pdb", "*.exe", "*.dll") for p in root.rglob(ext)}
        dirs.extend(sorted(found) or [root])
    return dirs


def _ms_symbol_path() -> str:
    if not config.MS_SYMBOL_SERVER:
        return ""
    config.SYMBOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return f"srv*{config.SYMBOL_CACHE_DIR}*{config.MS_SYMBOL_SERVER}"


def _read_pcallstack(dmp: Path) -> list[tuple[str, int]]:
    """CrashContext 里 UE 在玩家机上展开好的崩溃线程调用栈：[(模块, 偏移)]。"""
    xml = dmp.parent / "CrashContext.runtime-xml"
    if not xml.is_file():
        return []
    try:
        text = crash_parser.parse_crash_context(xml).get("PCallStack", "")
    except Exception:
        logger.exception("Failed to read PCallStack: %s", xml)
        return []
    frames = []
    for line in text.splitlines():
        m = re.match(r"\s*(\S+)\s+0x[0-9a-fA-F]+\s*\+\s*([0-9a-fA-F]+)", line)
        if m:
            frames.append((m.group(1), int(m.group(2), 16)))
    return frames


_PCS_BEGIN = "@@PCALLSTACK_BEGIN@@"
_PCS_FRAME = "@@PCS@@"
_PCS_END = "@@PCALLSTACK_END@@"


def _build_cdb_command(reloads: list[DumpModule] | None = None,
                       pcallstack: list[tuple[str, int]] | None = None) -> str:
    cmds = []
    for mod in reloads or []:
        # dump 里没有镜像头，必须显式给出 名字=基址,大小
        cmds.append(f".reload /f /i {mod.name}={mod.base:x},{mod.size:x}")
    cmds += [".ecxr", "kv 200", "kP 200", "dps @rsp L300"]
    if pcallstack:
        cmds.append(".lines -e")
        cmds.append(f".echo {_PCS_BEGIN}")
        for module, offset in pcallstack:
            cmds.append(f".echo {_PCS_FRAME} {module}+0x{offset:x}")
            # 模块名里的 '-' 在 cdb 表达式里是减号，cdb 内部模块名用 '_'
            expr_mod = re.sub(r"[^0-9A-Za-z_]", "_", module)
            cmds.append(f"ln {expr_mod}+0x{offset:x}")
            cmds.append(f"lsa {expr_mod}+0x{offset:x},0,0")
        cmds.append(f".echo {_PCS_END}")
    cmds.append("q")
    # 写进脚本文件用 -cf 执行：一行一条命令。
    # 不能用 -c 拼分号：.echo 会吃掉后面整行，带引号的 .printf 又会被命令行转义截断。
    return "\n".join(cmds) + "\n"


def symbolicate_minidump(dmp_path: str, pdb_search_path: str | None = None) -> str | None:
    cdb = resolve_cdb_path()
    if cdb is None:
        return None

    dmp = Path(dmp_path)
    if not dmp.exists():
        logger.warning("Minidump not found: path=%s", dmp)
        return None

    pdb_path = pdb_search_path or config.PDB_SEARCH_PATH
    store_dirs = _symbol_dirs(pdb_path)

    alias_dir = config.SYMBOL_ALIAS_DIR / uuid.uuid4().hex[:12]
    try:
        modules = read_dump_modules(dmp)
    except Exception:
        logger.exception("Failed to read dump module list: %s", dmp)
        modules = []
    try:
        reloads = _prepare_game_images(modules, [Path(p) for p in pdb_path.split(";") if p and "*" not in p], alias_dir)
    except Exception:
        logger.exception("Failed to prepare game images: %s", dmp)
        reloads = []

    ms = _ms_symbol_path()
    local = [str(alias_dir)] if reloads else []
    local += [str(d) for d in store_dirs] or [pdb_path]
    sym_path = ";".join(([ms] if ms else []) + local)
    img_path = sym_path

    pcallstack = _read_pcallstack(dmp)

    alias_dir.mkdir(parents=True, exist_ok=True)
    script = alias_dir / "cdb_script.txt"
    script.write_text(_build_cdb_command(reloads, pcallstack), encoding="utf-8")

    cmd = [
        str(cdb),
        "-z", str(dmp),
        "-y", sym_path,
        "-i", img_path,
        "-cf", str(script),
    ]

    try:
        logger.info("Running CDB: dmp=%s sym_path=%s reloads=%s pcallstack_frames=%s",
                    dmp, sym_path, [m.name for m in reloads], len(pcallstack))
        result = subprocess.run(
            cmd,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.CDB_TIMEOUT,
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
        return _format_result(raw_output)
    except subprocess.TimeoutExpired:
        logger.exception("CDB timed out: dmp=%s sym_path=%s", dmp, sym_path)
        return f"符号化超时（{config.CDB_TIMEOUT}秒）"
    except Exception as e:
        logger.exception("CDB failed: dmp=%s sym_path=%s", dmp, sym_path)
        return f"符号化失败: {e}"
    finally:
        shutil.rmtree(alias_dir, ignore_errors=True)


def _parse_pcallstack_section(raw: str) -> tuple[str, list[str]]:
    """把 PCallStack 的 ln/lsa 输出整理成一帧一行；返回 (去掉该段的原文, 帧列表)。"""
    begin = raw.find(_PCS_BEGIN)
    end = raw.find(_PCS_END, begin + 1)
    if begin < 0 or end < 0:
        return raw, []
    rest = raw[:begin] + raw[end + len(_PCS_END):]
    # -cf 脚本的每条命令 cdb 会以 "0:085> 命令" 回显，去掉回显行，只留输出
    section = "\n".join(
        l for l in raw[begin:end].splitlines() if not re.match(r"^\s*\d+:\d+>", l)
    )

    frames = []
    for idx, chunk in enumerate(section.split(_PCS_FRAME)[1:]):
        lines = [l.strip() for l in chunk.splitlines() if l.strip()]
        addr = lines[0] if lines else "?"
        sym = ""
        src = ""
        for l in lines[1:]:
            m = re.match(r"^\([0-9a-fA-F`]+\)\s+(\S+?)\s*(\||$)", l)
            if m and not sym:
                sym = m.group(1)
            m2 = re.match(r"^([A-Za-z]:\\.+?\(\d+\))", l)
            if m2 and not src:
                src = m2.group(1)
        line = f"{idx:02d} {sym or addr}"
        if src:
            line += f"  [{src}]"
        frames.append(line)
    return rest, frames


def _format_result(raw: str) -> str:
    rest, pcs_frames = _parse_pcallstack_section(raw)
    stack = _parse_cdb_output(rest)
    if not pcs_frames:
        return stack
    return (
        "=== 崩溃线程调用栈（UE 上报 PCallStack 符号化）===\n"
        + "\n".join(pcs_frames)
        + "\n\n=== CDB 展开 ===\n"
        + stack
    )


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
