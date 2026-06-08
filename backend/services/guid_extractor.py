import logging
import math
import struct
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PdbGuidInfo:
    guid: str
    age: int
    pdb_filename: str
    source_file: str


def _format_guid(guid_bytes: bytes) -> str:
    data1, data2, data3 = struct.unpack_from("<IHH", guid_bytes, 0)
    tail = guid_bytes[8:16].hex().upper()
    return f"{data1:08X}{data2:04X}{data3:04X}{tail}"


def _parse_cv_info_pdb70(data: bytes, offset: int) -> PdbGuidInfo | None:
    if offset + 24 > len(data):
        return None
    cv_sig, = struct.unpack_from("<I", data, offset)
    if cv_sig != 0x53445352:  # 'RSDS'
        return None
    guid_bytes = data[offset + 4: offset + 20]
    age, = struct.unpack_from("<I", data, offset + 20)
    end = data.find(b"\x00", offset + 24)
    if end == -1:
        end = len(data)
    pdb_filename = data[offset + 24: end].decode("utf-8", errors="replace")
    pdb_filename = pdb_filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    return PdbGuidInfo(
        guid=_format_guid(guid_bytes),
        age=age,
        pdb_filename=pdb_filename,
        source_file="",
    )


def extract_guids_from_dmp(dmp_path: str | Path) -> list[PdbGuidInfo]:
    dmp_path = Path(dmp_path)
    data = dmp_path.read_bytes()

    if len(data) < 32 or data[:4] != b"MDMP":
        return []

    _, _, num_streams, stream_dir_rva, _ = struct.unpack_from("<4sIIII", data, 0)

    module_rva = 0
    for i in range(num_streams):
        off = stream_dir_rva + i * 12
        if off + 12 > len(data):
            break
        stream_type, data_size, rva = struct.unpack_from("<III", data, off)
        if stream_type == 4:  # ModuleListStream
            module_rva = rva
            break

    if module_rva == 0:
        return []

    num_modules, = struct.unpack_from("<I", data, module_rva)
    results = []

    for i in range(num_modules):
        mod_off = module_rva + 4 + i * 108
        if mod_off + 108 > len(data):
            break

        name_rva, = struct.unpack_from("<I", data, mod_off + 20)
        cv_data_size, cv_rva = struct.unpack_from("<II", data, mod_off + 76)

        module_name = ""
        if name_rva + 4 <= len(data):
            str_len, = struct.unpack_from("<I", data, name_rva)
            end_pos = min(name_rva + 4 + str_len, len(data))
            try:
                module_name = data[name_rva + 4: end_pos].decode("utf-16-le")
                module_name = module_name.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
            except Exception:
                pass

        if cv_data_size >= 24 and cv_rva + 24 <= len(data):
            info = _parse_cv_info_pdb70(data, cv_rva)
            if info:
                info.source_file = module_name
                results.append(info)

    return results


def extract_guids_from_pe(pe_path: str | Path) -> list[PdbGuidInfo]:
    pe_path = Path(pe_path)
    data = pe_path.read_bytes()

    if len(data) < 0x40 or data[:2] != b"MZ":
        return []

    pe_offset, = struct.unpack_from("<I", data, 0x3C)
    if pe_offset + 24 > len(data) or data[pe_offset: pe_offset + 4] != b"PE\x00\x00":
        return []

    coff_off = pe_offset + 4
    _, num_sections, _, _, _, opt_size, _ = struct.unpack_from("<HHIIIHH", data, coff_off)

    opt_off = coff_off + 20
    if opt_off + 2 > len(data):
        return []

    magic, = struct.unpack_from("<H", data, opt_off)
    if magic == 0x20B:  # PE32+
        data_dir_start = opt_off + 112
    elif magic == 0x10B:  # PE32
        data_dir_start = opt_off + 96
    else:
        return []

    if data_dir_start + 7 * 8 > len(data):
        return []

    debug_rva, debug_size = struct.unpack_from("<II", data, data_dir_start + 6 * 8)
    if debug_rva == 0 or debug_size == 0:
        return []

    sections_off = opt_off + opt_size
    sections = []
    for j in range(num_sections):
        s_off = sections_off + j * 40
        if s_off + 40 > len(data):
            break
        _, vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<8sIIII", data, s_off)
        sections.append((vaddr, vsize, raw_ptr, raw_size))

    def rva_to_offset(rva):
        for vaddr, vsize, raw_ptr, raw_size in sections:
            if vaddr <= rva < vaddr + vsize:
                return rva - vaddr + raw_ptr
        return rva

    debug_file_off = rva_to_offset(debug_rva)
    num_entries = debug_size // 28
    results = []
    filename = pe_path.name

    for i in range(num_entries):
        entry_off = debug_file_off + i * 28
        if entry_off + 28 > len(data):
            break
        _, _, _, _, dbg_type, size_of_data, _, ptr_to_raw = struct.unpack_from(
            "<IIHHIIII", data, entry_off
        )
        if dbg_type == 2 and ptr_to_raw + 24 <= len(data):  # IMAGE_DEBUG_TYPE_CODEVIEW
            info = _parse_cv_info_pdb70(data, ptr_to_raw)
            if info:
                info.source_file = filename
                results.append(info)

    return results


