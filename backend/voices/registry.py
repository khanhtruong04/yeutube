"""
Provider registry cho TTS — dispatch tới đúng adapter module theo tên provider,
không sửa các adapter hiện có (omnivoice/vbee/elevenlabs/edgetts).

Chỉ 4 provider có adapter thật được hỗ trợ. "openai" xuất hiện trong
voice/openai.csv và SKILL.md nhưng chưa có backend/voices/openai.py — cố tình
không đưa vào registry để tránh quảng cáo 1 provider không chạy được.
"""
import asyncio
import csv
import os
from pathlib import Path

from . import edgetts, elevenlabs, nghitts, omnivoice, vbee

# Số lần thử lại + thời gian chờ khi 1 lệnh TTS lỗi thoáng qua. Quan trọng từ khi
# TTS chạy theo từng câu (dub_timeline.py) thay vì 1 lần cho cả bài — số lượt gọi
# tăng từ 1 lên hàng trăm mỗi job.
#
# Chờ theo cấp số nhân (2/4/8/16s ≈ 30s) chứ không tăng đều: "No audio was
# received" của edge-tts là Microsoft chặn theo nhịp gọi, và khi đã bị chặn thì
# chặn cả một khoảng thời gian — đo thực tế: gọi dồn thì hỏng 40-60%, giãn 1
# giây/lệnh thì 24/24 lệnh đều chạy, cùng câu cùng giọng. Chờ đều 1.5-6s (tổng
# 15s) thì cả 5 lượt thử rơi gọn trong khoảng đang bị chặn nên cùng hỏng.
_TTS_RETRIES = 4
_TTS_RETRY_DELAY = 2.0

PROJECT_ROOT = Path(__file__).parent.parent.parent
VOICE_DIR = PROJECT_ROOT / "voice"

# Thứ tự ưu tiên khi auto-chọn provider.
# nghitts và edgetts miễn phí, không cần key, luôn khả dụng.
# nghitts chạy mô hình local Piper chất lượng cao.
PRIORITY = ["nghitts", "vbee", "elevenlabs", "edgetts", "omnivoice"]

PROVIDERS = {
    "nghitts": {"module": nghitts, "env_required": []},
    "vbee": {"module": vbee, "env_required": ["VBEE_TOKEN", "VBEE_APP_ID"]},
    "elevenlabs": {"module": elevenlabs, "env_required": ["ELEVENLABS_API_KEY"]},
    "omnivoice": {"module": omnivoice, "env_required": []},
    "edgetts": {"module": edgetts, "env_required": []},
}


def _is_set(key: str) -> bool:
    """True nếu env var có giá trị thật — bỏ qua placeholder '...' còn sót trong .env.example."""
    value = (os.environ.get(key) or "").strip()
    return bool(value) and value != "..."


def _is_available(name: str) -> bool:
    required = PROVIDERS[name]["env_required"]
    return all(_is_set(k) for k in required)


def available_providers() -> list[dict]:
    result = []
    for name in PRIORITY:
        required = PROVIDERS[name]["env_required"]
        available = _is_available(name)
        result.append({
            "name": name,
            "available": available,
            "reason": None if available else f"Thiếu env: {', '.join(required)}",
        })
    return result


def default_provider() -> str:
    for name in PRIORITY:
        if _is_available(name):
            return name
    return "edgetts"  # luôn sẵn sàng, không cần key


def _voice_csv_path(provider: str) -> Path:
    return VOICE_DIR / f"{provider}.csv"


def list_voices(provider: str) -> list[dict]:
    path = _voice_csv_path(provider)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def default_voice(provider: str) -> str | None:
    voices = list_voices(provider)
    if not voices:
        return None
    return voices[0].get("voice_id")


# edgetts không có CSV danh mục — hardcode 2 voice tiếng Việt có sẵn của Edge TTS.
_EDGETTS_BY_GENDER = {"male": "vi-VN-NamMinhNeural", "female": "vi-VN-HoaiMyNeural"}

_GENDER_ALIASES = {
    "male": {"male", "nam", "m"},
    "female": {"female", "nữ", "nu", "f"},
}


def pick_voice(provider: str, gender: str | None = None) -> str | None:
    """Chọn voice_code theo giới tính từ danh mục voice/<provider>.csv (cột `gender`).
    Fallback: nếu provider không có cột gender (vd. elevenlabs) hoặc không khớp
    giới tính nào, trả về voice đầu tiên trong danh mục."""
    if provider == "edgetts":
        if gender and gender.lower() in _GENDER_ALIASES.get("male", set()):
            return _EDGETTS_BY_GENDER["male"]
        if gender and gender.lower() in _GENDER_ALIASES.get("female", set()):
            return _EDGETTS_BY_GENDER["female"]
        return _EDGETTS_BY_GENDER["female"]

    voices = list_voices(provider)
    if not voices:
        return None
    if not gender:
        return voices[0].get("voice_id")

    wanted = gender.lower()
    aliases = _GENDER_ALIASES.get(wanted, {wanted})
    for v in voices:
        g = (v.get("gender") or "").strip().lower()
        if g in aliases:
            return v.get("voice_id")
    return voices[0].get("voice_id")


