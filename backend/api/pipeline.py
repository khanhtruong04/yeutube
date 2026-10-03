"""
Orchestrator pipeline job web — chạy phần máy tính SONG SONG với lúc user thao tác.

Các bước nặng (STT, dịch, TTS) không phụ thuộc vào box che hay vị trí phụ đề mà
user vẽ, nên không có lý do bắt chúng xếp hàng chờ. Chúng chạy ngay sau khi tải
xong, đúng lúc user đang kéo chuột:

    tải xong ─┬─> [user vẽ box che] ──> [user đặt vị trí phụ đề] ─┐
              └─> STT ─> dịch ─> TTS ─────────────────────────────┴─> render -> done

Hai nhánh gặp nhau ở `maybe_render`: nhánh nào xong sau thì nhánh đó khởi động
render. `jobs_store.claim_render` là phép so-sánh-rồi-đặt nguyên tử trong SQLite
nên dù 2 nhánh kết thúc cùng lúc cũng chỉ 1 bên render, không chạy trùng.

Job có 2 trục trạng thái độc lập:
  - `status`      : việc user đang thấy (awaiting_masks/awaiting_layout/waiting_prep/rendering/done)
  - `prep_status` : việc máy đang làm nền (transcribing/translating/synthesizing/ready)

Chỉ gọi lại engine có sẵn (transcribe) + module mới (translate/mixer/registry/
ytdlp_download/mask_overlay/subtitle_burn/render). Không sửa engine gốc.

Tải video dùng yt-dlp cho MỌI nền tảng. Riêng Douyin hiện yt-dlp hay thất bại ở
tầng chữ ký chống-bot ("Fresh cookies ... are needed", không phải do cookies hỏng)
nên có đường dự phòng qua trình duyệt thật — xem douyin_fallback.py.
"""
import asyncio
import json
import traceback
from pathlib import Path

from .. import jobs_store
from ..cookies_util import netscape_cookie_file
from ..douyin_fallback import download_douyin_via_browser, is_douyin
from ..dub_timeline import synthesize_timeline
from ..mixer import extract_thumbnail, generate_srt, probe_video
from ..render import render_final
from ..subtitle_burn import build_ass
from ..transcribe import transcribe_video
from ..translate import translate_transcript
from ..ytdlp_download import download_via_ytdlp

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEB_ROOT = PROJECT_ROOT / "downloads" / "web"

# Giữ tham chiếu tới task nền đang chạy — asyncio chỉ giữ weak reference, task
# không có ai giữ có thể bị thu gom giữa chừng và dừng im lặng.
_BG_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


async def _fail(job_id: str, e: Exception) -> None:
    # In traceback đầy đủ ra console: khi job lỗi, chỉ str(e) thường không đủ
    # để biết lỗi ở dòng nào trong stage nào.
    detail = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    print(f"[pipeline] job {job_id} lỗi:\n{detail}", flush=True)
    # Nhiều exception có str() rỗng (vd. TimeoutError()) -> luôn kèm tên class,
    # nếu không UI chỉ hiện ô lỗi trắng trơn không đoán được nguyên nhân.
    message = f"{type(e).__name__}: {e}".strip().rstrip(":").strip()
    await jobs_store.update_job(job_id, status="error", prep_status="error", error=message[:2000])


async def run_stage1_download(job_id: str) -> None:
    job = await jobs_store.get_job(job_id)
    if job is None:
        return
    job_dir = WEB_ROOT / job_id

    try:
        await jobs_store.update_job(job_id, status="downloading")
        if is_douyin(job["video_url"]):
            # Douyin đi thẳng đường trình duyệt, không thử yt-dlp trước: yt-dlp
            # bị chặn ở tầng chữ ký chống-bot nên hỏng 100% (xem douyin_fallback.py),
            # thử vẫn mất 24 giây và in ra một loạt lỗi đỏ "Fresh cookies" dễ bị
            # hiểu nhầm thành hỏng cookie.
            info = await download_douyin_via_browser(job["video_url"], job_dir, log=print)
        else:
            info = await download_via_ytdlp(
                job["video_url"],
                job_dir,
                cookiefile=netscape_cookie_file(),
                max_res=job.get("target_resolution") or 1080,
                log=print,
            )
        video_path = job_dir / "index.mp4"
        if not video_path.exists():
            raise RuntimeError(f"Không tìm thấy video sau khi tải: {video_path}")

        dims = await probe_video(str(video_path))
        await jobs_store.update_job(
            job_id,
            status="awaiting_masks",
            folder=str(job_dir),
            title=info.get("title", ""),
            platform=info.get("extractor", "unknown"),
            video_width=dims["width"],
            video_height=dims["height"],
            video_duration=dims["duration"],
        )
    except Exception as e:
        await _fail(job_id, e)
        return

    # Không chờ user: bắt đầu STT/dịch/TTS ngay bây giờ.
    _spawn(run_prep(job_id))


