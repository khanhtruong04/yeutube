from fastapi import APIRouter, BackgroundTasks, HTTPException

from ... import jobs_store
from ..pipeline import run_job
from ..schemas import JobCreate, JobOut

router = APIRouter(tags=["jobs"])


@router.post("/jobs", response_model=JobOut)
async def create_job(payload: JobCreate, background_tasks: BackgroundTasks):
    row = await jobs_store.create_job(**payload.model_dump())
    background_tasks.add_task(run_job, row["id"])
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
