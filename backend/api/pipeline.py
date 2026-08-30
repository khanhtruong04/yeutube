"""
Orchestrator pipeline job web: queued -> downloading -> transcribing ->
translating -> synthesizing -> mixing -> done (hoặc error).
Chỉ gọi lại engine có sẵn (transcribe) + module mới ở Phase 0
(translate/mixer/registry/ytdlp_download). Không sửa engine gốc.

Tải video dùng yt-dlp cho MỌI nền tảng, kể cả Douyin. Playwright crawler
(crawler.py) không dùng ở đây: Douyin trả 403 cho API aweme/detail khi bị điều
khiển tự động, kể cả khi cookies đăng nhập hợp lệ. yt-dlp có extractor Douyin
riêng, chỉ cần cookies -> ổn định hơn hẳn. crawler.py vẫn giữ nguyên cho CLI
(crawl hàng loạt theo feed/profile, dùng endpoint khác không bị chặn).
"""
import json
from pathlib import Path

from .. import jobs_store
from ..cookies_util import netscape_cookie_file
from ..mixer import generate_srt, mix_and_mux
from ..transcribe import transcribe_video
from ..translate import translate_transcript
from ..voices import registry
from ..ytdlp_download import download_via_ytdlp

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEB_ROOT = PROJECT_ROOT / "downloads" / "web"


async def _download(job: dict, job_dir: Path) -> tuple[Path, str, str]:
    """Trả về (folder chứa index.mp4, title, platform)."""
    url = job["video_url"]
    info = await download_via_ytdlp(url, job_dir, cookiefile=netscape_cookie_file())
    return job_dir, info.get("title", ""), info.get("extractor", "unknown")


async def run_job(job_id: str) -> None:
    job = await jobs_store.get_job(job_id)
    if job is None:
        return

    job_dir = WEB_ROOT / job_id

    try:
        await jobs_store.update_job(job_id, status="downloading")
        folder, title, platform = await _download(job, job_dir)
        await jobs_store.update_job(job_id, folder=str(folder), title=title, platform=platform)

        video_path = folder / "index.mp4"
        if not video_path.exists():
            raise RuntimeError(f"Không tìm thấy video sau khi tải: {video_path}")

        await jobs_store.update_job(job_id, status="transcribing")
        await transcribe_video(
            video_path=str(video_path),
            model=job["whisper_model"] or "base",
            language=job["stt_language"],
            aweme_id=job_id,
            update_index=False,  # job web track trong jobs.db, không ghi index.csv của CLI
        )
        transcript_path = folder / "transcript.json"
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

        await jobs_store.update_job(job_id, status="translating")
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

        await jobs_store.update_job(job_id, status="synthesizing")
        dub_path = folder / "dub_vi.mp3"
        tts = await registry.synthesize(
            transcript_vi["text"],
            gender=job.get("voice_gender"),
            provider=job["provider"],
            voice_code=job["voice_code"],
            speed=job["speed"],
            output=str(dub_path),
            log=print,
        )
        await jobs_store.update_job(job_id, provider=tts["provider"], voice_code=tts["voice_code"])

        await jobs_store.update_job(job_id, status="mixing")
        srt_path = folder / "subtitle_vi.srt"
        generate_srt(transcript_vi, str(srt_path))
        output_path = folder / "output_vi.mp4"
        await mix_and_mux(
            str(video_path), str(dub_path), str(output_path),
            volume_goc=job["volume_goc"], volume_dub=job["volume_dub"],
        )

        await jobs_store.update_job(job_id, status="done")

    except Exception as e:
        await jobs_store.update_job(job_id, status="error", error=str(e)[:2000])
