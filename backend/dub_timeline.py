"""TTS theo từng câu (segment) của transcript, đặt đúng vị trí thời gian gốc
trong video bằng adelay+amix — thay vì đọc liền một mạch từ đầu tới cuối rồi
kéo giãn/nén (atempo) cho vừa tổng thời lượng, khiến câu nói lệch dần khỏi
đúng lúc nhân vật nói câu đó trên hình.

Mỗi câu: đọc theo ngữ điệu (`prosody.render`: lướt qua liên từ, ngắt ở dấu câu,
nhấn chữ in đậm, im hẳn ở chỗ kịch bản ghi 【DỪNG n GIÂY】) -> nếu dài hơn khung
thời gian (end-start) gốc của câu đó thì atempo nén lại cho vừa -> đặt đúng vào
mốc start bằng adelay -> amix tất cả lại thành 1 track dài bằng video_duration.
"""
import asyncio
import re
from pathlib import Path
from typing import Awaitable, Callable

from . import prosody
from .proc_util import run_command
from .voices import registry

# Edge TTS hay trả NoAudioReceived khi bị gọi dồn dập -> giới hạn 2 câu song song
# và giãn nhịp nhẹ giữa các lần gọi.
MAX_CONCURRENCY = 2
_STAGGER_DELAY = 0.2

# Tỉ lệ câu lỗi tối đa còn chấp nhận được. Dưới ngưỡng này thì bỏ qua câu lỗi
# (đoạn đó im lặng) thay vì huỷ cả job — hỏng 1 câu mà mất công cả trăm câu đã
# đọc xong thì quá phí.
_MAX_FAIL_RATIO = 0.15

# Text chỉ toàn dấu câu/ký hiệu chắc chắn làm TTS lỗi -> lọc bỏ từ đầu.
_SPEAKABLE = re.compile(r"[0-9A-Za-zÀ-ɏḀ-ỿ一-鿿]")

# Ngữ điệu ở đây phải ghì lại so với khi đọc kịch bản rời: mỗi câu chỉ có đúng
# khung thời gian gốc của nó trên hình, nghỉ thêm bao nhiêu thì phần đọc bị
# atempo nén lại bấy nhiêu cho vừa khung — nghỉ thoải mái thì giọng hoá ra nói
# nhanh như chạy.
_PAUSE_SCALE = 0.7
_MAX_PAUSE = 0.8


def _is_speakable(text: str) -> bool:
    return bool(_SPEAKABLE.search(text or ""))


def _cached(path: str) -> bool:
    """Câu đã tổng hợp xong ở lần chạy trước -> dùng lại, khỏi gọi TTS lại."""
    p = Path(path)
    return p.exists() and p.stat().st_size > 0


