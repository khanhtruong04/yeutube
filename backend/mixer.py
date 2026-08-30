"""
Sinh SRT + trộn audio/ghép video — tách từ script inline trong skill voice-over
(bước 5, 6) thành hàm dùng chung cho pipeline web.
"""
import json
from pathlib import Path

from .proc_util import run_command


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_srt(transcript: dict, srt_path: str) -> int:
    """Sinh file .srt từ transcript (dict có segments[].start/end/text). Trả về số dòng."""
    segments = transcript.get("segments", [])
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(
            f"{i}\n{_fmt_srt_time(seg['start'])} --> {_fmt_srt_time(seg['end'])}\n{seg['text'].strip()}\n"
        )
    Path(srt_path).parent.mkdir(parents=True, exist_ok=True)
    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    return len(segments)


def generate_srt_from_file(transcript_path: str, srt_path: str) -> int:
    transcript = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
    return generate_srt(transcript, srt_path)


async def _duration(path: str) -> float | None:
    """Độ dài (giây) của file media qua ffprobe. None nếu không đọc được."""
    code, stdout, _ = await run_command([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    if code != 0:
        return None
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return None


async def probe_video(path: str) -> dict:
    """Trả về {width, height, duration} của file video qua ffprobe."""
    code, stdout, stderr = await run_command([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", path,
    ])
    if code != 0:
        raise RuntimeError(f"ffprobe lỗi: {stderr.decode(errors='replace')[-500:]}")
    data = json.loads(stdout.decode())
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "duration": float(fmt.get("duration", 0)),
    }


async def dub_audio_filter(video_path: str, dub_path: str, volume_dub: float, fit_to_video: bool = True) -> str:
    """Sinh filter cho stream audio dub (dùng chung bởi mix_and_mux và render.py):
    tự thêm atempo nếu dub dài hơn video, để không bị dư audio khi ghép."""
    dub_filter = f"volume={volume_dub}"
    if fit_to_video:
        video_dur = await _duration(video_path)
        dub_dur = await _duration(dub_path)
        if video_dur and dub_dur and dub_dur > video_dur:
            tempo = min(2.0, dub_dur / video_dur)
            dub_filter = f"atempo={tempo:.4f},volume={volume_dub}"
    return dub_filter


async def mix_and_mux(
    video_path: str,
    dub_path: str,
    output_path: str,
    volume_goc: float = 0.10,
    volume_dub: float = 1.0,
    fit_to_video: bool = True,
) -> None:
    """
    Trộn audio gốc (volume_goc) + audio dub (volume_dub) rồi ghép vào video gốc.
    Tương đương lệnh ffmpeg ở bước 6 skill voice-over, nhưng tham số hoá volume.

    fit_to_video: giọng đọc dịch thường dài hơn audio gốc (vd. 283s dub cho video
    221s) -> phần dư sẽ chạy khi video đã hết hình. Bật cờ này để tăng tốc dub
    bằng atempo cho vừa độ dài video. Clamp trong [1.0, 2.0]: atempo chỉ nhận
    0.5–2.0, và đọc quá nhanh sẽ khó nghe.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    dub_filter = await dub_audio_filter(video_path, dub_path, volume_dub, fit_to_video)

    filter_complex = (
        f"[0:a]volume={volume_goc}[orig];"
        f"[1:a]{dub_filter}[dub];"
        "[orig][dub]amix=inputs=2:normalize=0[mix]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", dub_path,
        "-filter_complex", filter_complex,
        "-map", "0:v", "-map", "[mix]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    code, _, stderr = await run_command(cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg lỗi (code {code}): {stderr.decode(errors='replace')[-2000:]}")