def detect_provider_for_voice(voice_code: str | None) -> str | None:
    """Tự động nhận diện provider sở hữu voice_code này."""
    if not voice_code:
        return None
    code_clean = voice_code.strip()
    if code_clean.startswith("vi-VN-"):
        return "edgetts"

    # Kiểm tra nghitts
    from .nghitts import VOICE_ALIASES
    nghitts_voices = {v.get("voice_id", "").strip().lower() for v in list_voices("nghitts")}
    if code_clean.lower() in nghitts_voices or code_clean.lower() in VOICE_ALIASES:
        return "nghitts"

    # Kiểm tra các provider khác
    for prov in ("vbee", "elevenlabs", "omnivoice"):
        prov_voices = {v.get("voice_id", "").strip() for v in list_voices(prov)}
        if code_clean in prov_voices:
            return prov
    return None


async def run_tts(
    provider: str,
    text: str,
    *,
    voice_code: str | None = None,
    speed: float | None = None,
    output: str,
    log=None,
) -> dict:
    if provider not in PROVIDERS:
        raise ValueError(f"Provider không hỗ trợ: {provider}. Chọn 1 trong {list(PROVIDERS)}")

    module = PROVIDERS[provider]["module"]
    voice = voice_code or default_voice(provider)

    if provider == "elevenlabs":
        if not voice:
            raise ValueError("elevenlabs bắt buộc phải có voice_code.")
        call = lambda: module.run_tts(text=text, voice_code=voice, output=output, log=log)
    else:
        # vbee / omnivoice / nghitts / edgetts: voice_code optional (module tự có default),
        # speed được hỗ trợ bởi vbee, omnivoice và nghitts.
        kwargs = {"text": text, "voice_code": voice, "output": output, "log": log}
        if provider in ("vbee", "omnivoice", "nghitts") and speed is not None:
            kwargs["speed"] = speed
        call = lambda: module.run_tts(**kwargs)

    _log = log or (lambda _: None)
    last_error: Exception | None = None
    for attempt in range(_TTS_RETRIES + 1):
        try:
            return await call()
        except Exception as e:
            last_error = e
            if attempt < _TTS_RETRIES:
                delay = _TTS_RETRY_DELAY * (2 ** attempt)
                _log(f"[registry] '{provider}' lỗi thoáng qua ({e!s:.150}), chờ {delay:.1f}s rồi thử lần {attempt + 2}...")
                await asyncio.sleep(delay)
    raise last_error


async def synthesize(
    text: str,
    *,
    gender: str | None = None,
    provider: str | None = None,
    voice_code: str | None = None,
    speed: float | None = None,
    output: str,
    log=None,
) -> dict:
    """Chạy TTS với provider phù hợp, tự fallback sang provider khả dụng kế tiếp khi lỗi.

    Cần fallback vì "có key" không đồng nghĩa "dùng được": vd. ElevenLabs gói free
    trả 402 khi gọi library voice qua API. Trả về kèm provider/voice_code thực tế đã dùng.
    """
    # Nếu voice_code được truyền vào mà chưa chỉ định provider, tự dò xem voice thuộc provider nào
    target_prov = provider or (detect_provider_for_voice(voice_code) if voice_code else None)

    if target_prov:
        # Ưu tiên target_prov lên đầu danh sách candidates
        candidates = [target_prov]
        for p in PRIORITY:
            if p != target_prov and _is_available(p) and p not in candidates:
                candidates.append(p)
    else:
        candidates = [p for p in PRIORITY if _is_available(p)]

    if not candidates:
        raise RuntimeError("Không có provider TTS nào khả dụng.")

    _log = log or (lambda _: None)
    errors = []
    for i, name in enumerate(candidates):
        # voice_code do user chỉ định chỉ áp cho provider khớp với voice đó (thường là lượt đầu)
        if i == 0 and voice_code:
            code = voice_code
        else:
            code = pick_voice(name, gender)

        try:
            result = await run_tts(name, text, voice_code=code, speed=speed, output=output, log=log)
            return {**result, "provider": name, "voice_code": code}
        except Exception as e:
            errors.append(f"{name}: {str(e)[:200]}")
            _log(f"[registry] provider '{name}' lỗi, thử provider tiếp theo...")

    raise RuntimeError("Tất cả provider TTS đều lỗi -> " + " | ".join(errors))
