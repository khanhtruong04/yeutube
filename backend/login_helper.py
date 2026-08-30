"""
Mở browser thật (không headless) để đăng nhập Douyin bằng tay 1 lần, sau đó lưu
cookies ra cookies_playwright.json (đúng format Playwright) cho crawler dùng lại.

Chạy từ project root:
  backend/.venv/Scripts/python -m backend.login_helper
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).parent.parent
COOKIES_OUT = PROJECT_ROOT / "cookies_playwright.json"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded")

        print("\n" + "=" * 60)
        print("Cửa sổ Chrome đã mở. Đăng nhập Douyin bằng tay (quét QR hoặc SMS).")
        print("Đăng nhập xong (thấy avatar/tên tài khoản góc trên) thì quay lại")
        print("đây, nhấn Enter để lưu cookies.")
        print("=" * 60 + "\n")

        await asyncio.to_thread(input, "Nhấn Enter sau khi đăng nhập xong... ")

        cookies = await context.cookies()
        COOKIES_OUT.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã lưu {len(cookies)} cookies -> {COOKIES_OUT}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
