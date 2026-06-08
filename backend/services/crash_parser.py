import json
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .. import config


def extract_zip(zip_path: Path, extract_base: Path) -> Path:
    temp_dir = extract_base / f"_tmp_{uuid.uuid4().hex[:8]}"
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(temp_dir)

    crash_dir = _find_crash_dir(temp_dir)
    if crash_dir is None:
        shutil.rmtree(temp_dir)
        raise ValueError("ZIP 中未找到 CrashContext.runtime-xml 文件")

    crash_guid = _extract_guid(crash_dir)
    final_dir = extract_base / crash_guid
    if final_dir.exists():
        shutil.rmtree(final_dir)
    shutil.move(str(crash_dir), str(final_dir))

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    return final_dir


def _find_crash_dir(root: Path) -> Path | None:
    for xml_file in root.rglob("CrashContext.runtime-xml"):
        return xml_file.parent
    return None


def _extract_guid(crash_dir: Path) -> str:
    xml_path = crash_dir / "CrashContext.runtime-xml"
    if xml_path.exists():
        ctx = parse_crash_context(xml_path)
        guid = ctx.get("CrashGUID")
        if guid:
            return guid
    return crash_dir.name


def parse_crash_context(xml_path: Path) -> dict:
    raw = xml_path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="replace")
    root = ET.fromstring(text)
    runtime = root.find("RuntimeProperties")
    if runtime is None:
        return {}

    fields = [
        "CrashGUID", "GameName", "ExecutableName", "BuildConfiguration",
        "PlatformName", "EngineVersion", "BuildVersion", "ErrorMessage",
        "CrashType", "IsEnsure", "IsAssert", "IsStall",
        "SecondsSinceStart", "ProcessId",
        "Misc.NumberOfCores", "Misc.CPUBrand", "Misc.PrimaryGPUBrand",
        "Misc.OSVersionMajor",
        "MemoryStats.TotalPhysicalGB", "MemoryStats.AvailablePhysical",
        "MemoryStats.bIsOOM",
    ]

    result = {}
    for field in fields:
        el = runtime.find(field)
        if el is not None and el.text:
            result[field] = el.text.strip()

    pcallstack_el = runtime.find("PCallStack")
    if pcallstack_el is not None and pcallstack_el.text:
        result["PCallStack"] = pcallstack_el.text.strip()

    pcallstack_hash_el = runtime.find("PCallStackHash")
    if pcallstack_hash_el is not None and pcallstack_hash_el.text:
        result["PCallStackHash"] = pcallstack_hash_el.text.strip()

    threads_el = runtime.find("Threads")
    crashed_thread = None
    thread_list = []
    if threads_el is not None:
        for thread_el in threads_el.findall("Thread"):
            t = {}
            name_el = thread_el.find("ThreadName")
            tid_el = thread_el.find("ThreadID")
            crashed_el = thread_el.find("IsCrashed")
            stack_el = thread_el.find("CallStack")

            if name_el is not None and name_el.text:
                t["name"] = name_el.text.strip()
            if tid_el is not None and tid_el.text:
                t["id"] = tid_el.text.strip()
            if crashed_el is not None and crashed_el.text:
                t["is_crashed"] = crashed_el.text.strip().lower() == "true"
                if t["is_crashed"] and name_el is not None:
                    crashed_thread = name_el.text.strip()
            if stack_el is not None and stack_el.text:
                t["callstack"] = stack_el.text.strip()

            thread_list.append(t)

    result["crashed_thread"] = crashed_thread
    result["threads"] = thread_list

    engine_data = root.find("EngineData")
    if engine_data is not None:
        for child in engine_data:
            if child.text:
                result[f"Engine.{child.tag}"] = child.text.strip()

    return result


def determine_crash_type(ctx: dict) -> str:
    if ctx.get("IsEnsure", "false").lower() == "true":
        return "Ensure"
    if ctx.get("IsAssert", "false").lower() == "true":
        return "Assert"
    if ctx.get("IsStall", "false").lower() == "true":
        return "Stall"
    return ctx.get("CrashType", "Crash")


def read_log_file(crash_dir: Path) -> tuple[str, str]:
    log_files = list(crash_dir.glob("*.log"))
    if not log_files:
        return "", ""
    log_path = log_files[0]
    content = log_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    tail = "\n".join(lines[-config.LOG_TAIL_LINES:])
    return content, tail


def parse_crash_directory(crash_dir: Path) -> dict:
    xml_path = crash_dir / "CrashContext.runtime-xml"
    if not xml_path.exists():
        raise FileNotFoundError(f"CrashContext.runtime-xml not found in {crash_dir}")

    ctx = parse_crash_context(xml_path)
    log_content, log_tail = read_log_file(crash_dir)
    crash_type = determine_crash_type(ctx)

    dmp_files = list(crash_dir.glob("*.dmp"))

    return {
        "id": ctx.get("CrashGUID", crash_dir.name),
        "game_name": ctx.get("GameName"),
        "build_version": ctx.get("BuildVersion"),
        "platform": ctx.get("PlatformName"),
        "engine_version": ctx.get("EngineVersion"),
        "error_message": ctx.get("ErrorMessage"),
        "crash_type": crash_type,
        "crashed_thread": ctx.get("crashed_thread"),
        "raw_callstack": ctx.get("PCallStack", ""),
        "crash_context_json": json.dumps(ctx, ensure_ascii=False, indent=2),
        "log_content": log_content,
        "log_tail": log_tail,
        "has_minidump": len(dmp_files) > 0,
        "minidump_path": str(dmp_files[0]) if dmp_files else None,
    }
