from fastapi import APIRouter

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
