import atexit
import faulthandler
import logging
import os
import signal
import sys
import threading
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .database import init_db
from .routers import analysis, crash, symbol


_fault_log_handle = None


def configure_logging():
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=log_level,
        handlers=[console_handler, file_handler],
        force=True,
    )

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).handlers.clear()
        logging.getLogger(logger_name).propagate = True


def configure_process_diagnostics():
    global _fault_log_handle

    if _fault_log_handle is None:
        _fault_log_handle = open(config.FAULT_LOG_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_log_handle, all_threads=True)

    logger = logging.getLogger(__name__)
    logger.info(
        "Process diagnostics enabled: pid=%s ppid=%s executable=%s argv=%s cwd=%s fault_log=%s",
        os.getpid(),
        os.getppid(),
        sys.executable,
        sys.argv,
        os.getcwd(),
        config.FAULT_LOG_FILE,
    )

    def log_excepthook(exc_type, exc, traceback):
        logger.critical("Unhandled top-level exception", exc_info=(exc_type, exc, traceback))
        sys.__excepthook__(exc_type, exc, traceback)

    def log_threading_excepthook(args):
        logger.critical(
            "Unhandled thread exception: thread=%s",
            args.thread.name if args.thread else None,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        if hasattr(threading, "__excepthook__"):
            threading.__excepthook__(args)

    sys.excepthook = log_excepthook
    if hasattr(threading, "excepthook"):
        threading.excepthook = log_threading_excepthook

    def log_exit():
        logger.info("Python process exiting: pid=%s", os.getpid())
        for handler in logging.getLogger().handlers:
            handler.flush()
        if _fault_log_handle is not None:
            _fault_log_handle.flush()

    atexit.register(log_exit)

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        previous_handler = signal.getsignal(sig)

        def make_handler(name, signum, old_handler):
            def handler(received_signum, frame):
                logger.warning("Received signal: name=%s signum=%s pid=%s", name, received_signum, os.getpid())
                for log_handler in logging.getLogger().handlers:
                    log_handler.flush()
                if callable(old_handler):
                    old_handler(received_signum, frame)
                elif old_handler == signal.SIG_DFL:
                    raise KeyboardInterrupt if signum == signal.SIGINT else SystemExit(128 + received_signum)
            return handler

        signal.signal(sig, make_handler(signal_name, sig, previous_handler))


configure_logging()
configure_process_diagnostics()
logger = logging.getLogger(__name__)

app = FastAPI(title="CrashDog", description="UE5 崩溃收集与分析平台")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(crash.router)
app.include_router(analysis.router)
app.include_router(symbol.router)


@app.middleware("http")
async def log_unhandled_request_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled request error: method=%s path=%s client=%s",
            request.method,
            request.url.path,
            request.client.host if request.client else None,
        )
        raise


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled application exception: method=%s path=%s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


@app.on_event("startup")
def startup():
    logger.info("CrashDog backend starting")
    init_db()
    logger.info("CrashDog backend started; database=%s log_file=%s", config.DATABASE_URL, config.LOG_FILE)


@app.get("/api/health")
def health():
    return {"status": "ok"}
