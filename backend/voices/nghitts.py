"""
NghiTTS (Piper TTS) adapter — Miễn phí, offline, không cần API key.
Sử dụng các mô hình giọng tiếng Việt chất lượng cao từ nghitts (https://nghitts.app).

Usage:
  from backend.voices.nghitts import run_tts
  await run_tts(text="Xin chào", voice_code="Ngọc Huyền (mới)", output="out.mp3")

CLI:
  python -m backend.voices.nghitts "Xin chào" --voice "Ngọc Huyền (mới)" -o out.mp3
"""

import asyncio
import os
from pathlib import Path
import sys
import tempfile
import urllib.parse
import urllib.request
import wave

import piper

from ..proc_util import run_command

DEFAULT_VOICE = "Ngọc Huyền (mới)"

PROJECT_ROOT = Path(__file__).parent.parent.parent
MODEL_DIRS = [
    PROJECT_ROOT / "models" / "piper",
    PROJECT_ROOT / "nghitts" / "public" / "tts-model" / "vi",
]

# Aliases hỗ trợ các mã cũ / không dấu
VOICE_ALIASES = {
    "ngocngan3701": "Ngọc Ngạn",
    "mytam": "Mỹ Tâm",
    "vietthao3886": "Việt Thảo",
    "tranthanh": "Trấn Thành",
    "oryx": "Duy Oryx",
    "cuthuvien": "Ban Mai",
    "calmwoman3688": "Ban Mai",
    "deepman3909": "Minh Khang",
}

# Cache PiperVoice đã tải vào RAM để các câu tiếp theo chạy cực nhanh (~80ms/câu)
_VOICE_CACHE: dict[str, piper.PiperVoice] = {}
_LOCK = asyncio.Lock()


def resolve_voice_code(voice_code: str | None) -> str:
    if not voice_code:
        return DEFAULT_VOICE
    cleaned = voice_code.strip()
    return VOICE_ALIASES.get(cleaned.lower(), cleaned)


def _find_local_model(model_name: str) -> tuple[Path, Path] | None:
    """Tìm file .onnx và .onnx.json trong các thư mục model local."""
    for mdir in MODEL_DIRS:
        onnx_file = mdir / f"{model_name}.onnx"
        json_file = mdir / f"{model_name}.onnx.json"
        if onnx_file.exists() and json_file.exists():
            return onnx_file, json_file
    return None


