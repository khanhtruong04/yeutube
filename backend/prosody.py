"""Ngữ điệu (prosody) cho TTS — đọc như người thật, không đọc đều một mạch.

Bốn provider TTS trong `backend/voices/` đều chỉ nhận một chuỗi text phẳng và
một `speed` duy nhất cho cả đoạn (edge-tts/elevenlabs còn không nhận cả speed),
không cái nào nhận SSML. Nên muốn có ngữ điệu thì phải tự dựng ở phía mình:

    text -> tách thành các mẩu (chunk) kèm tốc độ + độ dài khoảng lặng
         -> TTS từng mẩu
         -> atempo (nhanh/chậm) + volume (nhấn) + apad (khoảng lặng) cho từng mẩu
         -> nối lại thành 1 file

Quy tắc tách, đúng theo cách người ta đọc một kịch bản lồng tiếng:

  * Liên từ / từ đưa đẩy đứng đầu vế ("Tuy nhiên", "Nói chung", "Thật ra thì"…)
    -> tách riêng, đọc lướt nhanh hơn, dính liền vào vế sau (không nghỉ).
  * Dấu phẩy -> ngắt ngắn; chấm/chấm than/chấm hỏi -> ngắt dài hơn; "…" và
    xuống dòng/hết đoạn -> ngắt dài nhất.
  * Chữ in đậm (`**...**`, `__...__`, `<b>`) -> nhấn mạnh: đọc chậm lại, to hơn
    một chút, có một nhịp lấy đà trước và sau.
  * Chỉ dẫn dừng ghi thẳng trong kịch bản — 【DỪNG 2 GIÂY】, (dừng 3 giây...),
    [pause 2s], (im lặng 1.5 giây) -> im hẳn đúng số giây đó, và bản thân chỉ
    dẫn KHÔNG được đọc lên.

Ngoặc đơn không phải chỉ dẫn dừng thì giữ nguyên, vẫn đọc bình thường — xoá hết
mọi thứ trong ngoặc thì dễ nuốt mất nội dung thật.

Mỗi mẩu TTS xong đều bị cắt sạch khoảng lặng thừa ở hai đầu (`silenceremove`)
trước khi nối — không thì mỗi dấu phẩy lại cõng thêm ~200ms im lặng của engine,
nối 50 mẩu thành ra lê thê.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterator

from .proc_util import run_command

# ── Thông số ngữ điệu (giây / hệ số tốc độ) ────────────────────────────────

PAUSE_COMMA = 0.20
PAUSE_COLON = 0.35
PAUSE_DASH = 0.28
PAUSE_SENTENCE = 0.45
PAUSE_EXCLAIM = 0.50
PAUSE_QUESTION = 0.50
PAUSE_ELLIPSIS = 0.60
PAUSE_LINE = 0.35
PAUSE_PARA = 0.75
PAUSE_MARKER_DEFAULT = 1.0   # 【DỪNG】 không ghi số giây
PAUSE_MARKER_MAX = 30.0

# Liên từ/đưa đẩy đọc lướt xong dính luôn vào vế sau -> nghỉ gần như bằng 0.
PAUSE_CONNECTIVE = 0.10
SPEED_CONNECTIVE = 1.20
SPEED_EMPHASIS = 0.86
GAIN_EMPHASIS_DB = 2.0
PAUSE_BEFORE_EMPHASIS = 0.12
PAUSE_AFTER_EMPHASIS = 0.16

# Vế còn lại phải đủ dài thì mới bõ tách liên từ ra đọc riêng — tách ra mà vế
# sau chỉ còn 1-2 chữ thì nghe vụn.
MIN_REST_WORDS = 4
# Mẩu ngắn hơn ngần này chữ thì gộp vào mẩu trước: TTS đọc một mẩu 1 chữ hay bị
# lên giọng kết câu, nghe rời rạc.
MIN_CHUNK_WORDS = 2

TRIM_KEEP = 0.03           # giữ lại 30ms lặng hai đầu cho đỡ cụt tiếng
TRIM_THRESHOLD = "-45dB"
SAMPLE_RATE = 44100

_SPEAKABLE = re.compile(r"[0-9A-Za-zÀ-ɏḀ-ỿ一-鿿]")


# ── Nhận diện chỉ dẫn dừng trong kịch bản ─────────────────────────────────

_PAUSE_KEYWORD_RE = re.compile(
    r"(dừng|dung|ngưng|ngung|nghỉ|nghi|im\s*lặng|im\s*lang|lặng|pause|break|beat|silence|hold)",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mili\s*giây|mili\s*giay|ms|giây|giay|s|sec|secs|second|seconds)?",
    re.IGNORECASE,
)
_BARE_DURATION_RE = re.compile(
    r"^\d+(?:[.,]\d+)?\s*(giây|giay|s|sec|secs|second|seconds)\s*[.…]*$",
    re.IGNORECASE,
)


def _parse_pause_marker(inner: str) -> float | None:
    """Nội dung trong ngoặc -> số giây im lặng, hoặc None nếu đây không phải
    chỉ dẫn dừng (ngoặc nội dung thật thì trả None để giữ nguyên mà đọc)."""
    s = inner.strip()
    if not s:
        return None
    if not _PAUSE_KEYWORD_RE.search(s) and not _BARE_DURATION_RE.match(s):
        return None
    m = _DURATION_RE.search(s)
    if not m:
        return PAUSE_MARKER_DEFAULT
    value = float(m.group(1).replace(",", "."))
    unit = (m.group(2) or "giây").lower().replace(" ", "")
    if unit in ("ms", "miligiây", "miligiay"):
        value /= 1000.0
    return max(0.0, min(PAUSE_MARKER_MAX, value))


# ── Liên từ / từ đưa đẩy đứng đầu vế, đọc lướt ────────────────────────────

_LEAD_FAST_PHRASES = [
    # liên từ
    "và", "rồi thì", "rồi", "nhưng mà", "nhưng", "cơ mà", "tuy nhiên", "tuy vậy",
    "thế nhưng", "mặc dù vậy", "dù vậy", "bởi vì", "bởi vậy", "bởi thế", "vì vậy",
    "vì thế", "chính vì thế", "chính vì vậy", "do đó", "do vậy", "cho nên là",
    "cho nên", "thế nên", "vậy nên", "thành ra", "thế là", "vậy là", "thế thì",
    "vậy thì", "tại vì", "với lại", "ngoài ra", "hơn nữa", "thêm vào đó",
    "bên cạnh đó", "mặt khác", "trong khi đó", "trong khi", "sau đó", "tiếp theo",
    "tiếp đó", "đầu tiên", "trước hết", "trước tiên", "thứ nhất", "thứ hai",
    "thứ ba", "cuối cùng", "nếu như", "nếu",
    # đưa đẩy / khẩu ngữ
    "nói chung là", "nói chung", "nói cách khác", "nói thật là", "nói thật",
    "nói thẳng ra", "tóm lại là", "tóm lại", "nhìn chung", "thật ra thì",
    "thật ra là", "thật ra", "thực ra thì", "thực ra là", "thực ra", "thực chất",
    "kiểu như là", "kiểu như", "đại loại là", "đại loại", "nghĩa là", "tức là",
    "có nghĩa là", "ý là", "ý tôi là", "chẳng qua là", "chẳng qua",
    "dĩ nhiên là", "dĩ nhiên", "tất nhiên là", "tất nhiên", "đương nhiên là",
    "đương nhiên", "quả thật là", "quả thật", "quả là", "nhân tiện thì",
    "nhân tiện", "nhân đây", "thú thật là", "thú thật", "à mà", "à thì", "ừ thì",
    "vậy đó", "thế đấy", "và rồi", "rồi sau đó",
]
_LEAD_FAST_RE = re.compile(
    r"^(?:"
    + "|".join(sorted((re.escape(p) for p in _LEAD_FAST_PHRASES), key=len, reverse=True))
    + r")(?=[\s,;:]|$)",
    re.IGNORECASE,
)


# ── Tách vế theo dấu câu ──────────────────────────────────────────────────

# `.` chỉ tính là hết câu khi không kẹp giữa hai chữ số (giữ nguyên "1.5 triệu").
_PUNCT_RE = re.compile(r"(\.{3,}|…+|(?<!\d)\.(?!\d)|[!?]+|[,;:]|[—–]|\n{2,}|\n)")


def _pause_for(mark: str) -> float:
    if mark.count("\n") >= 2:
        return PAUSE_PARA
    if "\n" in mark:
        return PAUSE_LINE
    if "…" in mark or mark.startswith("..."):
        return PAUSE_ELLIPSIS
    if "?" in mark:
        return PAUSE_QUESTION
    if "!" in mark:
        return PAUSE_EXCLAIM
    if mark == ".":
        return PAUSE_SENTENCE
    if mark in (":", ";"):
        return PAUSE_COLON
    if mark == ",":
        return PAUSE_COMMA
    return PAUSE_DASH


def _split_clauses(text: str) -> tuple[list[tuple[str, float]], float]:
    """-> ([(vế kèm dấu câu của nó, số giây nghỉ sau vế)], nghỉ mồ côi đầu đoạn).

    Dấu câu được giữ lại trong text gửi cho TTS: engine dựa vào nó để lên/xuống
    giọng cuối vế. "Nghỉ mồ côi" là dấu câu đứng trước mọi chữ đọc được của đoạn
    — vd. dấu chấm ngay sau một cụm in đậm — phải trả về cho bên gọi dồn ngược
    vào mẩu liền trước, không thì mất luôn nhịp ngắt hết câu."""
    out: list[tuple[str, float]] = []
    orphan = 0.0
    pos = 0
    for m in _PUNCT_RE.finditer(text):
        mark = m.group(0)
        raw = text[pos:m.start()]
        pos = m.end()
        spoken = "" if "\n" in mark else mark
        piece = (raw + spoken).strip()
        pause = _pause_for(mark)
        if _SPEAKABLE.search(piece):
            out.append((piece, pause))
        elif out:
            # vế rỗng (vd. hai dấu liền nhau) -> dồn khoảng nghỉ vào vế trước
            out[-1] = (out[-1][0], max(out[-1][1], pause))
        else:
            orphan = max(orphan, pause)
    tail = text[pos:].strip()
    if _SPEAKABLE.search(tail):
        out.append((tail, 0.0))
    return out, orphan


# ── Tokenize: in đậm + chỉ dẫn dừng + phần text thường ────────────────────

_TOKEN_RE = re.compile(
    r"(?P<bold>\*\*(?P<b1>[^*\n]{1,400}?)\*\*"
    r"|__(?P<b2>[^_\n]{1,400}?)__"
    r"|<(?:b|strong)>(?P<b3>.{1,400}?)</(?:b|strong)>)"
    r"|(?P<bracket>[\(\[\{【〔][^\(\)\[\]\{\}【】〔〕]{0,120}[\)\]\}】〕])",
    re.IGNORECASE | re.DOTALL,
)

_MD_NOISE_RE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]+|>[ \t]+|[-*+][ \t]+|\d+[.)][ \t]+)", re.MULTILINE)
_MD_RULE_RE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)


def _strip_markdown_noise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MD_RULE_RE.sub("", text)
    return _MD_NOISE_RE.sub("", text)


def _tokenize(text: str) -> Iterator[tuple[str, object]]:
    """-> ('text', str) | ('emph', str) | ('pause', float). Các đoạn text thường
    liền nhau được gộp lại trước khi trả ra, để không cắt nhầm giữa một vế."""
    buf: list[str] = []
    pos = 0

    def flush() -> list[tuple[str, object]]:
        joined = "".join(buf)
        buf.clear()
        return [("text", joined)] if joined.strip() else []

    for m in _TOKEN_RE.finditer(text):
        if m.group("bold") is not None:
            inner = m.group("b1") or m.group("b2") or m.group("b3") or ""
            buf.append(text[pos:m.start()])
            yield from flush()
            yield "emph", inner
        else:
            raw = m.group("bracket")
            seconds = _parse_pause_marker(raw[1:-1])
            if seconds is None:
                # ngoặc chứa nội dung thật -> giữ nguyên, vẫn đọc bình thường
                buf.append(text[pos:m.end()])
                pos = m.end()
                continue
            buf.append(text[pos:m.start()])
            yield from flush()
            yield "pause", seconds
        pos = m.end()
    buf.append(text[pos:])
    yield from flush()


# ── Chunk ─────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    text: str
    speed: float = 1.0        # hệ số so với tốc độ nền của giọng đọc
    gain_db: float = 0.0
    pause_after: float = 0.0
    atomic: bool = False      # không gộp / không tách tiếp (liên từ, nhấn mạnh)


def _apply_lead_fast(chunks: list[Chunk]) -> list[Chunk]:
    out: list[Chunk] = []
    for c in chunks:
        if c.atomic:
            out.append(c)
            continue
        m = _LEAD_FAST_RE.match(c.text)
        if not m:
            out.append(c)
            continue
        head = c.text[:m.end()].strip()
        rest = c.text[m.end():].strip()
        if not _SPEAKABLE.search(rest):
            # cả vế chỉ là liên từ ("Tuy nhiên,") -> lướt qua, dính vào vế sau
            c.speed = SPEED_CONNECTIVE
            c.pause_after = min(c.pause_after, PAUSE_CONNECTIVE)
            out.append(c)
            continue
        if len(rest.split()) < MIN_REST_WORDS:
            out.append(c)
            continue
        out.append(Chunk(text=head, speed=SPEED_CONNECTIVE, pause_after=0.0, atomic=True))
        c.text = rest
        out.append(c)
    return out


def _merge_tiny(chunks: list[Chunk]) -> list[Chunk]:
    out: list[Chunk] = []
    for c in chunks:
        if not _SPEAKABLE.search(c.text):
            if out:
                out[-1].pause_after = max(out[-1].pause_after, c.pause_after)
            continue
        if (
            not c.atomic
            and len(c.text.split()) < MIN_CHUNK_WORDS
            and out
            and not out[-1].atomic
        ):
            out[-1].text = f"{out[-1].text} {c.text}".strip()
            out[-1].pause_after = c.pause_after
            continue
        out.append(c)
    return out


def parse(
    text: str,
    *,
    fast_connectives: bool = True,
    pause_scale: float = 1.0,
    max_pause: float | None = None,
) -> tuple[list[Chunk], float]:
    """text kịch bản -> (danh sách chunk, số giây im lặng mở đầu)."""
    chunks: list[Chunk] = []
    lead = 0.0

    def add_pause(seconds: float, *, allow_lead: bool = True) -> None:
        """Chưa có mẩu nào thì khoảng nghỉ thành im lặng mở đầu — trừ nhịp lấy đà
        của chữ in đậm, mở đầu bản dub bằng 0.12s câm là thừa."""
        nonlocal lead
        if chunks:
            chunks[-1].pause_after = max(chunks[-1].pause_after, seconds)
        elif allow_lead:
            lead = max(lead, seconds)

    for kind, value in _tokenize(_strip_markdown_noise(text)):
        if kind == "pause":
            add_pause(float(value))
        elif kind == "emph":
            pieces, orphan = _split_clauses(str(value))
            add_pause(orphan)
            if not pieces:
                continue
            add_pause(PAUSE_BEFORE_EMPHASIS, allow_lead=False)   # nhịp lấy đà trước khi nhấn
            for clause, pause in pieces:
                chunks.append(Chunk(
                    text=clause, speed=SPEED_EMPHASIS, gain_db=GAIN_EMPHASIS_DB,
                    pause_after=pause, atomic=True,
                ))
            chunks[-1].pause_after = max(chunks[-1].pause_after, PAUSE_AFTER_EMPHASIS)
        else:
            pieces, orphan = _split_clauses(str(value))
            add_pause(orphan)
            for clause, pause in pieces:
                chunks.append(Chunk(text=clause, pause_after=pause))

    chunks = _merge_tiny(chunks)
    if fast_connectives:
        chunks = _apply_lead_fast(chunks)

    cap = max_pause if max_pause is not None else float("inf")
    lead = min(lead * pause_scale, cap)
    for c in chunks:
        c.pause_after = min(c.pause_after * pause_scale, cap)
    if chunks:
        chunks[-1].pause_after = 0.0   # đuôi im lặng thừa, cắt đi
    return chunks, lead


# ── Dựng audio ────────────────────────────────────────────────────────────

def _hash(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:10]


async def _post_process(raw: Path, out: Path, chunk: Chunk, lead: float) -> None:
    """Cắt lặng thừa hai đầu -> đổi tốc độ -> nhấn -> chèn khoảng lặng."""
    trim = f"silenceremove=start_periods=1:start_silence={TRIM_KEEP}:start_threshold={TRIM_THRESHOLD}"
    parts = [trim, "areverse", trim, "areverse"]
    if abs(chunk.speed - 1.0) > 0.01:
        parts.append(f"atempo={chunk.speed:.4f}")
    if abs(chunk.gain_db) > 0.01:
        parts.append(f"volume={chunk.gain_db:.2f}dB")
    if lead > 0.005:
        parts.append(f"adelay={round(lead * 1000)}:all=1")
    if chunk.pause_after > 0.005:
        parts.append(f"apad=pad_dur={chunk.pause_after:.3f}")

    code, _, stderr = await run_command([
        "ffmpeg", "-y", "-i", str(raw), "-af", ",".join(parts),
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(out),
    ])
    if code != 0:
        raise RuntimeError(f"ffmpeg xử lý ngữ điệu lỗi: {stderr.decode(errors='replace')[-500:]}")


async def _concat(pieces: list[Path], work_dir: Path, output: str) -> None:
    # Đường dẫn trong file concat để tương đối so với chính nó — thư mục
    # downloads có tên tiếng Trung/tiếng Việt, nhét đường dẫn tuyệt đối vào file
    # danh sách dễ lỗi encoding; tên file chunk thì thuần ASCII nên luôn an toàn.
    list_file = work_dir / "concat.txt"
    list_file.write_text("".join(f"file '{p.name}'\n" for p in pieces), encoding="utf-8")
    codec = (
        ["-c:a", "pcm_s16le"] if output.lower().endswith(".wav")
        else ["-c:a", "libmp3lame", "-b:a", "192k"]
    )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    code, _, stderr = await run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-ar", str(SAMPLE_RATE), "-ac", "1", *codec, output,
    ])
    if code != 0:
        raise RuntimeError(f"ffmpeg nối chunk ngữ điệu lỗi: {stderr.decode(errors='replace')[-500:]}")


async def render(
    text: str,
    *,
    tts: Callable[[str, str], Awaitable[None]],
    work_dir: Path | str,
    output: str,
    pause_scale: float = 1.0,
    max_pause: float | None = None,
    fast_connectives: bool = True,
    concurrency: int = 1,
    use_cache: bool = True,
    log=None,
) -> dict:
    """Đọc `text` theo ngữ điệu rồi ghi ra `output`.

    `tts(text, out_path)` là hàm gọi engine — bơm từ ngoài vào để module này
    không dính gì tới việc chọn provider/giọng (dub_timeline khoá sẵn 1 giọng
    cho cả video, CLI thì để registry tự chọn).

    `pause_scale` / `max_pause` để bên gọi ghì bớt khoảng lặng khi audio còn
    phải khớp vào một khung thời gian có sẵn của video.

    `use_cache=False` bắt đọc lại từ đầu kể cả khi đã có file cũ — cần cho lần
    gọi đầu tiên của dub_timeline, nó phải thực sự gọi engine mới biết provider
    nào chạy được để khoá giọng cho cả video.
    """
    _log = log or (lambda _: None)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    chunks, lead = parse(
        text, fast_connectives=fast_connectives, pause_scale=pause_scale, max_pause=max_pause
    )
    if not chunks:
        raise RuntimeError("Không có nội dung nào đọc được sau khi bóc chỉ dẫn ngữ điệu.")

    _log(
        f"[prosody] {len(text.strip())} chars → {len(chunks)} mẩu, "
        f"nghỉ tổng {sum(c.pause_after for c in chunks) + lead:.1f}s"
    )

    sem = asyncio.Semaphore(max(1, concurrency))
    pieces: list[Path | None] = [None] * len(chunks)

    async def build(i: int, c: Chunk) -> None:
        text_hash = _hash(c.text)
        spec = f"{text_hash}|{c.speed}|{c.gain_db}|{c.pause_after}|{lead if i == 0 else 0}"
        raw = work_dir / f"raw_{text_hash}.mp3"
        piece = work_dir / f"p{i:04d}_{_hash(spec)}.wav"
        cached = lambda p: use_cache and p.exists() and p.stat().st_size > 0
        if not cached(piece):
            async with sem:
                if not cached(raw):
                    await tts(c.text, str(raw))
            await _post_process(raw, piece, c, lead if i == 0 else 0.0)
        pieces[i] = piece

    await asyncio.gather(*(build(i, c) for i, c in enumerate(chunks)))
    await _concat([p for p in pieces if p is not None], work_dir, output)

    size = Path(output).stat().st_size
    _log(f"[prosody] saved {size:,} bytes → {output}")
    return {"output_file": output, "bytes": size, "chunks": len(chunks)}
