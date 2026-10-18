"""
Ghép nhiều video output_vi.mp4 thành 1 file merged_output.mp4.

Xử lý 2 trường hợp:
  1. Tất cả video cùng resolution/aspect ratio → dùng concat demuxer (nhanh nhất,
     không re-encode nếu codec trùng).
  2. Video có resolution/aspect khác nhau → re-encode tất cả về cùng 1 chuẩn
     (scale + pad) rồi concat bằng filter_complex.
"""
from pathlib import Path

from .mixer import probe_video
from .proc_util import run_command


async def concat_videos(
    video_paths: list[str],
    output_path: str,
    log=print,
) -> None:
    """Ghép danh sách video theo thứ tự. video_paths đã được sắp xếp theo batch_order."""
    if not video_paths:
        raise ValueError("Danh sách video rỗng, không có gì để ghép.")
    if len(video_paths) == 1:
        # Chỉ 1 video: copy thẳng, không cần ffmpeg
        import shutil
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(video_paths[0], output_path)
        log(f"[concat] Chỉ 1 video, copy thẳng → {output_path}")
        return

    # Đo kích thước từng video
    dims = []
    for vp in video_paths:
        d = await probe_video(vp)
        dims.append(d)
        log(f"[concat] {Path(vp).name}: {d['width']}x{d['height']}")

    # Kiểm tra xem tất cả có cùng resolution không
    all_same = all(
        d["width"] == dims[0]["width"] and d["height"] == dims[0]["height"]
        for d in dims
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if all_same:
        log("[concat] Tất cả video cùng resolution → dùng concat demuxer (nhanh)")
        await _concat_demuxer(video_paths, output_path, log)
    else:
        log("[concat] Video có resolution khác nhau → re-encode + scale/pad")
        await _concat_filter(video_paths, dims, output_path, log)

    log(f"[concat] Hoàn tất → {output_path}")


async def _concat_demuxer(
    video_paths: list[str],
    output_path: str,
    log=print,
) -> None:
    """Concat nhanh bằng demuxer — không re-encode, giữ nguyên chất lượng."""
    out_dir = Path(output_path).parent
    list_file = out_dir / "concat_list.txt"

    # Viết file danh sách cho ffmpeg concat demuxer
    lines = []
    for vp in video_paths:
        # Escape dấu ' trong path
        safe = str(Path(vp).resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    code, _, stderr = await run_command(cmd)
    if code != 0:
        raise RuntimeError(
            f"ffmpeg concat demuxer lỗi (code {code}): {stderr.decode(errors='replace')[-2000:]}"
        )


async def _concat_filter(
    video_paths: list[str],
    dims: list[dict],
    output_path: str,
    log=print,
) -> None:
    """Concat bằng filter_complex — scale + pad tất cả về cùng 1 resolution."""
    # Chọn resolution đích: lấy max width/height từ tất cả video
    # Phát hiện hướng video chủ đạo (ngang hay dọc) dựa trên số lượng
    landscape_count = sum(1 for d in dims if d["width"] >= d["height"])
    portrait_count = len(dims) - landscape_count

    if landscape_count >= portrait_count:
        # Đa số ngang → chuẩn hoá về landscape
        target_w = max(d["width"] for d in dims)
        target_h = max(d["height"] for d in dims)
        if target_w < target_h:
            target_w, target_h = target_h, target_w
    else:
        # Đa số dọc → chuẩn hoá về portrait
        target_w = min(max(d["width"] for d in dims), max(d["height"] for d in dims))
        target_h = max(max(d["width"] for d in dims), max(d["height"] for d in dims))
        if target_w > target_h:
            target_w, target_h = target_h, target_w

    # Đảm bảo chẵn (libx264 yêu cầu)
    target_w = target_w + (target_w % 2)
    target_h = target_h + (target_h % 2)

    log(f"[concat] Target resolution: {target_w}x{target_h}")

    n = len(video_paths)
    inputs = []
    for vp in video_paths:
        inputs.extend(["-i", vp])

    # Build filter_complex
    filter_parts = []
    concat_inputs = []
    for i in range(n):
        label = f"v{i}"
        filter_parts.append(
            f"[{i}:v]scale={target_w}:{target_h}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1[{label}]"
        )
        concat_inputs.append(f"[{label}]")
        concat_inputs.append(f"[{i}:a]")

    concat_str = "".join(concat_inputs)
    filter_parts.append(f"{concat_str}concat=n={n}:v=1:a=1[vout][aout]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ]
    code, _, stderr = await run_command(cmd)
    if code != 0:
        raise RuntimeError(
            f"ffmpeg concat filter lỗi (code {code}): {stderr.decode(errors='replace')[-2000:]}"
        )
