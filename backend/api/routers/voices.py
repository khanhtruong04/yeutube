import asyncio
import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ...voices import registry

router = APIRouter(tags=["voices"])

PREVIEW_TEXT = (
    "Chúc bạn một ngày mới tràn đầy năng lượng, luôn vui vẻ, gặp nhiều may mắn, "
    "làm gì cũng thuận lợi và mỗi khoảnh khắc đều ngập tràn niềm vui!"
)
PREVIEW_DIR = Path(__file__).parents[3] / "downloads" / "voice_previews"

# Mỗi voice chỉ được tổng hợp 1 lần cùng lúc (tránh bấm liên tục sinh nhiều lệnh TTS).
_preview_locks: dict[str, asyncio.Lock] = {}


@router.get("/providers")
async def get_providers():
    return registry.available_providers()


@router.get("/voices")
async def get_voices(provider: str):
    return registry.list_voices(provider)


@router.get("/voices/preview")
async def preview_voice(voice_id: str, provider: str = "nghitts"):
    """Nghe thử giọng đọc: đọc 1 câu mẫu, cache file mp3 theo (provider, voice, câu mẫu)."""
    if provider not in registry.PROVIDERS:
        raise HTTPException(400, f"Provider không hỗ trợ: {provider}")

    key = hashlib.sha1(f"{provider}|{voice_id}|{PREVIEW_TEXT}".encode("utf-8")).hexdigest()[:16]
    out_path = PREVIEW_DIR / f"{key}.mp3"

    if not out_path.exists() or out_path.stat().st_size == 0:
        lock = _preview_locks.setdefault(key, asyncio.Lock())
        async with lock:
            if not out_path.exists() or out_path.stat().st_size == 0:
                PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
                tmp_path = out_path.with_name(f"{key}.tmp.mp3")
                try:
                    await registry.run_tts(
                        provider, PREVIEW_TEXT, voice_code=voice_id, output=str(tmp_path)
                    )
                    tmp_path.replace(out_path)
                except Exception as e:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(502, f"Không tạo được giọng nghe thử: {str(e)[:200]}")

    return FileResponse(out_path, media_type="audio/mpeg")