def _safe_log(log_fn, msg: str) -> None:
    if not log_fn:
        return
    try:
        log_fn(msg)
    except UnicodeEncodeError:
        try:
            log_fn(msg.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


def _download_file(url: str, dest_path: Path, log=None) -> None:
    """Tải 1 file từ URL về dest_path an toàn bằng file tạm."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(temp_dest, "wb") as f:
            while chunk := resp.read(1024 * 1024):
                f.write(chunk)
        temp_dest.replace(dest_path)
    except Exception as e:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)
        raise RuntimeError(f"Lỗi tải model Piper từ {url}: {e}") from e


def _ensure_model_sync(model_name: str, log=None) -> tuple[Path, Path]:
    """Đảm bảo model có sẵn ở local, nếu chưa có thì tải từ R2 / nghitts.app CDN."""
    found = _find_local_model(model_name)
    if found:
        return found

    target_dir = MODEL_DIRS[0]
    target_dir.mkdir(parents=True, exist_ok=True)

    onnx_file = target_dir / f"{model_name}.onnx"
    json_file = target_dir / f"{model_name}.onnx.json"

    enc_name = urllib.parse.quote(model_name)
    base_url = f"https://nghitts.app/api/model/{enc_name}"

    if not json_file.exists():
        _safe_log(log, f"[nghitts] Đang tải config model '{model_name}'...")
        _download_file(f"{base_url}.onnx.json", json_file, log=log)

    if not onnx_file.exists():
        _safe_log(log, f"[nghitts] Đang tải trọng số model '{model_name}' (~60MB, chỉ tải 1 lần duy nhất)...")
        _download_file(f"{base_url}.onnx", onnx_file, log=log)

    return onnx_file, json_file


def _synthesize_to_wav(voice: piper.PiperVoice, text: str, wav_path: Path, speed: float | None = None) -> None:
    """Tổng hợp tiếng ra file WAV (chạy trong worker thread)."""
    length_scale = (1.0 / speed) if (speed and speed > 0) else 1.0
    syn_config = piper.SynthesisConfig(length_scale=length_scale)

    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        for chunk in voice.synthesize(text, syn_config=syn_config):
            wav_file.writeframes(chunk.audio_int16_bytes)


async def run_tts(
    text: str,
    *,
    voice_code: str | None = None,
    speed: float | None = None,
    output: str | None = None,
    log=None,
) -> dict:
    """Gọi Piper TTS với giọng tiếng Việt từ NghiTTS."""
    if not text or not text.strip():
        raise ValueError("text is required")

    model_name = resolve_voice_code(voice_code)
    out_file = output or f"output_{__import__('time').time_ns()}.mp3"
    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Đảm bảo model đã được tải về
    onnx_path, json_path = await asyncio.to_thread(_ensure_model_sync, model_name, log)

    # 2. Lấy PiperVoice từ cache hoặc load mới
    async with _LOCK:
        if model_name not in _VOICE_CACHE:
            _safe_log(log, f"[nghitts] Đang nạp model '{model_name}' vào bộ nhớ...")
            voice = await asyncio.to_thread(piper.PiperVoice.load, str(onnx_path), str(json_path))
            _VOICE_CACHE[model_name] = voice
        else:
            voice = _VOICE_CACHE[model_name]

    _safe_log(log, f"[nghitts] {len(text.strip())} chars → {out_file} (voice={model_name}, speed={speed or 1.0})")

    # 3. Tạo file WAV tạm
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        tmp_wav_path = Path(tmp_wav.name)

    try:
        await asyncio.to_thread(_synthesize_to_wav, voice, text.strip(), tmp_wav_path, speed)

        # 4. Chuyển đổi WAV sang output format (mp3 nếu đường dẫn ra là .mp3)
        if out_path.suffix.lower() == ".mp3":
            code, stdout, stderr = await run_command([
                "ffmpeg", "-y", "-i", str(tmp_wav_path), "-b:a", "128k", str(out_path)
            ])
            if code != 0:
                raise RuntimeError(f"ffmpeg chuyển đổi MP3 lỗi: {stderr.decode(errors='replace')[-500:]}")
        else:
            # Nếu output là .wav thì copy thẳng
            import shutil
            shutil.copyfile(tmp_wav_path, out_path)

        size = out_path.stat().st_size
        _safe_log(log, f"[nghitts] saved {size:,} bytes → {out_file}")
        return {"output_file": str(out_path), "bytes": size, "mode": "sync"}
    finally:
        if tmp_wav_path.exists():
            tmp_wav_path.unlink(missing_ok=True)


async def tts_to_file(
    text: str,
    output: str,
    voice_code: str | None = None,
    speed: float | None = None,
) -> None:
    await run_tts(text=text, output=output, voice_code=voice_code, speed=speed)


# ── CLI ────────────────────────────────────────────────────────────────────

def _parse_cli(argv):
    opts = {"text": [], "voice": None, "output": None, "speed": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--voice", "-v") and i + 1 < len(argv):
            opts["voice"] = argv[i + 1]; i += 2
        elif a in ("--output", "-o") and i + 1 < len(argv):
            opts["output"] = argv[i + 1]; i += 2
        elif a in ("--speed", "-s") and i + 1 < len(argv):
            opts["speed"] = float(argv[i + 1]); i += 2
        elif not a.startswith("--"):
            opts["text"].append(a); i += 1
        else:
            i += 1
    opts["text"] = " ".join(opts["text"])
    return opts


async def _cli_main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    opts = _parse_cli(sys.argv[1:])
    text = opts["text"].strip()
    if not text:
        print('Usage: python -m backend.voices.nghitts "text" [--voice "Ngọc Huyền (mới)"] [-o out.mp3]',
              file=sys.stderr)
        sys.exit(1)
    try:
        result = await run_tts(
            text=text, voice_code=opts["voice"], speed=opts["speed"], output=opts["output"], log=print
        )
        print(f"✅ {result['output_file']} ({result['bytes']:,} bytes)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(_cli_main())
