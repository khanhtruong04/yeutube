"""
Sinh đoạn ffmpeg filter_complex để che (mask) vùng trên video theo khoảng thời
gian — dùng bởi backend/render.py.

Mask dict kỳ vọng các key: x, y, w, h (phân số 0-1 của khung hình), t_start,
t_end (giây), type ("blur" | "solid"), color (chỉ dùng khi type="solid").
"""


def _clamp_box(x_frac: float, y_frac: float, w_frac: float, h_frac: float, video_w: int, video_h: int):
    w = max(2, round(w_frac * video_w))
    h = max(2, round(h_frac * video_h))
    x = min(max(0, round(x_frac * video_w)), video_w - w)
    y = min(max(0, round(y_frac * video_h)), video_h - h)
    return x, y, w, h


def build_mask_filters(
    masks: list[dict],
    video_w: int,
    video_h: int,
    input_label: str = "0:v",
    output_label: str = "vmasked",
) -> str:
    """Trả về chuỗi filter_complex (không có dấu ';' cuối) áp toàn bộ mask lên
    stream video, mỗi mask chỉ hiện trong khoảng [t_start, t_end]."""
    if not masks:
        return f"[{input_label}]null[{output_label}]"

    parts: list[str] = []
    cur = input_label
    for i, m in enumerate(masks):
        x, y, w, h = _clamp_box(m["x"], m["y"], m["w"], m["h"], video_w, video_h)
        t_start = max(0, float(m.get("t_start", 0)))
        t_end = float(m.get("t_end", 1e9))
        # trong dấu nháy đơn nên dấu phẩy không cần escape (không đi qua shell,
        # gọi ffmpeg qua subprocess_exec với argv list).
        enable = f"between(t,{t_start:.3f},{t_end:.3f})"
        nxt = f"vm{i}"

        if m.get("type") == "solid":
            color = m.get("color") or "black"
            parts.append(
                f"[{cur}]drawbox=x={x}:y={y}:w={w}:h={h}:color={color}@1.0:t=fill:enable='{enable}'[{nxt}]"
            )
        else:  # blur (mặc định)
            parts.append(f"[{cur}]split=2[base{i}][tocrop{i}]")
            parts.append(f"[tocrop{i}]crop={w}:{h}:{x}:{y},boxblur=12:4[blurred{i}]")
            parts.append(f"[base{i}][blurred{i}]overlay={x}:{y}:enable='{enable}'[{nxt}]")
        cur = nxt

    parts.append(f"[{cur}]null[{output_label}]")
    return ";".join(parts)
