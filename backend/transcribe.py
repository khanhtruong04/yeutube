"""
Whisper transcription dùng faster-whisper.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rich.console import Console

from .store import get_aweme_id_from_path, upsert_caption

console = Console()

_NVIDIA_DLL_DIRS = ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin")
_cuda_dlls_ready = False
_model_cache: tuple[tuple[str, str, str], object] | None = None


def _nvidia_package_dir() -> Path | None:
    """Thư mục gói `nvidia` của chính interpreter đang chạy — hỏi sysconfig thay
    vì đoán đường dẫn venv (venv của project nằm ở backend/.venv, không phải gốc).
    `nvidia` là namespace package nên __file__ là None, phải dùng __path__."""
    import sysconfig

    purelib = sysconfig.get_paths().get("purelib")
    if purelib and (Path(purelib) / "nvidia").is_dir():
        return Path(purelib) / "nvidia"
    try:
        import nvidia
        for entry in getattr(nvidia, "__path__", []):
            if Path(entry).is_dir():
                return Path(entry)
    except ImportError:
        pass
    return None


def _setup_cuda_dlls() -> None:
    """Cho Windows thấy các DLL CUDA nằm trong site-packages/nvidia/*/bin.

    Không có bước này, CTranslate2 báo "Library cublas64_12.dll is not found"
    dù gói nvidia-cublas-cu12 đã cài. Lưu ý: os.add_dll_directory() một mình
    KHÔNG đủ (đã thử) — bắt buộc phải có trong PATH thì CTranslate2 mới nạp được.
    """
    global _cuda_dlls_ready
    if _cuda_dlls_ready or sys.platform != "win32":
        return
    base = _nvidia_package_dir()
    if base is None:
        return
    dirs = [base / d for d in _NVIDIA_DLL_DIRS if (base / d).is_dir()]
    if not dirs:
        return
    for p in dirs:
        os.add_dll_directory(str(p))
    os.environ["PATH"] = os.pathsep.join(str(p) for p in dirs) + os.pathsep + os.environ.get("PATH", "")
    _cuda_dlls_ready = True


def _devices_to_try() -> list[tuple[str, str]]:
    """Danh sách (device, compute_type) theo thứ tự ưu tiên. GPU nhanh hơn CPU
    khoảng 4 lần với model 'base' và 9 lần với 'small' (đo trên RTX 3050).
    Đặt WHISPER_DEVICE=cpu trong .env để ép chạy CPU."""
    forced = (os.environ.get("WHISPER_DEVICE") or "").strip().lower()
    if forced == "cpu":
        return [("cpu", "int8")]
    if forced == "cuda":
        return [("cuda", "float16")]

    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return [("cuda", "float16"), ("cpu", "int8")]
    except Exception:
        pass
    return [("cpu", "int8")]


def _check_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _extract_audio(video_path: str, audio_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", "-f", "wav", audio_path],
        capture_output=True, check=True,
    )


def _get_model(model: str, device: str, compute_type: str):
    """Giữ lại model đã nạp để job sau khỏi nạp lại (mất vài giây mỗi lần).

    Chỉ giữ 1 model: model lớn chiếm nhiều VRAM mà card chỉ có 4GB, ôm nhiều bản
    cùng lúc dễ hết bộ nhớ."""
    global _model_cache
    key = (model, device, compute_type)
    if _model_cache is not None and _model_cache[0] == key:
        return _model_cache[1]

    from faster_whisper import WhisperModel

    console.print(f"[cyan]Load faster-whisper '{model}' trên {device} ({compute_type})...[/cyan]")
    m = WhisperModel(model, device=device, compute_type=compute_type)
    _model_cache = (key, m)
    return m


def _transcribe_on(audio_path: str, model: str, language: str | None, device: str, compute_type: str) -> dict:
    m = _get_model(model, device, compute_type)
    console.print("[cyan]Đang transcribe...[/cyan]")
    segments, info = m.transcribe(
        audio_path, language=language, beam_size=5,
        word_timestamps=False,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 500},
    )

    # faster-whisper trả generator lười — phải duyệt hết ở đây thì lỗi CUDA mới
    # lộ ra bên trong khối try của _run_faster_whisper để còn kịp lùi về CPU.
    result_segments = []
    full_text_parts = []
    for seg in segments:
        result_segments.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        })
        full_text_parts.append(seg.text.strip())

    console.print(f"[dim]Detected language: {info.language} (prob={info.language_probability:.2f})[/dim]")
    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "text": " ".join(full_text_parts).strip(),
        "segments": result_segments,
    }


def _run_faster_whisper(audio_path: str, model: str, language: str | None) -> dict:
    _setup_cuda_dlls()
    attempts = _devices_to_try()
    last_error: Exception | None = None
    for device, compute_type in attempts:
        try:
            return _transcribe_on(audio_path, model, language, device, compute_type)
        except Exception as e:
            last_error = e
            console.print(f"[yellow]Whisper trên {device} lỗi: {str(e)[:150]}[/yellow]")
    raise last_error if last_error else RuntimeError("Không chạy được Whisper.")


def _get_video_folder(video_path: Path) -> Path | None:
    """Trả về folder chứa video nếu theo cấu trúc mới (parent là folder tên video)."""
    parent = video_path.parent
    # Cấu trúc mới: downloads/jingxuan/{folder}/index.mp4
    if video_path.name == "index.mp4":
        return parent
    # Cấu trúc cũ: flat file — không có folder riêng
    return None


async def transcribe_video(
    video_path: str,
    model: str = "large-v3-turbo",
    language: str | None = None,
    aweme_id: str | None = None,
    update_index: bool = True,
) -> dict:
    """update_index=False để bỏ qua việc ghi index.csv — web app dùng jobs.db riêng,
    không nên trộn job web vào index.csv của CLI."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {video_path}")
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg chưa cài. Chạy: brew install ffmpeg")

    vid_id = aweme_id or get_aweme_id_from_path(video_path) or path.stem
    console.print(f"[yellow]Video:[/yellow] {path.name}  [yellow]aweme_id:[/yellow] {vid_id}  [yellow]Model:[/yellow] {model}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    try:
        console.print("[cyan]Trích xuất audio...[/cyan]")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _extract_audio, video_path, audio_path)
        result = await loop.run_in_executor(None, _run_faster_whisper, audio_path, model, language)
    finally:
        Path(audio_path).unlink(missing_ok=True)

    # Lưu transcript.json vào folder nếu theo cấu trúc mới
    folder = _get_video_folder(path)
    if folder:
        transcript_path = folder / "transcript.json"
        transcript_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        console.print(f"[green]Đã lưu transcript.json → {transcript_path}[/green]")

    caption = result["text"]
    console.print(f"\n[green]Caption:[/green]\n{caption}\n")
    if update_index:
        await upsert_caption(aweme_id=vid_id, caption=caption)
        console.print("[green]Đã cập nhật index.csv[/green]")
    return result
