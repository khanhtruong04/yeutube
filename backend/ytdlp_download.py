"""
Tải video đa nền tảng qua yt-dlp Python API — bản Python-callable của skill
video-download (hiện chỉ là hướng dẫn bash cho agent, chưa có hàm gọi được).
Dùng đúng options skill đang dùng: bestvideo+bestaudio merge mp4, no-playlist,
restrict-filenames.
"""
import asyncio
from pathlib import Path

import yt_dlp


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
    url: str, out_dir: Path, cookiefile: str | None = None, max_res: int | None = None
) -> dict:
    """Tải video về out_dir/index.mp4. Trả về {title, extractor}.

    max_res: trần độ phân giải theo cạnh ngắn (vd. 1080, 720). None = lấy bản tốt nhất.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download_sync, url, out_dir, cookiefile, max_res)
