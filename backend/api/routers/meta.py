from fastapi import APIRouter
import json
import re
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


# ---------------------------------------------------------------------------
# Danh sách giọng đọc Piper TTS từ nghitts (https://nghitts.app)
# voice_id = tên file model (không đuôi .onnx), display_name = tên hiển thị đẹp
# ---------------------------------------------------------------------------
NGHITTS_VI_VOICES = [
    # ── GIỌNG NỮ ────────────────────────────────────────────────────────────
    {
        "voice_id": "Ngọc Huyền (mới)",
        "display_name": "Ngọc Huyền (review phim)",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng review phim của Ngọc Huyền - nữ, phong cách sinh động, cuốn hút",
    },
    {
        "voice_id": "Mỹ Tâm",
        "display_name": "Mỹ Tâm",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng ca sĩ Mỹ Tâm - nữ",
    },
    {
        "voice_id": "Mỹ Tâm Real",
        "display_name": "Mỹ Tâm (Real)",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng ca sĩ Mỹ Tâm bản chân thực - nữ",
    },
    {
        "voice_id": "Ban Mai",
        "display_name": "Ban Mai",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng nữ trong trẻo, tự nhiên, rõ ràng",
    },
    {
        "voice_id": "Mai Phương",
        "display_name": "Mai Phương",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng nữ nhẹ nhàng, truyền cảm",
    },
    {
        "voice_id": "Phương Trang",
        "display_name": "Phương Trang",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng nữ ấm áp, chuẩn mực",
    },
    {
        "voice_id": "Thanh Phương Viettel",
        "display_name": "Thanh Phương Viettel",
        "gender": "female",
        "provider": "nghitts",
        "description": "Giọng nữ chuẩn đọc sách, tổng đài",
    },
    # ── GIỌNG NAM ────────────────────────────────────────────────────────────
    {
        "voice_id": "Trấn Thành",
        "display_name": "Trấn Thành",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng MC Trấn Thành - nam, linh hoạt, biểu cảm",
    },
    {
        "voice_id": "Việt Thảo",
        "display_name": "Việt Thảo",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nghệ sĩ hài MC Việt Thảo - nam, sôi nổi",
    },
    {
        "voice_id": "Ngọc Ngạn",
        "display_name": "Ngọc Ngạn",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng MC Nguyễn Ngọc Ngạn - nam, truyền cảm",
    },
    {
        "voice_id": "Duy Onyx (mới)",
        "display_name": "Duy Onyx (mới)",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam trầm ấm, phát âm chuẩn",
    },
    {
        "voice_id": "Duy Oryx",
        "display_name": "Duy Oryx",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam siêu trầm đặc biệt",
    },
    {
        "voice_id": "Chiếu Thành",
        "display_name": "Chiếu Thành",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam phong cách đọc truyện, tự sự",
    },
    {
        "voice_id": "Minh Khang",
        "display_name": "Minh Khang",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam thanh niên hiện đại",
    },
    {
        "voice_id": "Minh Quang",
        "display_name": "Minh Quang",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam truyền cảm, ấm áp",
    },
    {
        "voice_id": "Mạnh Dũng",
        "display_name": "Mạnh Dũng",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam dõng dạc, mạnh mẽ",
    },
    {
        "voice_id": "Thiện Tâm",
        "display_name": "Thiện Tâm",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam điềm đạm, tin cậy",
    },
    {
        "voice_id": "Tài An",
        "display_name": "Tài An",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam trẻ trung, tự nhiên",
    },
    {
        "voice_id": "Lạc Phi",
        "display_name": "Lạc Phi",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam đọc truyện, diễn cảm",
    },
    {
        "voice_id": "adam",
        "display_name": "Adam",
        "gender": "male",
        "provider": "nghitts",
        "description": "Giọng nam chuẩn quốc tế",
    },
]

# Map voice_id → metadata để tra cứu nhanh
_VOICE_META: dict[str, dict] = {v["voice_id"]: v for v in NGHITTS_VI_VOICES}

_FEMALE_KEYWORDS = {
    "woman", "female", "nu", "nữ", "girl",
    "mytam", "ngocngan", "huyền", "huyen", "huong",
    "lan", "linh", "ngoc", "cuthu",
}
_MALE_KEYWORDS = {
    "man", "male", "nam", "boy", "deep",
    "vietthao", "tranthanh", "oryx", "thanh",
}


def _detect_gender(name: str) -> str:
    lower = name.lower()
    for kw in _FEMALE_KEYWORDS:
        if kw in lower:
            return "female"
    for kw in _MALE_KEYWORDS:
        if kw in lower:
            return "male"
    return "unknown"


def _make_display_name(voice_id: str) -> str:
    """Tạo tên hiển thị đẹp từ voice_id (fallback cho model không có tên tĩnh)."""
    name = re.sub(r"\d{4}$", "", voice_id).strip()
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ")
    return name.strip().title() or voice_id


@router.get("/free-voices")
async def get_free_voices():
    """Trả về danh sách giọng đọc free từ nghitts (Piper TTS - tiếng Việt).

    Kết hợp 2 nguồn:
    1. Danh sách tĩnh đã biết (NGHITTS_VI_VOICES) — có tên đẹp và gender đúng.
    2. Scan thêm từ public/tts-model/vi/ nếu có model local chưa có trong danh sách tĩnh.
    """
    PROJECT_ROOT = Path(__file__).parents[3]
    vi_model_dir = PROJECT_ROOT / "nghitts" / "public" / "tts-model" / "vi"

    # Bắt đầu với danh sách tĩnh (duy trì thứ tự)
    result: dict[str, dict] = {}
    for v in NGHITTS_VI_VOICES:
        result[v["voice_id"]] = {
            "voice_id": v["voice_id"],
            "model_name": v["display_name"],
            "gender": v["gender"],
            "provider": v.get("provider", "nghitts"),
            "description": v.get("description", ""),
        }

    # Bổ sung model local nếu chưa có trong danh sách tĩnh
    if vi_model_dir.is_dir():
        for f in sorted(vi_model_dir.iterdir()):
            if f.name.endswith(".onnx.json"):
                vid = f.name.replace(".onnx.json", "")
                if vid not in result:
                    meta = _VOICE_META.get(vid)
                    if meta:
                        result[vid] = {
                            "voice_id": vid,
                            "model_name": meta["display_name"],
                            "gender": meta["gender"],
                            "provider": "nghitts",
                            "description": meta.get("description", ""),
                        }
                    else:
                        result[vid] = {
                            "voice_id": vid,
                            "model_name": _make_display_name(vid),
                            "gender": _detect_gender(vid),
                            "provider": "nghitts",
                            "description": "",
                        }

    return list(result.values())
