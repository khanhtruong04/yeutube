"""
ElevenLabs Text-to-Speech adapter.

Config (env):
  ELEVENLABS_API_KEY   API key
  ELEVENLABS_MODEL_ID  Model (mặc định eleven_multilingual_v2)

Usage:
  from backend.voices.elevenlabs import run_tts
  await run_tts(text="Xin chào", voice_code="w2KTJ6MO4SIK6nWK4YH8", output="out.mp3")

CLI:
  python -m backend.voices.elevenlabs "Xin chào" --voice w2KTJ6MO4SIK6nWK4YH8
"""

import os
import sys
from pathlib import Path

import httpx

DEFAULT_MODEL_ID = "eleven_multilingual_v2"
BASE_URL = "https://api.elevenlabs.io"


def _cfg(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


async def run_tts(
    text: str,
    *,
    voice_code: str,
    output: str | None = None,
    model_id: str | None = None,
    log=None,
) -> dict:
    """
    Gọi ElevenLabs TTS API.

    Args:
        text:       Nội dung cần đọc.
        voice_code: ElevenLabs voice_id (xem voice/elevenlabs.csv).
        output:     Đường dẫn file output.
        model_id:   Override model (mặc định ELEVENLABS_MODEL_ID hoặc eleven_multilingual_v2).
        log:        Callable(msg) để in log.

    Returns:
        { output_file, bytes, mode }
    """
    if not text or not text.strip():
        raise ValueError("text is required")
    if not voice_code:
        raise ValueError("voice_code is required")

    api_key = _cfg("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("Missing ELEVENLABS_API_KEY env var.")

    _log = log or (lambda _: None)
    model = model_id or _cfg("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID)
    out_file = output or f"output_{__import__('time').time_ns()}.mp3"

    _log(f"[elevenlabs] {len(text.strip())} chars → {out_file} (voice={voice_code}, model={model})")

    url = f"{BASE_URL}/v1/text-to-speech/{voice_code}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
    payload = {"text": text.strip(), "model_id": model}

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, headers=headers, json=payload)

    if not resp.is_success:
        raise RuntimeError(f"ElevenLabs TTS [{resp.status_code}]: {resp.text[:500]}")

    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    _log(f"[elevenlabs] saved {len(resp.content):,} bytes → {out_file}")

    return {"output_file": out_file, "bytes": len(resp.content), "mode": "sync"}


async def tts_to_file(
    text: str,
    output: str,
    voice_code: str,
    speed: float | None = None,
) -> None:
    """Drop-in replacement cho edge_tts trong srt_to_mp4/batch_render."""
    await run_tts(text=text, output=output, voice_code=voice_code)


# ── CLI ────────────────────────────────────────────────────────────────────

def _parse_cli(argv):
    opts = {"text": [], "voice": None, "output": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--voice", "-v") and i + 1 < len(argv):
            opts["voice"] = argv[i + 1]; i += 2
        elif a in ("--output", "-o") and i + 1 < len(argv):
            opts["output"] = argv[i + 1]; i += 2
        elif not a.startswith("--"):
            opts["text"].append(a); i += 1
        else:
            i += 1
    opts["text"] = " ".join(opts["text"])
    return opts


async def _cli_main():
    opts = _parse_cli(sys.argv[1:])
    text = opts["text"].strip()
    if not text:
        print('Usage: python -m backend.voices.elevenlabs "text" --voice <voice_id> [-o out.mp3]',
              file=sys.stderr)
        sys.exit(1)
    try:
        result = await run_tts(text=text, voice_code=opts["voice"], output=opts["output"], log=print)
        print(f"✅ {result['output_file']} ({result['bytes']:,} bytes)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(_cli_main())