async def _probe_duration(path: str) -> float:
    _, stdout, _ = await run_command([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    try:
        return float(stdout.decode().strip())
    except ValueError:
        return 0.0


async def _fit_segment(raw_path: str, fitted_path: str, target_dur: float) -> None:
    """Nén tốc độ (atempo) nếu audio TTS dài hơn khung thời gian gốc của câu đó."""
    dur = await _probe_duration(raw_path)
    if target_dur <= 0 or dur <= target_dur:
        Path(fitted_path).write_bytes(Path(raw_path).read_bytes())
        return
    tempo = min(2.0, dur / target_dur)
    code, _, stderr = await run_command(
        ["ffmpeg", "-y", "-i", raw_path, "-filter:a", f"atempo={tempo:.4f}", fitted_path]
    )
    if code != 0:
        raise RuntimeError(f"ffmpeg atempo lỗi: {stderr.decode(errors='replace')[-500:]}")


async def synthesize_timeline(
    segments: list[dict],
    *,
    gender: str | None,
    provider: str | None,
    voice_code: str | None,
    speed: float | None,
    video_duration: float,
    work_dir: Path,
    output_path: str,
    log=None,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> dict:
    """Trả về {"provider", "voice_code"} thực tế đã dùng — khoá cố định cho cả
    track sau câu đầu tiên (registry.synthesize có thể fallback provider khác
    nhau nếu gọi riêng lẻ từng câu, làm giọng đổi giữa chừng)."""
    _log = log or (lambda _: None)
    seg_dir = work_dir / "tts_segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    items = [(i, s) for i, s in enumerate(segments) if _is_speakable(s.get("text"))]
    if not items:
        raise RuntimeError("Không có đoạn transcript nào để tổng hợp giọng đọc.")
    total = len(items)
    done_count = 0
    fitted_paths: dict[int, str] = {}

    async def report() -> None:
        nonlocal done_count
        done_count += 1
        _log(f"[dub_timeline] xong đoạn {done_count}/{total}")
        if on_progress:
            await on_progress(done_count, total)

    # Chốt provider/voice bằng câu đầu tiên đọc được, rồi dùng cố định cho cả
    # track — registry.synthesize có fallback provider, nếu để nó tự chọn lại ở
    # từng câu thì giọng có thể đổi giữa chừng. Thử vài câu đầu phòng khi câu
    # đầu tiên lỗi.
    locked: dict[str, str] = {}
    probe_error: Exception | None = None

    async def probe_tts(text: str, out_path: str) -> None:
        """Mẩu đầu tiên để registry tự dò provider chạy được, các mẩu sau bám
        theo đúng provider/voice đó."""
        if locked:
            await registry.run_tts(
                locked["provider"], text, voice_code=locked["voice_code"],
                speed=speed, output=out_path, log=log,
            )
            return
        result = await registry.synthesize(
            text, gender=gender, provider=provider, voice_code=voice_code,
            speed=speed, output=out_path, log=log,
        )
        locked.update(provider=result["provider"], voice_code=result["voice_code"])

    for i, seg in items[:3]:
        raw_p = str(seg_dir / f"{i:04d}_raw.mp3")
        fitted_p = str(seg_dir / f"{i:04d}_fit.mp3")
        try:
            # use_cache=False: chạy lại job mà lấy hết từ cache thì không lần nào
            # gọi tới engine, không biết được provider nào đang sống để khoá.
            await prosody.render(
                seg["text"], tts=probe_tts, work_dir=seg_dir / f"{i:04d}_prosody",
                output=raw_p, pause_scale=_PAUSE_SCALE, max_pause=_MAX_PAUSE,
                use_cache=False, log=log,
            )
            await _fit_segment(raw_p, fitted_p, max(0.1, seg["end"] - seg["start"]))
        except Exception as e:
            probe_error = e
            _log(f"[dub_timeline] đoạn {i} lỗi khi dò provider: {str(e)[:120]}")
            continue
        fitted_paths[i] = fitted_p
        await report()
        break

    locked_provider = locked.get("provider")
    locked_voice = locked.get("voice_code")

    if locked_provider is None:
        raise RuntimeError(f"Không tổng hợp được giọng đọc cho đoạn nào. Lỗi cuối: {probe_error}")

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    failures: list[tuple[int, Exception]] = []

    async def locked_tts(text: str, out_path: str) -> None:
        await asyncio.sleep(_STAGGER_DELAY)
        await registry.run_tts(
            locked_provider, text, voice_code=locked_voice,
            speed=speed, output=out_path, log=log,
        )

    async def synth_one(i: int, seg: dict) -> None:
        raw_p = str(seg_dir / f"{i:04d}_raw.mp3")
        fitted_p = str(seg_dir / f"{i:04d}_fit.mp3")
        try:
            if _cached(fitted_p):
                fitted_paths[i] = fitted_p
                return
            async with sem:
                # concurrency=1: các mẩu trong cùng 1 câu đọc lần lượt, giữ số
                # lệnh TTS chạy song song đúng bằng MAX_CONCURRENCY như trước.
                await prosody.render(
                    seg["text"], tts=locked_tts, work_dir=seg_dir / f"{i:04d}_prosody",
                    output=raw_p, pause_scale=_PAUSE_SCALE, max_pause=_MAX_PAUSE, log=log,
                )
                await _fit_segment(raw_p, fitted_p, max(0.1, seg["end"] - seg["start"]))
            fitted_paths[i] = fitted_p
        except Exception as e:
            # Bỏ qua câu lỗi thay vì huỷ cả job; đoạn đó sẽ im lặng trong video.
            failures.append((i, e))
            _log(f"[dub_timeline] BỎ QUA đoạn {i} — TTS lỗi: {str(e)[:120]}")
        finally:
            await report()

    remaining = [(i, s) for i, s in items if i not in fitted_paths]
    await asyncio.gather(*(synth_one(i, seg) for i, seg in remaining))

    if failures:
        ratio = len(failures) / total
        _log(f"[dub_timeline] {len(failures)}/{total} đoạn TTS lỗi ({ratio:.0%}), đã bỏ qua.")
        if ratio > _MAX_FAIL_RATIO:
            raise RuntimeError(
                f"Quá nhiều đoạn TTS lỗi ({len(failures)}/{total}). "
                f"Chạy lại job sẽ dùng lại các đoạn đã xong. Lỗi đầu tiên: {failures[0][1]}"
            )

    ordered = sorted(fitted_paths.items())
    inputs: list[str] = []
    filter_parts: list[str] = []
    labels: list[str] = []
    for idx, (i, path) in enumerate(ordered):
        inputs += ["-i", path]
        start_ms = max(0, round(segments[i]["start"] * 1000))
        label = f"a{idx}"
        filter_parts.append(f"[{idx}:a]adelay={start_ms}:all=1[{label}]")
        labels.append(f"[{label}]")
    filter_parts.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,apad,atrim=0:{video_duration:.3f}[dubmix]"
    )
    filter_complex = ";".join(filter_parts)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", filter_complex, "-map", "[dubmix]", output_path]
    code, _, stderr = await run_command(cmd)
    if code != 0:
        raise RuntimeError(
            f"ffmpeg trộn dub timeline lỗi (code {code}): {stderr.decode(errors='replace')[-2000:]}"
        )

    return {"provider": locked_provider, "voice_code": locked_voice}
