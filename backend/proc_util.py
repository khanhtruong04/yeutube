"""
Chạy tiến trình con (ffmpeg/ffprobe) độc lập với loại event loop đang dùng.

Lý do không dùng asyncio.create_subprocess_exec: trên Windows nó chỉ chạy được
với ProactorEventLoop. Khi bật `uvicorn --reload`, uvicorn tự chuyển sang
WindowsSelectorEventLoopPolicy -> mọi lệnh gọi subprocess ném NotImplementedError,
làm hỏng toàn bộ pipeline (bước nào cũng cần ffmpeg/ffprobe).

Gọi subprocess đồng bộ trong thread riêng qua asyncio.to_thread thì chạy đúng
với mọi event loop, trên mọi hệ điều hành.
"""
import asyncio
import subprocess
import sys

# Không bật cửa sổ console mới cho mỗi lần gọi ffmpeg trên Windows.
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _run_sync(cmd: list[str]) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATION_FLAGS,
    )
    return proc.returncode, proc.stdout, proc.stderr


async def run_command(cmd: list[str]) -> tuple[int, bytes, bytes]:
    """Chạy lệnh, trả về (returncode, stdout, stderr)."""
    return await asyncio.to_thread(_run_sync, cmd)
