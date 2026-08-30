"""
Chuyển cookies JSON (export từ Cookie-Editor / Playwright) sang định dạng
Netscape mà yt-dlp yêu cầu.

Cookie-Editor xuất field `expirationDate`, Playwright xuất `expires` — hỗ trợ cả hai.
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
COOKIES_JSON = PROJECT_ROOT / "cookies_playwright.json"
COOKIES_NETSCAPE = PROJECT_ROOT / "cookies_netscape.txt"


def netscape_cookie_file() -> str | None:
    """Sinh (hoặc cập nhật) file cookie Netscape từ cookies_playwright.json.
    Trả về đường dẫn file, hoặc None nếu không có cookie JSON."""
    if not COOKIES_JSON.exists():
        return None

    try:
        cookies = json.loads(COOKIES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    lines = ["# Netscape HTTP Cookie File", ""]
    for c in cookies:
        try:
            domain = c["domain"]
            name = c["name"]
            value = c["value"]
        except KeyError:
            continue
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path") or "/"
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = int(c.get("expires") or c.get("expirationDate") or 0)
        lines.append("\t".join([domain, include_subdomains, path, secure, str(expires), name, value]))

    COOKIES_NETSCAPE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(COOKIES_NETSCAPE)
