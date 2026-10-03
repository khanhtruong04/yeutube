"""
Douyin crawler: Playwright intercept XHR/fetch, tìm aweme_list trong response.
"""
import asyncio
import json
import re
import sys
from typing import AsyncGenerator
from urllib.parse import urlparse, parse_qs

# Playwright dùng asyncio.create_subprocess_exec để khởi động chromium.
# Trên Windows, lệnh đó chỉ chạy được với ProactorEventLoop, không dùng được
# SelectorEventLoop (mặc định khi uvicorn --reload). Ép policy ở đây đảm bảo
# mọi event loop được tạo ra sau khi import module này đều dùng Proactor.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright, Response
from rich.console import Console

console = Console()

JINGXUAN_URL = "https://www.douyin.com/jingxuan"

# Số giây tối đa chờ trang gọi API chi tiết trong crawl_single_url.
_SINGLE_URL_TIMEOUT = 25

_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-web-security",
]
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_STEALTH_SCRIPT = (
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
)


def _find_aweme_list(data) -> list:
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "aweme_id" in data[0]:
            return data
        for item in data:
            result = _find_aweme_list(item)
            if result:
                return result
    elif isinstance(data, dict):
        for key in ("aweme_list", "item_list", "aweme_info", "data"):
            if key in data:
                result = _find_aweme_list(data[key])
                if result:
                    return result
        for v in data.values():
            if isinstance(v, (dict, list)):
                result = _find_aweme_list(v)
                if result:
                    return result
    return []


def _get_download_urls(video: dict) -> list[str]:
    """Mọi link tải được của video, thứ tự ưu tiên giảm dần.

    Trả về cả danh sách chứ không chỉ link đầu: Douyin có nhiều CDN cho cùng một
    video và không phải cái nào cũng cho tải — host `v3-web-prime` chẳng hạn trả
    403 cho mọi request ngoài trình duyệt, trong khi link khác của chính video đó
    lại tải bình thường."""
    urls: list[str] = []
    for key in ("play_addr", "play_addr_h264", "download_addr", "play_addr_lowbr"):
        for url in (video.get(key) or {}).get("url_list") or []:
            url = re.sub(r"[?&](logo_name|watermark|wm_url)[^&]*", "", url)
            if url not in urls:
                urls.append(url)
    return urls


def _parse_aweme(item: dict) -> dict | None:
    aweme_id = str(item.get("aweme_id") or item.get("id") or "")
    if not aweme_id:
        return None
    desc = (item.get("desc") or "").strip() or f"video_{aweme_id}"
    author_name = (item.get("author") or {}).get("nickname") or "unknown"
    download_urls = _get_download_urls(item.get("video") or {})
    if not download_urls:
        return None
    return {
        "aweme_id": aweme_id,
        "title": desc[:100],
        "author": author_name,
        "download_url": download_urls[0],
        "download_urls": download_urls,
    }


def _is_douyin_api(url: str) -> bool:
    return (
        "douyin.com" in url
        and any(x in url for x in ["/aweme/", "/api/", "/web/"])
        and url.startswith("https")
    )


_SAMESITE_MAP = {
    "no_restriction": "None", "none": "None",
    "lax": "Lax", "unspecified": "Lax",
    "strict": "Strict",
}


def _normalize_cookies(raw: list[dict]) -> list[dict]:
    """Chấp nhận cả 2 format: Playwright native (expires/sameSite='Lax'...) và
    export từ browser extension (expirationDate/sameSite=null|'no_restriction'...).
    Playwright bắt buộc sameSite phải là 'Strict'|'Lax'|'None' (string), không nhận null,
    và bỏ qua field lạ (hostOnly/session/storeId) cũng gây lỗi validate."""
    out = []
    for c in raw:
        cookie = {"name": c["name"], "value": c["value"], "path": c.get("path", "/")}
        if c.get("domain"):
            cookie["domain"] = c["domain"]
        expires = c.get("expires", c.get("expirationDate"))
        if expires is not None:
            cookie["expires"] = float(expires)
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        same_site = c.get("sameSite")
        if isinstance(same_site, str) and same_site.lower() in _SAMESITE_MAP:
            cookie["sameSite"] = _SAMESITE_MAP[same_site.lower()]
        out.append(cookie)
    return out


