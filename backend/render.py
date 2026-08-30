"""
Render cuối cùng cho pipeline có mask + burn-in subtitle: 1 lệnh ffmpeg áp mask
(mask_overlay) + subtitle (subtitle_burn) lên video, trộn audio (như mixer.mix_and_mux)
rồi xuất ra output_vi.mp4. Không dùng -c:v copy được nữa vì có filter video.
"""
from pathlib import Path

from .mask_overlay import build_mask_filters
from .mixer import dub_audio_filter
from .proc_util import run_command


def _escape_subtitles_path(path: str) -> str:
    """ffmpeg subtitles= filter cần path dùng '/' và escape ':' sau ổ đĩa Windows
    (nếu không, 'C:' bị hiểu nhầm là phân tách option filter)."""
    p = str(Path(path).resolve()).replace("\\", "/")
    return p.replace(":", "\\:")


async def render_final(
    video_path: str,
    dub_path: str,
    ass_path: str | None,
    masks: list[dict],
    video_w: int,
    video_h: int,
    output_path: str,
    volume_goc: float = 0.10,
    volume_dub: float = 1.0,
    fit_dub_to_video: bool = True,
    upscale_to: int | None = None,
) -> None:
    """ass_path=None -> bỏ qua burn-in subtitle (user tắt "hiển thị text đã dịch"),
    chỉ áp mask + trộn audio. fit_dub_to_video=False khi dub track đã được canh
    đúng độ dài video từ trước (dub_timeline.py canh theo timestamp từng câu) —
    không cần atempo lại lần nữa.

    upscale_to: phóng khung hình lên cho cạnh ngắn đạt mức này (vd. 1080) khi
    video gốc nhỏ hơn. Chỉ kéo giãn pixel, KHÔNG thêm chi tiết — chỉ dùng khi
    cần đáp ứng yêu cầu độ phân giải tối thiểu của nơi đăng."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    dub_filter = await dub_audio_filter(video_path, dub_path, volume_dub, fit_to_video=fit_dub_to_video)
    needs_upscale = bool(upscale_to and min(video_w, video_h) < upscale_to)

    # Không mask, không burn phụ đề, không phóng to -> không đụng gì tới khung
    # hình, chỉ trộn audio. Copy thẳng stream video thay vì mã hoá lại: nhanh hơn
    # hàng chục lần và không mất chất lượng.
    if not masks and not ass_path and not needs_upscale:
        await _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dub_path,
            "-filter_complex",
            f"[0:a]volume={volume_goc}[orig];[1:a]{dub_filter}[dub];"
            "[orig][dub]amix=inputs=2:normalize=0[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            output_path,
        ])
        return

    mask_chain = build_mask_filters(masks, video_w, video_h, input_label="0:v", output_label="vmasked")

    parts = [mask_chain]
    last = "vmasked"
    if ass_path:
        ass_escaped = _escape_subtitles_path(ass_path)
        parts.append(f"[{last}]subtitles='{ass_escaped}'[vsub]")
        last = "vsub"

    # Phóng to sau khi đã che + burn phụ đề, để mọi thứ giãn cùng tỉ lệ.
    if needs_upscale:
        # Ép theo cạnh ngắn (đúng cho cả video dọc lẫn ngang); -2 để cạnh còn
        # lại giữ tỉ lệ và luôn là số chẵn — libx264 yuv420p bắt buộc.
        scale = f"scale={upscale_to}:-2" if video_w <= video_h else f"scale=-2:{upscale_to}"
        parts.append(f"[{last}]{scale}[vout]")
    else:
        parts.append(f"[{last}]null[vout]")

    parts.append(f"[0:a]volume={volume_goc}[orig]")
    parts.append(f"[1:a]{dub_filter}[dub]")
    parts.append("[orig][dub]amix=inputs=2:normalize=0[aout]")
    filter_complex = ";".join(parts)

    await _run_ffmpeg([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", dub_path,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ])


async def _run_ffmpeg(cmd: list[str]) -> None:
    code, _, stderr = await run_command(cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg render lỗi (code {code}): {stderr.decode(errors='replace')[-2000:]}")
