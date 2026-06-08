from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import analysis, crash, symbol

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


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}
