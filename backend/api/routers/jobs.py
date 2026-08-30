import json

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ... import jobs_store
from ..pipeline import run_stage1_download, run_stage2_process, run_stage3_render
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


@router.post("/jobs/{job_id}/masks", response_model=JobOut)
async def submit_masks(job_id: str, payload: SubmitMasks, background_tasks: BackgroundTasks):
    row = await jobs_store.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job không tồn tại")
    if row["status"] != "awaiting_masks":
        raise HTTPException(
            status_code=409,
            detail=f"Job đang ở trạng thái '{row['status']}', không phải 'awaiting_masks'.",
        )

    masks_json = json.dumps([m.model_dump() for m in payload.masks], ensure_ascii=False)
    await jobs_store.update_job(job_id, masks_json=masks_json)
    background_tasks.add_task(run_stage2_process, job_id)

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
    await jobs_store.update_job(
        job_id, text_layout_json=layout_json, subtitles_enabled=int(payload.enabled)
    )
    background_tasks.add_task(run_stage3_render, job_id)

    row = await jobs_store.get_job(job_id)
    return JobOut.from_row(row)