def extract_guids_from_pdb(pdb_path: str | Path) -> list[PdbGuidInfo]:
    pdb_path = Path(pdb_path)
    MSF_MAGIC = b"Microsoft C/C++ MSF 7.00\r\n\x1aDS\x00\x00\x00"

    with open(pdb_path, "rb") as f:
        magic = f.read(32)
        if magic != MSF_MAGIC:
            return []

        header = f.read(24)
        block_size, _, _, num_dir_bytes, _, block_map_addr = struct.unpack("<IIIIII", header)

        num_dir_blocks = math.ceil(num_dir_bytes / block_size)
        f.seek(block_map_addr * block_size)
        block_indices = struct.unpack(f"<{num_dir_blocks}I", f.read(num_dir_blocks * 4))

        dir_data = bytearray()
        for bi in block_indices:
            f.seek(bi * block_size)
            dir_data.extend(f.read(block_size))
        dir_data = bytes(dir_data[:num_dir_bytes])

        if len(dir_data) < 4:
            return []
        num_streams, = struct.unpack_from("<I", dir_data, 0)

        if num_streams < 2:
            return []

        sizes_end = 4 + num_streams * 4
        if sizes_end > len(dir_data):
            return []
        stream_sizes = struct.unpack_from(f"<{num_streams}I", dir_data, 4)

        blocks_offset = sizes_end
        stream1_blocks = []
        for s_idx in range(num_streams):
            s_size = stream_sizes[s_idx]
            if s_size == 0xFFFFFFFF or s_size == 0:
                if s_idx == 1:
                    return []
                continue
            n_blocks = math.ceil(s_size / block_size)
            if s_idx == 1:
                for b in range(n_blocks):
                    pos = blocks_offset + b * 4
                    if pos + 4 > len(dir_data):
                        return []
                    bi, = struct.unpack_from("<I", dir_data, pos)
                    stream1_blocks.append(bi)
                break
            blocks_offset += n_blocks * 4

        if not stream1_blocks:
            return []

        stream1_data = bytearray()
        for bi in stream1_blocks:
            f.seek(bi * block_size)
            stream1_data.extend(f.read(block_size))
        stream1_data = bytes(stream1_data[: stream_sizes[1]])

        if len(stream1_data) < 28:
            return []

        _, _, age = struct.unpack_from("<III", stream1_data, 0)
        guid_bytes = stream1_data[12:28]
        guid = _format_guid(guid_bytes)

        return [PdbGuidInfo(
            guid=guid,
            age=age,
            pdb_filename=pdb_path.name,
            source_file=pdb_path.name,
        )]


def scan_directory_for_guids(directory: str | Path) -> list[PdbGuidInfo]:
    directory = Path(directory)
    results = []

    for f in directory.rglob("*"):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        try:
            if ext == ".pdb":
                infos = extract_guids_from_pdb(f)
            elif ext in (".exe", ".dll"):
                infos = extract_guids_from_pe(f)
            else:
                continue
            for info in infos:
                info.source_file = str(f.relative_to(directory))
                results.append(info)
        except Exception as e:
            logger.warning("Failed to extract GUID from %s: %s", f, e)

    return results
