import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ... import jobs_store
from ..pipeline import maybe_render, run_prep, run_stage1_download
from ..schemas import JobCreate, JobOut, SubmitLayout, SubmitMasks

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobOut)
async def create_job(payload: JobCreate, background_tasks: BackgroundTasks):
    row = await jobs_store.create_job(**payload.model_dump())
    background_tasks.add_task(run_stage1_download, row["id"])
    return JobOut.from_row(row)


@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(limit: int = 50):
    rows = await jobs_store.list_jobs(limit=limit)
    return [JobOut.from_row(r) for r in rows]


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str):
    row = await jobs_store.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    return JobOut.from_row(row)


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
async def retry_job(job_id: str, background_tasks: BackgroundTasks):
    """Chạy lại job lỗi, tiếp tục từ chỗ dở thay vì làm lại từ đầu.

    Mọi thứ đã làm xong đều nằm trong folder job (video, transcript, từng đoạn
    TTS) và các bước đều kiểm tra file có sẵn trước khi làm lại, nên chạy lại
    chỉ tốn công cho phần còn thiếu — vd. 11 đoạn TTS hỏng giữa 71 đoạn."""
    row = await jobs_store.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    if row["status"] not in ("error", "waiting_prep", "rendering", "queued"):
        raise HTTPException(
            status_code=409,
            detail=f"Job đang ở trạng thái '{row['status']}', không thể chạy lại.",
        )

    if row["folder"] and (Path(row["folder"]) / "index.mp4").exists():
        # Trả status về đúng bước user đang dang dở, vì lúc lỗi nó bị ghi đè
        # thành 'error' và mất dấu.
        if row["masks_json"] is None:
            status = "awaiting_masks"
        elif row["text_layout_json"] is None:
            status = "awaiting_layout"
        else:
            status = "waiting_prep"
        await jobs_store.update_job(job_id, status=status, prep_status="pending", error=None)
        background_tasks.add_task(run_prep, job_id)
    else:
        await jobs_store.update_job(job_id, status="queued", prep_status="pending", error=None)
        background_tasks.add_task(run_stage1_download, job_id)

    row = await jobs_store.get_job(job_id)
    return JobOut.from_row(row)


@router.post("/jobs/{job_id}/masks", response_model=JobOut)
async def submit_masks(job_id: str, payload: SubmitMasks):
    """Chỉ lưu box che rồi cho user sang bước đặt phụ đề. Không khởi động STT ở
    đây — nó đã chạy nền từ lúc tải xong, song song với lúc user vẽ box."""
    row = await jobs_store.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    if row["status"] != "awaiting_masks":
        raise HTTPException(
            status_code=409,
            detail=f"Job đang ở trạng thái '{row['status']}', không phải 'awaiting_masks'.",
        )

    masks_json = json.dumps([m.model_dump() for m in payload.masks], ensure_ascii=False)
    await jobs_store.update_job(job_id, masks_json=masks_json, status="awaiting_layout")

    row = await jobs_store.get_job(job_id)
    return JobOut.from_row(row)


@router.post("/jobs/{job_id}/layout", response_model=JobOut)
async def submit_layout(job_id: str, payload: SubmitLayout, background_tasks: BackgroundTasks):
    row = await jobs_store.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    if row["status"] != "awaiting_layout":
        raise HTTPException(
            status_code=409,
            detail=f"Job đang ở trạng thái '{row['status']}', không phải 'awaiting_layout'.",
        )

    layout_json = json.dumps([z.model_dump() for z in payload.layout], ensure_ascii=False)
    # waiting_prep = user xong việc, chỉ còn chờ máy. Nếu máy đã xong sẵn thì
    # maybe_render bên dưới khởi động render ngay.
    await jobs_store.update_job(
        job_id,
        text_layout_json=layout_json,
        subtitles_enabled=int(payload.enabled),
        status="waiting_prep",
    )
    background_tasks.add_task(maybe_render, job_id)

    row = await jobs_store.get_job(job_id)
    return JobOut.from_row(row)
