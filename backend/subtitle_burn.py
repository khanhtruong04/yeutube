"""
Sinh file .ass (Advanced SubStation Alpha) từ transcript đã dịch + vùng vị trí
(text_layout) để burn-in cứng vào video qua ffmpeg filter `subtitles=`.

Layout zone dict kỳ vọng: x, y (phân số 0-1, TÂM vùng — text canh giữa tại
điểm này), t_start, t_end (giây), font_size?, color? (hex "#RRGGBB").
"""
from pathlib import Path

DEFAULT_ZONE = {"x": 0.5, "y": 0.9, "w": 0.6, "t_start": 0, "t_end": 1e9, "font_size": 28, "color": "#FFFFFF"}


def _fmt_ass_time(seconds: float) -> str:
    seconds = max(0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_to_ass_color(hex_color: str) -> str:
    """'#RRGGBB' -> ASS '&H00BBGGRR' (alpha 00 = đục hoàn toàn)."""
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _active_zone(zones: list[dict], t: float) -> dict:
    for z in zones:
        if z.get("t_start", 0) <= t < z.get("t_end", 1e9):
            return z
    return zones[0] if zones else DEFAULT_ZONE


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\N").replace("{", "\\{").replace("}", "\\}")


def _wrap_text(text: str, max_chars: int) -> str:
    """Xuống dòng thủ công để chữ không tràn ra ngoài bề rộng box người dùng đặt
    (ASS không tự wrap theo pixel, chỉ theo PlayResX toàn màn hình)."""
    if max_chars <= 0:
        return text
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        candidate = f"{cur} {w}".strip()
        if len(candidate) > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def build_ass(
    transcript: dict,
    layout: list[dict],
    video_w: int,
    video_h: int,
    ass_path: str,
) -> int:
    """Sinh file .ass từ segments[].start/end/text + vùng layout đang active
    tại thời điểm mỗi segment. Trả về số dòng dialogue đã ghi."""
    zones = layout or [DEFAULT_ZONE]
    segments = transcript.get("segments", [])

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,28,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        zone = _active_zone(zones, seg["start"])
        x_px = round(zone.get("x", 0.5) * video_w)
        y_px = round(zone.get("y", 0.9) * video_h)
        font_size = zone.get("font_size") or 28
        color = _hex_to_ass_color(zone.get("color") or "#FFFFFF")
        zone_w_px = zone.get("w", 0.6) * video_w
        max_chars = max(4, int(zone_w_px / (font_size * 0.55)))
        wrapped = _wrap_text(text, max_chars)
        override = f"{{\\an5\\pos({x_px},{y_px})\\fs{font_size}\\c{color}}}"
        start = _fmt_ass_time(seg["start"])
        end = _fmt_ass_time(seg["end"])
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{override}{_escape_ass_text(wrapped)}")

    Path(ass_path).parent.mkdir(parents=True, exist_ok=True)
    Path(ass_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines) - 1