async def _make_context(p, headless: bool, cookies_file: str | None):
    browser = await p.chromium.launch(headless=headless, args=_BROWSER_ARGS)
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=_USER_AGENT,
        locale="zh-CN",
    )
    await context.add_init_script(_STEALTH_SCRIPT)
    await context.add_init_script(
        "window.addEventListener('DOMContentLoaded', () => localStorage.setItem('douyin_web_hide_guide', '1'))"
    )
    if cookies_file:
        try:
            with open(cookies_file, encoding="utf-8") as f:
                raw_cookies = json.load(f)
            await context.add_cookies(_normalize_cookies(raw_cookies))
            console.print(f"[green]Loaded {len(raw_cookies)} cookies từ {cookies_file}[/green]")
        except Exception as e:
            console.print(f"[yellow]Không load được cookies: {e}[/yellow]")
    return browser, context


async def _run_in_proactor(async_fn, *args, **kwargs):
    """Trên Windows, khi Uvicorn chạy với --reload (hoặc khi event loop hiện tại là
    SelectorEventLoop), Playwright sẽ crash với NotImplementedError vì
    SelectorEventLoop không hỗ trợ subprocess.
    Hàm này tự động chuyển việc chạy Playwright sang một worker thread riêng với
    ProactorEventLoop, đảm bảo tương thích 100% dù server khởi động bằng lệnh nào.
    """
    if sys.platform != "win32":
        return await async_fn(*args, **kwargs)

    current_loop = asyncio.get_running_loop()
    if isinstance(current_loop, getattr(asyncio, "ProactorEventLoop", ())):
        return await async_fn(*args, **kwargs)

    def in_thread():
        proactor_loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(proactor_loop)
        try:
            return proactor_loop.run_until_complete(async_fn(*args, **kwargs))
        finally:
            try:
                pending = asyncio.all_tasks(proactor_loop)
                for task in pending:
                    task.cancel()
                if pending:
                    proactor_loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            proactor_loop.close()

    return await asyncio.to_thread(in_thread)


async def _crawl_impl(
    start_url: str,
    max_videos: int,
    scroll_count: int,
    headless: bool,
    cookies_file: str | None,
    stop_when_no_new: int = 6,
) -> list[dict]:
    collected: dict[str, dict] = {}

    async with async_playwright() as p:
        browser, context = await _make_context(p, headless, cookies_file)
        page = await context.new_page()

        async def handle_response(response: Response):
            if len(collected) >= max_videos or not _is_douyin_api(response.url):
                return
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                data = await response.json()
                items = _find_aweme_list(data)
                new_count = 0
                for item in items:
                    v = _parse_aweme(item)
                    if v and v["aweme_id"] not in collected:
                        collected[v["aweme_id"]] = v
                        new_count += 1
                if new_count:
                    short_url = response.url.split("?")[0].replace("https://www.douyin.com", "")
                    console.print(
                        f"[green]+{new_count} video[/green] từ [dim]{short_url}[/dim] "
                        f"(tổng: {len(collected)})"
                    )
            except Exception:
                pass

        page.on("response", handle_response)
        console.print(f"[cyan]Mở trang {start_url}...[/cyan]")
        try:
            await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            console.print(f"[yellow]Timeout (bình thường): {e}[/yellow]")

        await page.wait_for_timeout(4000)
        await page.evaluate("""
            localStorage.setItem('douyin_web_hide_guide', '1');
            document.querySelectorAll('[id^="login-full-panel-"]').forEach(el => el.remove());
        """)

        prev, no_new = 0, 0
        for i in range(scroll_count):
            if len(collected) >= max_videos:
                break
            if no_new >= stop_when_no_new:
                console.print("[yellow]Không tìm thêm được video mới, dừng scroll.[/yellow]")
                break
            await page.evaluate("""
                document.querySelectorAll('[id^="login-full-panel-"]').forEach(el => el.remove());
                window.scrollTo(0, document.documentElement.scrollHeight);
            """)
            await page.wait_for_timeout(3500)
            console.print(f"[dim]Scroll {i+1}/{scroll_count} — {len(collected)} video[/dim]")
            if len(collected) == prev:
                no_new += 1
            else:
                no_new, prev = 0, len(collected)

        await browser.close()

    return list(collected.values())[:max_videos]


