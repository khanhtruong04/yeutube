import asyncio
import sys
from pathlib import Path

# Windows: stdout/stderr mặc định dùng codepage hệ thống (vd. cp1252), không in
# được tiếng Việt/Trung có dấu -> rich.Console() ở crawler/downloader/transcribe
# (log "Mở {url}...", v.v.) sẽ crash UnicodeEncodeError khi chạy trong
# BackgroundTasks. Ép UTF-8 trước khi import các module đó.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    # Playwright và ffmpeg dùng asyncio.create_subprocess_exec vốn chỉ chạy
    # được trên ProactorEventLoop. Khi bật --reload, uvicorn tự đổi sang
    # WindowsSelectorEventLoopPolicy và làm hỏng Playwright.
    # Ép lại ProactorEventLoop trước khi uvicorn can thiệp.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from .. import jobs_store  # noqa: E402
from . import pipeline  # noqa: E402
from .routers import jobs, meta, voices  # noqa: E402

app = FastAPI(title="Video Dubbing API")

# Mở cho mọi origin để máy khác cùng mạng LAN vào được qua IP (vd.
# http://192.168.1.6:3000). An toàn ở mức tương đương cấu hình cũ: API không
# dùng cookie/credential nên CORS không phải lớp bảo vệ ở đây — thứ quyết định
# ai truy cập được là việc server có mở ra ngoài mạng hay không (--host).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

downloads_dir = PROJECT_ROOT / "downloads"
downloads_dir.mkdir(exist_ok=True)
app.mount("/files", StaticFiles(directory=str(downloads_dir)), name="files")

app.include_router(jobs.router, prefix="/api")
app.include_router(voices.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


async def _recover_stalled_jobs():
    """Tự động phát hiện và tiếp tục các job bị gián đoạn do server restart/reload."""
    await asyncio.sleep(1.0)
    try:
        rows = await jobs_store.list_jobs(limit=100)
        for r in rows:
            jid = r["id"]
            status = r["status"]
            prep_status = r.get("prep_status")
            folder = Path(r["folder"]) if r.get("folder") else None

            if status == "waiting_prep" and prep_status in ("synthesizing", "translating", "transcribing", "pending"):
                if folder and (folder / "index.mp4").exists():
                    print(f"[recovery] Khôi phục job {jid} đang dở ở bước prep...")
                    asyncio.create_task(pipeline.run_prep(jid))
            elif status == "rendering":
                if folder and (folder / "dub_vi.mp3").exists():
                    print(f"[recovery] Khôi phục job {jid} đang dở ở bước render...")
                    asyncio.create_task(pipeline._render(jid))
    except Exception as e:
        print(f"[recovery] Lỗi kiểm tra job dở dang: {e}")


@app.on_event("startup")
async def on_startup():
    await jobs_store.init_db()
    asyncio.create_task(_recover_stalled_jobs())


@app.get("/api/health")
async def health():
    return {"status": "ok"}
