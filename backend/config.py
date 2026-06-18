from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

UPLOAD_DIR = BASE_DIR / "uploads"
CRASH_DIR = BASE_DIR / "crashes"
TEMP_DIR = PROJECT_DIR / "tmp"
SYMBOL_DIR = BASE_DIR / "symbols"
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "crashdog.log"
FAULT_LOG_FILE = LOG_DIR / "crashdog-fault.log"
LOG_LEVEL = "INFO"
DATABASE_URL = f"sqlite:///{PROJECT_DIR / 'crashdog.db'}"

PDB_SEARCH_PATH = str(PROJECT_DIR / "bin")
CDB_PATH = r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"

DEFAULT_AGENT = "copilot"
COPILOT_PATH = "copilot"
COPILOT_TIMEOUT = 600

SOURCE_DIR = str(PROJECT_DIR / "QingCheng")

LOG_TAIL_LINES = 200