async def run_prep(job_id: str) -> None:
    """Toàn bộ phần máy làm: STT -> dịch -> TTS. Chạy song song với thao tác của
    user, kết thúc bằng prep_status='ready' rồi thử khởi động render."""
    job = await jobs_store.get_job(job_id)
    if job is None:
        return
    folder = Path(job["folder"])

    try:
        transcript_path = folder / "transcript.json"
        if not transcript_path.exists():
            await jobs_store.update_job(job_id, prep_status="transcribing")
            await transcribe_video(
                video_path=str(folder / "index.mp4"),
                model=job["whisper_model"] or "base",
                language=job["stt_language"],
                aweme_id=job_id,
                update_index=False,  # job web track trong jobs.db, không ghi index.csv của CLI
            )
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

        await jobs_store.update_job(job_id, prep_status="translating")
        transcript_vi_path = folder / "transcript-vi.json"
        if transcript_vi_path.exists():
            transcript_vi = json.loads(transcript_vi_path.read_text(encoding="utf-8"))
        else:
            transcript_vi = await translate_transcript(
                transcript, target_language=job["target_language"] or "vi"
            )
            transcript_vi_path.write_text(
                json.dumps(transcript_vi, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        # .srt rời không phụ thuộc gì vào layout -> xuất luôn ở đây.
        generate_srt(transcript_vi, str(folder / "subtitle_vi.srt"))

        # Luôn kèm bản .srt tiếng Anh, tái dùng bản dịch vi nếu target_language
        # đã là "en" để khỏi tốn thêm 1 lượt gọi LLM.
        transcript_en_path = folder / "transcript-en.json"
        if (job["target_language"] or "vi") == "en":
            transcript_en = transcript_vi
        elif transcript_en_path.exists():
            transcript_en = json.loads(transcript_en_path.read_text(encoding="utf-8"))
        else:
            transcript_en = await translate_transcript(transcript, target_language="en")
            transcript_en_path.write_text(
                json.dumps(transcript_en, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        generate_srt(transcript_en, str(folder / "subtitle_en.srt"))

        segments = transcript_vi.get("segments", [])
        await jobs_store.update_job(
            job_id, prep_status="synthesizing", progress_current=0, progress_total=len(segments)
        )

        async def on_progress(done: int, total: int) -> None:
            await jobs_store.update_job(job_id, progress_current=done, progress_total=total)

        tts = await synthesize_timeline(
            segments,
            gender=job.get("voice_gender"),
            provider=job["provider"],
            voice_code=job["voice_code"],
            speed=job["speed"],
            video_duration=job["video_duration"],
            work_dir=folder,
            output_path=str(folder / "dub_vi.mp3"),
            log=print,
            on_progress=on_progress,
        )
        await jobs_store.update_job(
            job_id, prep_status="ready", provider=tts["provider"], voice_code=tts["voice_code"]
        )
    except Exception as e:
        await _fail(job_id, e)
        return

    await maybe_render(job_id)


async def maybe_render(job_id: str) -> None:
    """Khởi động render nếu CẢ HAI đã sẵn sàng: máy xong phần nền, user xong phần
    layout. Gọi từ cả 2 nhánh — bên nào xong sau thì bên đó thắng, bên xong trước
    bị claim_render trả về False và không làm gì."""
    if not await jobs_store.claim_render(job_id):
        return
    await _render(job_id)


async def _render(job_id: str) -> None:
    job = await jobs_store.get_job(job_id)
    if job is None:
        return
    folder = Path(job["folder"])

    output_path = folder / "output_vi.mp4"

    try:
        transcript_vi = json.loads((folder / "transcript-vi.json").read_text(encoding="utf-8"))

        masks = json.loads(job["masks_json"] or "[]")
        ass_path = None
        if job.get("subtitles_enabled", 1):
            layout = json.loads(job["text_layout_json"] or "[]")
            ass_path = str(folder / "layout.ass")
            build_ass(transcript_vi, layout, job["video_width"], job["video_height"], ass_path)

        await render_final(
            video_path=str(folder / "index.mp4"),
            dub_path=str(folder / "dub_vi.mp3"),
            ass_path=ass_path,
            masks=masks,
            video_w=job["video_width"],
            video_h=job["video_height"],
            output_path=str(output_path),
            volume_goc=job["volume_goc"],
            volume_dub=job["volume_dub"],
            fit_dub_to_video=False,  # dub_timeline đã canh đúng video_duration sẵn
            upscale_to=(job.get("target_resolution") or 1080) if job.get("upscale") else None,
        )

        # Lấy từ video kết quả (không phải video gốc) để thumbnail phản ánh đúng
        # thứ người xem thấy: đã che vùng, đã phóng to nếu có bật.
        await extract_thumbnail(str(output_path), str(folder / "thumbnail.jpg"))

        await jobs_store.update_job(job_id, status="done")
    except Exception as e:
        await _fail(job_id, e)
