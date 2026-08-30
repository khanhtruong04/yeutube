"""
Dịch transcript tự động qua OpenRouter (API tương thích OpenAI) — thay thế
bước "AI agent dịch tay" trong skill voice-over cho pipeline web tự động.

Config (env):
  OPENROUTER_API_KEY   Bắt buộc.
  OPENROUTER_MODEL      Mặc định "openai/gpt-4o-mini".

Usage:
  from backend.translate import translate_transcript
  transcript_vi = await translate_transcript(transcript, target_language="vi")
"""
import asyncio
import json
import os

import httpx

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Gửi cả trăm đoạn 1 lượt thì model hay gộp/bỏ đoạn (thực tế: 154 đoạn -> trả 143).
# Chia lô nhỏ để giữ đúng số lượng; lô nào vẫn lệch thì _translate_texts tự chia đôi.
BATCH_SIZE = 25

# Các lô độc lập nhau nên dịch song song thay vì xếp hàng chờ từng lô: video 200
# đoạn = 8 lô, chạy tuần tự thì cộng dồn 8 lượt chờ mạng. Giới hạn 4 để không bị
# OpenRouter chặn vì gọi quá dày.
MAX_PARALLEL_BATCHES = 4

_LANG_NAMES = {
    "vi": "Tiếng Việt", "en": "English", "zh": "中文", "ja": "日本語",
    "ko": "한국어", "fr": "Français", "es": "Español", "th": "ภาษาไทย",
}


def _cfg(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _build_prompt(texts: list[str], context: str, target_language: str) -> str:
    lang_name = _LANG_NAMES.get(target_language, target_language)
    numbered = "\n".join(f"{i}: {t}" for i, t in enumerate(texts))
    return (
        f"Dịch các đoạn phụ đề video sau sang {lang_name}. "
        "Văn phong tự nhiên, đúng ngữ cảnh (vlog/review/tin tức/kể chuyện...), "
        "không dịch máy móc từng từ.\n\n"
        f"Ngữ cảnh toàn video (chỉ để tham khảo, KHÔNG dịch phần này): {context[:1500]}\n\n"
        f"QUAN TRỌNG: phải trả về ĐÚNG {len(texts)} đoạn, đúng thứ tự, "
        "không gộp, không tách, không bỏ đoạn nào. Đoạn gốc nào quá ngắn hoặc chỉ là "
        "tiếng động thì vẫn phải có 1 phần tử tương ứng.\n\n"
        f"Các đoạn cần dịch (đánh số 0..{len(texts) - 1}):\n{numbered}\n\n"
        "Trả về DUY NHẤT 1 JSON object, không giải thích:\n"
        f'{{"segments": [<đúng {len(texts)} chuỗi đã dịch, theo thứ tự>]}}'
    )


async def _call_llm(
    client: httpx.AsyncClient, texts: list[str], context: str,
    target_language: str, model: str, headers: dict,
) -> list[str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _build_prompt(texts, context, target_language)}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    resp = await client.post(BASE_URL, headers=headers, json=payload)
    if not resp.is_success:
        raise RuntimeError(f"OpenRouter translate [{resp.status_code}]: {resp.text[:500]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        segments = parsed["segments"]
    except (KeyError, IndexError, json.JSONDecodeError, TypeError) as e:
        raise RuntimeError(f"OpenRouter trả về format không hợp lệ: {e}. Raw: {str(data)[:500]}") from e

    if not isinstance(segments, list):
        raise RuntimeError(f"Field 'segments' không phải list: {str(segments)[:200]}")
    return [str(s).strip() for s in segments]


async def _translate_texts(
    client: httpx.AsyncClient, texts: list[str], context: str,
    target_language: str, model: str, headers: dict,
) -> list[str]:
    """Dịch 1 nhóm đoạn, đảm bảo trả về đúng len(texts) phần tử.

    Nếu model trả sai số lượng thì chia đôi rồi dịch lại từng nửa — chia tới mức
    1 đoạn thì chắc chắn khớp. Đoạn lẻ cuối cùng nếu vẫn hỏng thì giữ nguyên bản
    gốc (thà sót 1 câu chưa dịch còn hơn hỏng cả job)."""
    if not texts:
        return []

    try:
        result = await _call_llm(client, texts, context, target_language, model, headers)
        if len(result) == len(texts):
            return result
    except RuntimeError:
        if len(texts) == 1:
            return [texts[0]]
        result = None

    if len(texts) == 1:
        return [texts[0]]

    mid = len(texts) // 2
    left = await _translate_texts(client, texts[:mid], context, target_language, model, headers)
    right = await _translate_texts(client, texts[mid:], context, target_language, model, headers)
    return left + right


async def translate_transcript(transcript: dict, target_language: str = "vi") -> dict:
    """
    Dịch transcript.json -> transcript-vi.json (hoặc ngôn ngữ khác), giữ nguyên
    language/language_probability/segments[].start/end/probability, chỉ thay text.
    """
    api_key = _cfg("OPENROUTER_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Missing OPENROUTER_API_KEY env var. Điền key vào .env để dùng dịch tự động."
        )

    segments = transcript.get("segments", [])
    if not segments:
        raise ValueError("transcript không có segments để dịch.")

    texts = [s["text"] for s in segments]
    model = _cfg("OPENROUTER_MODEL", DEFAULT_MODEL)
    context = transcript.get("text", "")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    batches = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    async with httpx.AsyncClient(timeout=180) as client:
        sem = asyncio.Semaphore(MAX_PARALLEL_BATCHES)

        async def run_batch(batch: list[str]) -> list[str]:
            async with sem:
                return await _translate_texts(client, batch, context, target_language, model, headers)

        # gather giữ nguyên thứ tự kết quả theo thứ tự batch -> ghép lại vẫn đúng
        # thứ tự đoạn gốc.
        results = await asyncio.gather(*(run_batch(b) for b in batches))
    translated: list[str] = [t for r in results for t in r]

    if len(translated) != len(segments):  # phòng hờ, không nên xảy ra
        raise RuntimeError(
            f"Số đoạn dịch ({len(translated)}) không khớp transcript gốc ({len(segments)})."
        )

    new_segments = [{**seg, "text": t} for seg, t in zip(segments, translated)]

    return {
        **transcript,
        "text": " ".join(t for t in translated if t).strip(),
        "segments": new_segments,
    }
