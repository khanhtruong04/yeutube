import json
from pathlib import Path
from typing import Literal

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
    # Trần độ phân giải theo cạnh ngắn khung hình; nguồn không có thì lấy bản cao nhất bên dưới.
    target_resolution: Literal[720, 1080] = 1080
    # Phóng to nếu video gốc thấp hơn mức trên. Chỉ giãn pixel, không nét thêm.
    upscale: bool = False


class MaskBox(BaseModel):
    id: str
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    t_start: float = Field(ge=0.0)
    t_end: float = Field(gt=0.0)
    type: Literal["blur", "solid"] = "blur"
    color: str | None = None  # chỉ dùng khi type="solid", vd "#000000" hoặc "black"


class TextLayoutZone(BaseModel):
    id: str
    x: float = Field(ge=0.0, le=1.0)  # tâm vùng, không phải góc
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(default=0.6, gt=0.0, le=1.0)  # bề rộng vùng (phân số) -> dùng để wrap dòng chữ
    h: float = Field(default=0.08, gt=0.0, le=1.0)
    t_start: float = Field(ge=0.0)
    t_end: float = Field(gt=0.0)
    font_size: int | None = None
    color: str | None = None  # "#RRGGBB"


class SubmitMasks(BaseModel):
    masks: list[MaskBox]


class SubmitLayout(BaseModel):
    layout: list[TextLayoutZone]
    enabled: bool = True  # False = tắt hẳn burn-in text dịch (vẫn xuất .srt rời)


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
    target_resolution: int = 1080
    upscale: bool = False
    status: str
    error: str | None = None
    created_at: str
    updated_at: str
    video_width: int | None = None
    video_height: int | None = None
    video_duration: float | None = None
    masks: list[MaskBox] = []
    text_layout: list[TextLayoutZone] = []
    subtitles_enabled: bool = True
    progress_current: int = 0
    progress_total: int = 0
    source_video_url: str | None = None  # video gốc, dùng để xem/vẽ box ở bước awaiting_masks/awaiting_layout
    result: dict | None = None

    @classmethod
    def from_row(cls, row: dict) -> "JobOut":
        result = None
        source_video_url = None
        if row.get("folder"):
            base = f"/files/{_rel_folder(row['folder'])}"
            source_video_url = f"{base}/index.mp4"
            if row.get("status") == "done":
                result = {
                    "video_url": f"{base}/output_vi.mp4",
                    "srt_url": f"{base}/subtitle_vi.srt",
                    "dub_audio_url": f"{base}/dub_vi.mp3",
                }

        masks = json.loads(row.get("masks_json") or "[]")
        text_layout = json.loads(row.get("text_layout_json") or "[]")

        return cls(**{
            **row,
            "result": result,
            "source_video_url": source_video_url,
            "masks": masks,
            "text_layout": text_layout,
            "target_resolution": row.get("target_resolution") or 1080,
            "upscale": bool(row.get("upscale")),
            "subtitles_enabled": bool(row.get("subtitles_enabled", 1)),
            "progress_current": row.get("progress_current") or 0,
            "progress_total": row.get("progress_total") or 0,
        })


def _rel_folder(folder: str) -> str:
    """Chuyển path folder tuyệt đối/tương đối thành path tương đối dưới downloads/ để build URL /files/."""
    p = Path(folder)
    parts = p.parts
    if "downloads" in parts:
        idx = parts.index("downloads")
        return "/".join(parts[idx + 1:])
    return p.as_posix()
