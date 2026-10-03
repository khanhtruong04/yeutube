"""
Tải video đa nền tảng qua yt-dlp Python API — bản Python-callable của skill
video-download (hiện chỉ là hướng dẫn bash cho agent, chưa có hàm gọi được).
Dùng đúng options skill đang dùng: bestvideo+bestaudio merge mp4, no-playlist,
restrict-filenames.
"""
import asyncio
from pathlib import Path

import yt_dlp

# Douyin chặn chập chờn -> thử lại vài lần, chờ lâu dần.
_DOWNLOAD_RETRIES = 3
_DOWNLOAD_RETRY_DELAY = 4.0


def _download_sync(url: str, out_dir: Path, cookiefile: str | None, max_res: int | None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "restrictfilenames": True,
        "outtmpl": str(out_dir / "index.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    if max_res:
        # `res` của yt-dlp là CẠNH NGẮN của khung hình, nên "1080p" hiểu đúng cho
        # cả video ngang (1920x1080) lẫn video dọc kiểu Douyin (1080x1920) —
        # dùng [height<=1080] sẽ loại nhầm video dọc vì chiều cao là 1920.
        # Đây là mức trần: nguồn không có bản đó thì lấy bản cao nhất bên dưới.
        ydl_opts["format_sort"] = [f"res:{max_res}"]
    # Douyin bắt buộc phải có cookies mới cho tải ("Fresh cookies ... are needed").
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return {
        "title": info.get("title") or "video",
        "extractor": info.get("extractor_key") or info.get("extractor") or "unknown",
    }


async def download_via_ytdlp(
    url: str,
    out_dir: Path,
    cookiefile: str | None = None,
    max_res: int | None = None,
    log=None,
) -> dict:
    """Tải video về out_dir/index.mp4. Trả về {title, extractor}.

    max_res: trần độ phân giải theo cạnh ngắn (vd. 1080, 720). None = lấy bản tốt nhất.

    Tự thử lại khi lỗi: Douyin thỉnh thoảng trả "Fresh cookies (not necessarily
    logged in) are needed" cho đúng link mà ngay sau đó tải lại thì được — dạng
    chặn tạm thời, không phải cookies hỏng. Không có retry thì một lần chập chờn
    làm hỏng cả job.
    """
    _log = log or (lambda _: None)
    loop = asyncio.get_event_loop()
    last_error: Exception | None = None

    for attempt in range(_DOWNLOAD_RETRIES + 1):
        try:
            return await loop.run_in_executor(None, _download_sync, url, out_dir, cookiefile, max_res)
        except Exception as e:
            last_error = e
            if attempt < _DOWNLOAD_RETRIES:
                delay = _DOWNLOAD_RETRY_DELAY * (attempt + 1)
                _log(f"[ytdlp] tải lỗi ({str(e)[:120]}), chờ {delay:.0f}s rồi thử lần {attempt + 2}...")
                await asyncio.sleep(delay)

    raise last_error if last_error else RuntimeError("Không tải được video.")
