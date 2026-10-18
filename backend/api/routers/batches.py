"""Router cho batch: tạo batch, xem batch, phê duyệt/từ chối ghép video."""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ... import jobs_store
from ..pipeline import run_stage1_download
from ..schemas import BatchCreate, BatchOut

router = APIRouter(tags=["batches"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WEB_ROOT = PROJECT_ROOT / "downloads" / "web"


@router.post("/batches", response_model=BatchOut)
async def create_batch(payload: BatchCreate, background_tasks: BackgroundTasks):
    batch_id = uuid.uuid4().hex
    batch_folder = str(WEB_ROOT / f"batch_{batch_id}")
    Path(batch_folder).mkdir(parents=True, exist_ok=True)

    batch = await jobs_store.create_batch(
        batch_id=batch_id,
        total_jobs=len(payload.videos),
        folder=batch_folder,
    )

    # Tạo N job con, mỗi cái gắn batch_id + batch_order
    shared_settings = {
        "voice_gender": payload.voice_gender,
        "provider": payload.provider,
        "voice_code": payload.voice_code,
        "whisper_model": payload.whisper_model,
        "stt_language": payload.stt_language,
        "target_language": payload.target_language,
        "volume_goc": payload.volume_goc,
        "volume_dub": payload.volume_dub,
        "speed": payload.speed,
        "target_resolution": payload.target_resolution,
        "upscale": payload.upscale,
    }

    job_rows = []
    for item in sorted(payload.videos, key=lambda v: v.order):
        row = await jobs_store.create_job(
            video_url=item.video_url,
            batch_id=batch_id,
            batch_order=item.order,
            **shared_settings,
        )
        job_rows.append(row)
        background_tasks.add_task(run_stage1_download, row["id"])

    return BatchOut.from_row(batch, job_rows)


@router.get("/batches", response_model=list[BatchOut])
async def list_batches(limit: int = 20):
    rows = await jobs_store.list_batches(limit=limit)
    result = []
    for r in rows:
        job_rows = await jobs_store.get_batch_jobs(r["id"])
        result.append(BatchOut.from_row(r, job_rows))
    return result


@router.get("/batches/{batch_id}", response_model=BatchOut)
async def get_batch(batch_id: str):
    row = await jobs_store.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")
    job_rows = await jobs_store.get_batch_jobs(batch_id)
    return BatchOut.from_row(row, job_rows)


@router.post("/batches/{batch_id}/merge", response_model=BatchOut)
async def approve_merge(batch_id: str, background_tasks: BackgroundTasks):
    """User phê duyệt ghép video."""
    row = await jobs_store.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")
    if row["status"] != "awaiting_merge":
        raise HTTPException(
            status_code=409,
            detail=f"Batch đang ở trạng thái '{row['status']}', không phải 'awaiting_merge'.",
        )

    await jobs_store.update_batch(batch_id, merge_approved=1)
    background_tasks.add_task(_run_merge, batch_id)

    row = await jobs_store.get_batch(batch_id)
    job_rows = await jobs_store.get_batch_jobs(batch_id)
    return BatchOut.from_row(row, job_rows)


@router.post("/batches/{batch_id}/skip-merge", response_model=BatchOut)
async def skip_merge(batch_id: str):
    """User chọn không ghép, giữ riêng lẻ."""
    row = await jobs_store.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")
    if row["status"] != "awaiting_merge":
        raise HTTPException(
            status_code=409,
            detail=f"Batch đang ở trạng thái '{row['status']}', không phải 'awaiting_merge'.",
        )

    await jobs_store.update_batch(batch_id, merge_approved=0, status="done")

    row = await jobs_store.get_batch(batch_id)
    job_rows = await jobs_store.get_batch_jobs(batch_id)
    return BatchOut.from_row(row, job_rows)


@router.get("/batches/{batch_id}/next-job")
async def get_next_job(batch_id: str):
    """Trả về job_id tiếp theo trong batch cần thao tác của user
    (awaiting_masks hoặc awaiting_layout theo thứ tự batch_order).
    Trả 204 nếu không còn job nào cần thao tác.
    """
    row = await jobs_store.get_batch(batch_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")

    job_rows = await jobs_store.get_batch_jobs(batch_id)
    needs_action = [
        j for j in job_rows
        if j["status"] in ("awaiting_masks", "awaiting_layout")
    ]
    if not needs_action:
        return {"job_id": None, "done": True}
    # Lấy job có batch_order nhỏ nhất (thứ tự ưu tiên)
    next_job = min(needs_action, key=lambda j: j.get("batch_order") or 0)
    return {"job_id": next_job["id"], "batch_order": next_job.get("batch_order"), "done": False}


@router.post("/batches/{batch_id}/jobs/{job_id}/retry")
async def retry_batch_job(batch_id: str, job_id: str, background_tasks: BackgroundTasks):
    """Retry 1 job lỗi trong batch. Không thay đổi trạng thái batch nếu đang
    processing — chỉ giảm done_jobs lại nếu job trước đó đã được đếm vào.
    """
    from ..pipeline import run_prep, run_stage1_download
    from pathlib import Path

    batch = await jobs_store.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch không tồn tại")

    row = await jobs_store.get_job(job_id)
    if row is None or row.get("batch_id") != batch_id:
        raise HTTPException(status_code=404, detail="Job không thuộc batch này")
    if row["status"] != "error":
        raise HTTPException(
            status_code=409,
            detail=f"Job đang ở trạng thái '{row['status']}', không thể retry.",
        )

    # Nếu job đã từng done (đã được đếm vào done_jobs) → không cần giảm
    # Chỉ giảm done_jobs nếu batch đang awaiting_merge (tức là đã count đủ)
    if batch["status"] == "awaiting_merge":
        await jobs_store.update_batch(
            batch_id,
            status="processing",
            done_jobs=max(0, (batch["done_jobs"] or 0) - 1),
        )

    folder = Path(row["folder"]) if row.get("folder") else None
    if folder and (folder / "index.mp4").exists():
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
    from ..schemas import JobOut
    return JobOut.from_row(row)


async def _run_merge(batch_id: str) -> None:
    """Chạy ghép video cho batch."""
    from ...concat import concat_videos

    if not await jobs_store.claim_merge(batch_id):
        return

    try:
        job_rows = await jobs_store.get_batch_jobs(batch_id)
        batch = await jobs_store.get_batch(batch_id)
        if batch is None:
            return

        # Lấy danh sách output_vi.mp4 theo thứ tự batch_order
        video_paths = []
        for jr in job_rows:
            if jr["status"] != "done" or not jr.get("folder"):
                raise RuntimeError(
                    f"Job #{jr.get('batch_order', '?')} (id={jr['id']}) chưa done, "
                    f"không thể ghép. Status: {jr['status']}"
                )
            output = Path(jr["folder"]) / "output_vi.mp4"
            if not output.exists():
                raise RuntimeError(f"Không tìm thấy {output}")
            video_paths.append(str(output))

        output_path = str(Path(batch["folder"]) / "merged_output.mp4")
        await concat_videos(video_paths, output_path, log=print)

        await jobs_store.update_batch(batch_id, status="done")
        print(f"[batch] Ghép xong batch {batch_id} → {output_path}")

    except Exception as e:
        import traceback
        detail = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        print(f"[batch] Lỗi ghép batch {batch_id}:\n{detail}", flush=True)
        message = f"{type(e).__name__}: {e}".strip().rstrip(":").strip()
        await jobs_store.update_batch(batch_id, status="error", error=message[:2000])
