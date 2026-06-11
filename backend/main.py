import logging
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .database import init_db
from .routers import analysis, crash, symbol


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


configure_logging()
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
