from fastapi import APIRouter
import json
from pathlib import Path

from ...cookies_util import cookie_status

router = APIRouter(tags=["meta"])

LANGUAGES = [
    {"code": "vi", "name": "Tiếng Việt"},
    {"code": "en", "name": "English"},
    {"code": "zh", "name": "中文"},
    {"code": "ja", "name": "日本語"},
    {"code": "ko", "name": "한국어"},
    {"code": "fr", "name": "Français"},
    {"code": "es", "name": "Español"},
    {"code": "th", "name": "ภาษาไทย"},
]

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large", "large-v3-turbo"]


@router.get("/languages")
async def get_languages():
    return LANGUAGES


@router.get("/whisper-models")
async def get_whisper_models():
    return WHISPER_MODELS


@router.get("/cookies/status")
async def get_cookie_status():
    return cookie_status()


def _detect_gender_from_name(name: str) -> str:
    lower = name.lower()
    if any(keyword in lower for keyword in ["woman", "female", "nu", "nữ", "girl", "female", "calmwoman", "việt"]):
        return "female"
    if any(keyword in lower for keyword in ["man", "male", "nam", "boy", "deepman"]):
        return "male"
    return "unknown"


@router.get("/free-voices")
async def get_free_voices():
    """Return list of free voices from the nghitts TTS models.
    Each entry contains `voice_id`, `model_name`, and inferred `gender`.
    """
    # Path relative to project root
    json_path = Path(__file__).parents[3] / "nghitts" / "public" / "tts-model" / "voices.json"
    if not json_path.is_file():
        return []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    voices = []
    for model_key, details in data.items():
        # Use the model_key as voice identifier (e.g., "en_US-libritts_r-medium")
        gender = _detect_gender_from_name(model_key)
        voices.append({
            "voice_id": model_key,
            "model_name": details.get("name", model_key),
            "gender": gender,
        })
    return voices
