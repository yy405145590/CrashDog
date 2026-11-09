from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

UPLOAD_DIR = BASE_DIR / "uploads"
CRASH_DIR = BASE_DIR / "crashes"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
TEMP_DIR = PROJECT_DIR / "tmp"
SYMBOL_DIR = BASE_DIR / "symbols"
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "crashdog.log"
FAULT_LOG_FILE = LOG_DIR / "crashdog-fault.log"
LOG_LEVEL = "INFO"
DATABASE_URL = f"sqlite:///{PROJECT_DIR / 'crashdog.db'}"

PDB_SEARCH_PATH = str(PROJECT_DIR / "bin")
CDB_PATH = r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"

# 系统 dll（KERNELBASE/ntdll/VCRUNTIME/msvcp 等）的镜像和 pdb 从微软符号服务器拉取。
# minidump 不带模块镜像，没有它们的展开表（.pdata）时 x64 调用栈在第 0 帧就断了。
# 内网无外网时置空字符串，只用本地缓存 + PCallStack 兜底。
MS_SYMBOL_SERVER = "https://msdl.microsoft.com/download/symbols"
SYMBOL_CACHE_DIR = PROJECT_DIR / "symcache"
# 每次符号化为游戏模块按 dump 里的模块名建别名（硬链接）的临时目录
SYMBOL_ALIAS_DIR = TEMP_DIR / "symalias"
# 首次要从符号服务器下载系统符号，给足时间
CDB_TIMEOUT = 600

DEFAULT_AGENT = "copilot"
COPILOT_PATH = "copilot"
COPILOT_TIMEOUT = 600

SOURCE_DIR = str(PROJECT_DIR / "QingCheng")

LOG_TAIL_LINES = 200

# 截图上传限制
ALLOWED_SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
MAX_SCREENSHOTS_PER_CRASH = 10
