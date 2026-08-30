"""
Orchestrator pipeline job web — chia 3 stage, dừng lại chờ user giữa mỗi stage:

  stage1 (download)              -> status="awaiting_masks"   -> chờ POST .../masks
  stage2 (transcribe+translate)  -> status="awaiting_layout"  -> chờ POST .../layout
  stage3 (tts+render)            -> status="done"

Mỗi stage là 1 FastAPI BackgroundTask riêng — endpoint nhận input từ user tự
trigger stage kế tiếp (xem backend/api/routers/jobs.py). Không cần queue/state
machine phức tạp vì "dừng" chỉ đơn giản là 1 background task kết thúc.

Chỉ gọi lại engine có sẵn (transcribe) + module mới (translate/mixer/registry/
ytdlp_download/mask_overlay/subtitle_burn/render). Không sửa engine gốc.

Tải video dùng yt-dlp cho MỌI nền tảng, kể cả Douyin (xem cookies_util.py) —
Douyin trả 403 cho Playwright crawler khi bị điều khiển tự động, kể cả cookies
hợp lệ; crawler.py vẫn dùng tốt cho CLI crawl feed/profile (endpoint khác).
"""
import json
import traceback
from pathlib import Path

from .. import jobs_store
from ..cookies_util import netscape_cookie_file
from ..dub_timeline import synthesize_timeline
from ..mixer import generate_srt, probe_video
from ..render import render_final
from ..subtitle_burn import build_ass
from ..transcribe import transcribe_video
from ..translate import translate_transcript
from ..ytdlp_download import download_via_ytdlp

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEB_ROOT = PROJECT_ROOT / "downloads" / "web"


async def _fail(job_id: str, e: Exception) -> None:
    # In traceback đầy đủ ra console: khi job lỗi, chỉ str(e) thường không đủ
    # để biết lỗi ở dòng nào trong stage nào.
    detail = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    print(f"[pipeline] job {job_id} lỗi:\n{detail}", flush=True)
    # Nhiều exception có str() rỗng (vd. TimeoutError()) -> luôn kèm tên class,
    # nếu không UI chỉ hiện ô lỗi trắng trơn không đoán được nguyên nhân.
    message = f"{type(e).__name__}: {e}".strip().rstrip(":").strip()
    await jobs_store.update_job(job_id, status="error", error=message[:2000])


async def run_stage1_download(job_id: str) -> None:
    job = await jobs_store.get_job(job_id)
    if job is None:
        return
    job_dir = WEB_ROOT / job_id

    try:
        await jobs_store.update_job(job_id, status="downloading")
        info = await download_via_ytdlp(
            job["video_url"],
            job_dir,
            cookiefile=netscape_cookie_file(),
            max_res=job.get("target_resolution") or 1080,
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


async def run_stage2_process(job_id: str) -> None:
    """Chạy sau khi user submit masks. Transcribe + dịch, rồi chuyển sang chờ layout."""
    job = await jobs_store.get_job(job_id)
    if job is None:
        return
    folder = Path(job["folder"])

    try:
        await jobs_store.update_job(job_id, status="transcribing")
        await transcribe_video(
            video_path=str(folder / "index.mp4"),
            model=job["whisper_model"] or "base",
            language=job["stt_language"],
            aweme_id=job_id,
            update_index=False,  # job web track trong jobs.db, không ghi index.csv của CLI
        )
        transcript = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))

        await jobs_store.update_job(job_id, status="translating")
        transcript_vi_path = folder / "transcript-vi.json"
        if transcript_vi_path.exists():
            transcript_vi = json.loads(transcript_vi_path.read_text(encoding="utf-8"))
        else:
            transcript_vi = await translate_transcript(transcript, target_language=job["target_language"] or "vi")
            transcript_vi_path.write_text(
                json.dumps(transcript_vi, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        await jobs_store.update_job(job_id, status="awaiting_layout")
    except Exception as e:
        await _fail(job_id, e)


async def run_stage3_render(job_id: str) -> None:
    """Chạy sau khi user submit layout. TTS -> burn mask+subtitle -> xuất kết quả."""
    job = await jobs_store.get_job(job_id)
    if job is None:
        return
    folder = Path(job["folder"])
    video_path = folder / "index.mp4"

    try:
        transcript_vi = json.loads((folder / "transcript-vi.json").read_text(encoding="utf-8"))
        segments = transcript_vi.get("segments", [])

        await jobs_store.update_job(job_id, status="synthesizing", progress_current=0, progress_total=len(segments))
        dub_path = folder / "dub_vi.mp3"

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
            output_path=str(dub_path),
            log=print,
            on_progress=on_progress,
        )
        await jobs_store.update_job(job_id, provider=tts["provider"], voice_code=tts["voice_code"])

        await jobs_store.update_job(job_id, status="mixing")
        srt_path = folder / "subtitle_vi.srt"
        generate_srt(transcript_vi, str(srt_path))

        masks = json.loads(job["masks_json"] or "[]")
        ass_path = None
        if job.get("subtitles_enabled", 1):
            layout = json.loads(job["text_layout_json"] or "[]")
            ass_path = str(folder / "layout.ass")
            build_ass(transcript_vi, layout, job["video_width"], job["video_height"], ass_path)

        output_path = folder / "output_vi.mp4"
        await render_final(
            video_path=str(video_path),
            dub_path=str(dub_path),
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

        await jobs_store.update_job(job_id, status="done")
    except Exception as e:
        await _fail(job_id, e)
