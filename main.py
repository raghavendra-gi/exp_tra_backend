import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from database import SessionLocal
from deps import clear_user_cache
from migrate import run_migrations
from routers import auth, users, expenses, files
from config import settings
from seed import seed_users

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Alembic migrations replace Base.metadata.create_all(): they create the
    # tables on a new database AND evolve existing ones (create_all never adds
    # columns or indexes to a table that already exists). See migrate.py.
    run_migrations()
    clear_user_cache()
    db = SessionLocal()
    try:
        seed_users(db)                      # creates head/hr/emp1-3 once
    finally:
        db.close()
    yield


app = FastAPI(title="Expense Tracker API", version="1.2.0", lifespan=lifespan)


class ServerTiming:
    """
    Adds `Server-Timing: app;dur=<ms>` to every response, so the browser's
    Network tab shows how long the API itself took (vs. network time).
    Plain ASGI middleware: no per-request overhead of BaseHTTPMiddleware.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        start = time.perf_counter()

        async def send_with_timing(message):
            if message["type"] == "http.response.start":
                dur = (time.perf_counter() - start) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"server-timing", f"app;dur={dur:.1f}".encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_timing)


# Compress JSON responses over 1 KB. Expense lists are highly repetitive JSON
# and typically shrink 70-90%, which matters most on mobile data.
# Level 5 compresses almost as well as the default 9 at a fraction of the CPU.
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,   # e.g. every *.vercel.app deployment of this project
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=600,   # browsers cache the CORS pre-flight for 10 min instead of asking before every call
)

app.add_middleware(ServerTiming)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["expenses"])
app.include_router(files.router, prefix="/api/files", tags=["files"])


@app.get("/")
def root():
    # Render pings "/" — without this it logs a 404 on every check
    return {"service": "Expense Tracker API", "status": "ok", "docs": "/docs"}


@app.get("/api/health")
def health():
    return {"status": "ok"}
