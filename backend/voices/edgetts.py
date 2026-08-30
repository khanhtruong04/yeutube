"""
Microsoft Edge TTS adapter — miễn phí, không cần API key.

Usage:
  from backend.voices.edgetts import run_tts
  await run_tts(text="Xin chào", voice_code="vi-VN-NamMinhNeural", output="out.mp3")

CLI:
  python -m backend.voices.edgetts "Xin chào" --voice vi-VN-NamMinhNeural -o out.mp3
"""

import sys
from pathlib import Path

import edge_tts

DEFAULT_VOICE = "vi-VN-NamMinhNeural"


async def run_tts(
    text: str,
    *,
    voice_code: str | None = None,
    output: str | None = None,
    log=None,
) -> dict:
    """
    Gọi Microsoft Edge TTS.

    Args:
        text:       Nội dung cần đọc.
        voice_code: Voice (vi-VN-NamMinhNeural | vi-VN-HoaiMyNeural | ...).
        output:     Đường dẫn file output.
        log:        Callable(msg) để in log.

    Returns:
        { output_file, bytes, mode }
    """
    if not text or not text.strip():
        raise ValueError("text is required")

    _log = log or (lambda _: None)
    voice = voice_code or DEFAULT_VOICE
    out_file = output or f"output_{__import__('time').time_ns()}.mp3"

    _log(f"[edgetts] {len(text.strip())} chars → {out_file} (voice={voice})")

    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(text.strip(), voice)
    await communicate.save(out_file)

    size = out.stat().st_size
    _log(f"[edgetts] saved {size:,} bytes → {out_file}")

    return {"output_file": out_file, "bytes": size, "mode": "sync"}


async def tts_to_file(
    text: str,
    output: str,
    voice_code: str | None = None,
    speed: float | None = None,
) -> None:
    """Drop-in replacement cho các adapter khác trong srt_to_mp4/batch_render."""
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
        print('Usage: python -m backend.voices.edgetts "text" [--voice vi-VN-NamMinhNeural] [-o out.mp3]',
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
