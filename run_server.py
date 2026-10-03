"""
Script khởi động backend trên Windows.
Phải set WindowsProactorEventLoopPolicy TRƯỚC KHI import uvicorn,
vì uvicorn.run() sẽ tạo event loop ngay lập tức khi được gọi.
"""
import asyncio
import sys

if sys.platform == "win32":
    # Playwright và các subprocess (ffmpeg, yt-dlp) cần ProactorEventLoop.
    # uvicorn --reload dùng WatchFiles process + subprocess worker; cả 2 đều
    # cần policy này được set trước khi uvicorn tạo loop.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "backend.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["backend"] if args.reload else None,
        reload_excludes=["downloads/*", "*.db*", "*.mp3", "*.mp4", "*.json"] if args.reload else None,
    )
