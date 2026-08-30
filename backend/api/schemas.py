from pydantic import BaseModel, Field


class JobCreate(BaseModel):
    video_url: str
    voice_gender: str = "female"  # "male" | "female"
    provider: str | None = None  # advanced override, không lộ ra UI mặc định
    voice_code: str | None = None  # advanced override, không lộ ra UI mặc định
    whisper_model: str = "base"
    stt_language: str | None = None  # None = auto-detect
    target_language: str = "vi"
    volume_goc: float = Field(default=0.10, ge=0.0, le=1.0)
    volume_dub: float = Field(default=1.0, ge=0.0, le=1.0)
    speed: float | None = Field(default=None, ge=0.5, le=2.0)


class JobOut(BaseModel):
    id: str
    video_url: str
    title: str | None = None
    platform: str | None = None
    provider: str | None = None
    voice_code: str | None = None
    voice_gender: str
    whisper_model: str
    stt_language: str | None = None
    target_language: str
    volume_goc: float
    volume_dub: float
    speed: float | None = None
    status: str
    error: str | None = None
    created_at: str
    updated_at: str
    result: dict | None = None

    @classmethod
    def from_row(cls, row: dict) -> "JobOut":
        result = None
        if row.get("status") == "done" and row.get("folder"):
            base = f"/files/{_rel_folder(row['folder'])}"
            result = {
                "video_url": f"{base}/output_vi.mp4",
                "srt_url": f"{base}/subtitle_vi.srt",
                "dub_audio_url": f"{base}/dub_vi.mp3",
            }
        return cls(**{**row, "result": result})


def _rel_folder(folder: str) -> str:
    """Chuyển path folder tuyệt đối/tương đối thành path tương đối dưới downloads/ để build URL /files/."""
    from pathlib import Path
    p = Path(folder)
    parts = p.parts
    if "downloads" in parts:
        idx = parts.index("downloads")
        return "/".join(parts[idx + 1:])
    return p.as_posix()
