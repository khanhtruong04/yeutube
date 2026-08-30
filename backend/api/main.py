import sys
from pathlib import Path

# Windows: stdout/stderr mặc định dùng codepage hệ thống (vd. cp1252), không in
# được tiếng Việt/Trung có dấu -> rich.Console() ở crawler/downloader/transcribe
# (log "Mở {url}...", v.v.) sẽ crash UnicodeEncodeError khi chạy trong
# BackgroundTasks. Ép UTF-8 trước khi import các module đó.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from .. import jobs_store  # noqa: E402
from .routers import jobs, meta, voices  # noqa: E402

app = FastAPI(title="Video Dubbing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

downloads_dir = PROJECT_ROOT / "downloads"
downloads_dir.mkdir(exist_ok=True)
app.mount("/files", StaticFiles(directory=str(downloads_dir)), name="files")

app.include_router(jobs.router, prefix="/api")
app.include_router(voices.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


@app.on_event("startup")
async def on_startup():
    await jobs_store.init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok"}
