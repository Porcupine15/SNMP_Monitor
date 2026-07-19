from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import environment, validate_runtime_config
from app.database import SessionLocal
from app.routes import auth, clients, discovery, lab, operations, devices, printers, dashboard, ping, admin
from app.scheduler import start_scheduler, shutdown_scheduler

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "script-src-attr 'none'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "base-uri 'none'; "
    "object-src 'none'; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "
    "media-src 'none'; "
    "worker-src 'none'"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_config()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()

production = environment() == "production"
app = FastAPI(
    title="SNMP Monitor API",
    version="0.4",
    lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)

trusted_hosts = [host.strip() for host in os.getenv("TRUSTED_HOSTS", "").split(",") if host.strip()]
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

allowed_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=bool(allowed_origins),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Lan-Agent-Token"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(printers.router)
app.include_router(dashboard.router)
app.include_router(ping.router)
app.include_router(admin.router)
app.include_router(discovery.router)
if not production:
    app.include_router(lab.router)
app.include_router(operations.router)
app.include_router(clients.router)

@app.get("/api/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/api/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    finally:
        db.close()
    return {"status": "ok", "database": "ok"}

frontend_dir = Path("/app/frontend")
if not frontend_dir.exists():
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_index():
    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)
