"""
Chuyển cookies JSON (export từ Cookie-Editor / Playwright) sang định dạng
Netscape mà yt-dlp yêu cầu.

Cookie-Editor xuất field `expirationDate`, Playwright xuất `expires` — hỗ trợ cả hai.

QUAN TRỌNG — không được ghi đè thẳng file Netscape bằng nội dung JSON.
Douyin chặn bằng cặp `__ac_nonce` + `__ac_signature`; `__ac_nonce` là nonce chống
bot, sống rất ngắn (~30 phút) và do CHÍNH SERVER trả về qua Set-Cookie. yt-dlp
nhận nó trong lúc tải rồi ghi ngược lại vào file cookie. Bản export tay
(cookies_playwright.json) không bao giờ có cookie này.

Nên nếu mỗi lần chạy đều dựng lại file Netscape từ JSON thì `__ac_nonce` bị xoá
sạch, và Douyin trả đúng lỗi:

    ERROR: [Douyin] <id>: Fresh cookies (not necessarily logged in) are needed

Vì vậy ở đây hợp nhất hai nguồn thay vì ghi đè: lấy hợp của JSON và file Netscape
đang có, bỏ cookie đã hết hạn, file nào MỚI HƠN thì thắng ở những cookie trùng
tên (user vừa export lại -> JSON thắng; yt-dlp vừa làm mới nonce -> file cũ thắng).
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
COOKIES_JSON = PROJECT_ROOT / "cookies_playwright.json"
COOKIES_NETSCAPE = PROJECT_ROOT / "cookies_netscape.txt"

_HTTPONLY = "#HttpOnly_"

# Khoá định danh một cookie theo đúng chuẩn: cùng domain + path + name mới là
# cùng một cookie.
Key = tuple[str, str, str]


def _alive(expires: int) -> bool:
    """expires = 0 -> cookie phiên, không có hạn -> luôn giữ."""
    return expires <= 0 or expires > time.time()


def _normalize_expires(raw) -> int:
    """Netscape format chỉ hiểu `0` là cookie phiên. Playwright lại xuất `-1`
    cho cookie phiên (không phải `0`) -> phải ép về 0, nếu không yt-dlp bỏ qua
    thẳng dòng đó khi đọc lại ('invalid expires at -1'), mất luôn cookie."""
    value = int(float(raw or 0))
    return max(0, value)


def _load_json_cookies() -> dict[Key, list[str]]:
    if not COOKIES_JSON.exists():
        return {}
    try:
        cookies = json.loads(COOKIES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    out: dict[Key, list[str]] = {}
    for c in cookies:
        try:
            domain, name, value = c["domain"], c["name"], c["value"]
        except (KeyError, TypeError):
            continue
        expires = _normalize_expires(c.get("expires") or c.get("expirationDate"))
        if not _alive(expires):
            continue
        path = c.get("path") or "/"
        out[(domain, path, name)] = [
            domain,
            "TRUE" if domain.startswith(".") else "FALSE",
            path,
            "TRUE" if c.get("secure") else "FALSE",
            str(expires),
            name,
            value,
        ]
    return out


def _load_netscape_cookies() -> dict[Key, list[str]]:
    """Đọc lại file Netscape hiện có — nguồn duy nhất giữ được `__ac_nonce`/`ttwid`
    mà yt-dlp làm mới sau mỗi lần tải."""
    if not COOKIES_NETSCAPE.exists():
        return {}
    try:
        raw = COOKIES_NETSCAPE.read_text(encoding="utf-8")
    except OSError:
        return {}

    out: dict[Key, list[str]] = {}
    for line in raw.splitlines():
        # yt-dlp đánh dấu cookie HttpOnly bằng tiền tố `#HttpOnly_`, vẫn là dòng
        # dữ liệu chứ không phải comment.
        if line.startswith("#") and not line.startswith(_HTTPONLY):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        try:
            expires = _normalize_expires(fields[4])
        except ValueError:
            continue
        if not _alive(expires):
            continue
        fields[4] = str(expires)   # dọn -1 còn sót lại từ file cũ trước khi sửa
        domain = fields[0].removeprefix(_HTTPONLY)
        out[(domain, fields[2], fields[5])] = fields
    return out


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def netscape_cookie_file() -> str | None:
    """Hợp nhất cookies_playwright.json với file Netscape đang có rồi ghi ra
    cookies_netscape.txt. Trả về đường dẫn file, hoặc None nếu không có cookie nào."""
    from_json = _load_json_cookies()
    from_file = _load_netscape_cookies()
    if not from_json and not from_file:
        return None

    # File nào mới hơn thì thắng ở cookie trùng tên; cookie chỉ có ở một bên thì
    # giữ nguyên. Cập nhật sau ghi đè lên cập nhật trước.
    if _mtime(COOKIES_JSON) > _mtime(COOKIES_NETSCAPE):
        merged = {**from_file, **from_json}
    else:
        merged = {**from_json, **from_file}

    lines = ["# Netscape HTTP Cookie File", ""]
    lines += ["\t".join(fields) for fields in merged.values()]
    COOKIES_NETSCAPE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(COOKIES_NETSCAPE)


# Cookie định danh phiên đăng nhập thật — có mặt và còn hạn thì coi là "đã đăng
# nhập". __ac_nonce/ttwid chỉ là thách đố chống bot, không nói lên gì về đăng nhập.
_AUTH_COOKIE_NAMES = {"sessionid", "sid_guard", "sid_tt"}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def cookie_status() -> dict:
    """Cookie đăng nhập Douyin còn hạn không, dùng cho banner cảnh báo ở UI.

    Chỉ đọc cookies_playwright.json (nguồn user export tay) — không đọc
    cookies_netscape.txt vì file đó luôn có __ac_nonce mới do yt-dlp tự ghi lại
    sau mỗi lần chạy, sẽ khiến trạng thái luôn báo "ổn" dù sessionid đã chết.

    Chỉ xét hạn ghi trong file, không suy ra từ việc tải lỗi: lỗi "Fresh cookies"
    của yt-dlp là do Douyin chặn ở tầng chữ ký chống-bot chứ không phải cookie
    hỏng (douyin_fallback.py), lấy nó làm tín hiệu thì banner báo sai suốt.
    """
    auth = {
        key: fields
        for key, fields in _load_json_cookies().items()
        if key[2] in _AUTH_COOKIE_NAMES
    }
    updated_at = _iso(_mtime(COOKIES_JSON)) if COOKIES_JSON.exists() else None

    if not auth:
        return {
            "ok": False,
            "reason": "missing",
            "message": "Chưa có cookie đăng nhập Douyin (sessionid/sid_guard) trong cookies_playwright.json.",
            "expires_at": None,
            "updated_at": updated_at,
        }

    expires_values = [int(fields[4]) for fields in auth.values() if int(fields[4]) > 0]
    expires_at = min(expires_values) if expires_values else None

    if expires_at is not None and expires_at <= time.time():
        return {
            "ok": False,
            "reason": "expired",
            "message": "Cookie đăng nhập Douyin đã hết hạn (theo `expires` trong file). Hãy export lại từ trình duyệt.",
            "expires_at": _iso(expires_at),
            "updated_at": updated_at,
        }

    return {
        "ok": True,
        "reason": None,
        "message": None,
        "expires_at": _iso(expires_at) if expires_at else None,
        "updated_at": updated_at,
    }
