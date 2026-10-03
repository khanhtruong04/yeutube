"""
Tải Douyin bằng trình duyệt thật khi yt-dlp bị chặn.

yt-dlp gọi thẳng API `aweme/v1/web/aweme/detail/` nhưng chưa cài bước tự sinh
chữ ký chống-bot của Douyin (chính source yt-dlp ghi `# TODO: Run verification
challenge code to generate signature cookies`), nên trả lỗi "Fresh cookies ...
are needed" kể cả khi cookies đăng nhập còn hạn — export lại cookie không cứu được.

Playwright thì không vướng: trang tự chạy JS ký request, ta chỉ việc nghe response
API rồi lấy link CDN trong đó. Link CDN sau đó tải bằng HTTP thường, không cần
cookie hay chữ ký gì.
"""
import asyncio
import re
from pathlib import Path

import aiofiles
import aiohttp

from .cookies_util import COOKIES_JSON
from .crawler import crawl_single_url
from .downloader import CHUNK_SIZE, DOUYIN_HEADERS


_SHORT_HOSTS = ("v.douyin.com", "iesdouyin.com")
_CRAWL_ATTEMPTS = 2
_CRAWL_RETRY_DELAY = 10.0
_AWEME_ID_RE = re.compile(r"/video/(\d+)")


def is_douyin(url: str) -> bool:
    return "douyin.com" in url


def _aweme_id(detail_url: str) -> str | None:
    m = _AWEME_ID_RE.search(detail_url)
    return m.group(1) if m else None


async def _resolve_short_url(url: str) -> str:
    """Đổi link rút gọn v.douyin.com thành link /video/<id> thật.

    Mở thẳng link rút gọn trong Playwright thì trang không gọi API chi tiết nên
    không bắt được gì; link /video/<id> thì chạy đúng, và crawler cũng cần id
    trong path để lọc đúng video giữa các response nó nghe được."""
    if not any(host in url for host in _SHORT_HOSTS):
        return url
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, headers=DOUYIN_HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            final = resp.url
    # Bỏ query: link rút gọn redirect kèm ?previous_page=web_code_link, giữ lại
    # thì Douyin ra trang khác không gọi API chi tiết, crawler nghe không thấy gì.
    return f"{final.scheme}://{final.host}{final.path}"


async def download_douyin_via_browser(url: str, out_dir: Path, log=None) -> dict:
    """Tải video Douyin về out_dir/index.mp4. Trả về {title, extractor} như download_via_ytdlp.

    Không nhận max_res: link CDN Douyin trả về chỉ có một bản, không chọn được
    độ phân giải như yt-dlp."""
    _log = log or (lambda _: None)
    out_dir.mkdir(parents=True, exist_ok=True)

    cookies_file = str(COOKIES_JSON) if COOKIES_JSON.exists() else None
    detail_url = await _resolve_short_url(url)
    _log("[douyin] yt-dlp không tải được, thử lại bằng trình duyệt thật...")

    # Douyin thỉnh thoảng trả trang không gọi API chi tiết -> mở lại lần nữa.
    wanted_id = _aweme_id(detail_url)
    video = None
    for attempt in range(_CRAWL_ATTEMPTS):
        found = await crawl_single_url(url=detail_url, headless=True, cookies_file=cookies_file)
        # Khi Douyin coi link là 404 nó đá sang feed trang chủ, và crawler nhặt
        # được video BẤT KỲ trong feed đó. Không đối chiếu id thì job lẳng lặng
        # tải về nhầm video mà không ai biết.
        if found and wanted_id and found["aweme_id"] != wanted_id:
            _log(f"[douyin] trang trả về video khác ({found['aweme_id']}), bỏ qua.")
            found = None
        if found:
            video = found
            break
        if attempt < _CRAWL_ATTEMPTS - 1:
            # Nghỉ trước khi mở lại: khi Douyin đang chặn tạm thời, mở lại ngay
            # chỉ làm nó chặn chặt hơn.
            _log(f"[douyin] trang chưa trả dữ liệu video, chờ {_CRAWL_RETRY_DELAY:.0f}s rồi mở lại...")
            await asyncio.sleep(_CRAWL_RETRY_DELAY)
    if not video:
        raise RuntimeError(
            f"Trình duyệt không lấy được dữ liệu video cho {url}. "
            "Douyin thường chặn tạm thời khi bị mở liên tục — chờ ít phút rồi chạy lại."
        )

    filepath = out_dir / "index.mp4"
    candidates = video.get("download_urls") or [video["download_url"]]
    last_error: Exception | None = None
    for i, link in enumerate(candidates):
        try:
            await _download(link, filepath)
        except Exception as e:
            # Douyin có nhiều CDN cho cùng video, có cái chỉ cho phát trong trình
            # duyệt (403) -> thử link kế tiếp thay vì bỏ cuộc.
            last_error = e
            _log(f"[douyin] link {i + 1}/{len(candidates)} lỗi ({str(e)[:80]}), thử link khác...")
            continue
        _log(f"[douyin] tải xong qua trình duyệt: {filepath.stat().st_size // 1024} KB")
        return {"title": video["title"], "extractor": "douyin-browser"}

    raise RuntimeError(f"Mọi link CDN của video đều tải lỗi. Lỗi cuối: {last_error}")


async def _download(link: str, filepath: Path) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            link, headers=DOUYIN_HEADERS, timeout=aiohttp.ClientTimeout(total=600, sock_read=60)
        ) as resp:
            resp.raise_for_status()
            async with aiofiles.open(filepath, "wb") as f:
                async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                    await f.write(chunk)