async def _crawl(
    start_url: str,
    max_videos: int,
    scroll_count: int,
    headless: bool,
    cookies_file: str | None,
    stop_when_no_new: int = 6,
) -> list[dict]:
    return await _run_in_proactor(
        _crawl_impl,
        start_url,
        max_videos,
        scroll_count,
        headless,
        cookies_file,
        stop_when_no_new,
    )


async def crawl_jingxuan(
    max_videos: int = 50,
    scroll_count: int = 15,
    headless: bool = True,
    cookies_file: str | None = None,
    start_url: str = JINGXUAN_URL,
) -> AsyncGenerator[dict, None]:
    for v in await _crawl(start_url, max_videos, scroll_count, headless, cookies_file):
        yield v


async def crawl_user_profile(
    user_url: str,
    max_videos: int = 100,
    headless: bool = True,
    cookies_file: str | None = None,
) -> AsyncGenerator[dict, None]:
    console.print(f"[cyan]Mở profile: {user_url}[/cyan]")
    for v in await _crawl(user_url, max_videos, 30, headless, cookies_file, stop_when_no_new=5):
        yield v


async def _crawl_single_url_impl(
    url: str,
    headless: bool = True,
    cookies_file: str | None = None,
) -> dict | None:
    parsed = urlparse(url)
    modal_id = parse_qs(parsed.query).get("modal_id", [None])[0]

    # Nếu URL dạng /video/{id} thì lấy id từ path
    if not modal_id and "/video/" in parsed.path:
        modal_id = parsed.path.split("/video/")[-1].split("?")[0].strip("/") or None

    collected: dict[str, dict] = {}

    async with async_playwright() as p:
        browser, context = await _make_context(p, headless, cookies_file)
        page = await context.new_page()

        async def handle_response(response: Response):
            if not _is_douyin_api(response.url):
                return
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                data = await response.json()
                detail = data.get("aweme_detail") or data.get("item_info", {})
                if detail and "aweme_id" in detail:
                    v = _parse_aweme(detail)
                    if v:
                        collected[v["aweme_id"]] = v
                        return
                for item in _find_aweme_list(data):
                    v = _parse_aweme(item)
                    if v:
                        if modal_id and v["aweme_id"] == modal_id:
                            collected[modal_id] = v
                        elif modal_id not in collected:
                            collected[v["aweme_id"]] = v
            except Exception:
                pass

        page.on("response", handle_response)
        console.print(f"[cyan]Mở {url}[/cyan]")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        # Chờ đến khi bắt được video rồi mới đóng, thay vì ngủ cứng 5 giây:
        # response API chi tiết có khi về chậm hơn thế (mạng chậm, trang nặng)
        # và lúc đó hàm trả về tay không dù trang vẫn đang tải bình thường.
        for _ in range(_SINGLE_URL_TIMEOUT):
            if collected.get(modal_id) if modal_id else collected:
                break
            await page.wait_for_timeout(1000)
        await browser.close()

    if modal_id and modal_id in collected:
        return collected[modal_id]
    return next(iter(collected.values()), None)


async def crawl_single_url(
    url: str,
    headless: bool = True,
    cookies_file: str | None = None,
) -> dict | None:
    return await _run_in_proactor(
        _crawl_single_url_impl,
        url=url,
        headless=headless,
        cookies_file=cookies_file,
    )

