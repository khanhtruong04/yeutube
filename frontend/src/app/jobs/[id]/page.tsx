"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  api,
  batchApi,
  fileUrl,
  jobProgressPercent,
  prepProgressPercent,
  PREP_LABELS,
  STATUS_LABELS,
  type Job,
} from "@/lib/api";
import MaskEditor from "@/components/MaskEditor";
import LayoutEditor from "@/components/LayoutEditor";
import CookieStatusBanner from "@/components/CookieStatusBanner";

const TERMINAL_STATUSES = new Set(["done", "error"]);
const AWAITING_STATUSES = new Set(["awaiting_masks", "awaiting_layout"]);

export default function JobPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const jobId = params.id;
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  // Tăng lên sau khi chạy lại job để vòng poll (đã dừng khi job lỗi) chạy lại.
  const [pollKey, setPollKey] = useState(0);
  // Batch context — tổng số job trong batch (để hiện "Video X/N")
  const [batchTotalJobs, setBatchTotalJobs] = useState<number | null>(null);

  async function refetch() {
    if (!jobId) return;
    try {
      const j = await api.getJob(jobId);
      setJob(j);
      return j;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được job");
    }
  }

  // Lấy tổng số job trong batch để hiện "Video X/N"
  useEffect(() => {
    if (!job?.batch_id) return;
    batchApi.getBatch(job.batch_id)
      .then((b) => setBatchTotalJobs(b.total_jobs))
      .catch(() => {});
  }, [job?.batch_id]);

  /** Sau khi user submit masks/layout, tự navigate sang job tiếp theo trong batch
   *  (nếu có), hoặc về trang batch nếu tất cả đã xong thao tác. */
  async function afterSubmit() {
    const j = await refetch();
    if (!j?.batch_id) return; // job đơn lẻ — không navigate
    try {
      const next = await batchApi.getNextJob(j.batch_id);
      if (!next.done && next.job_id && next.job_id !== jobId) {
        router.push(`/jobs/${next.job_id}`);
      } else if (next.done) {
        // Tất cả job đã xong thao tác → về trang batch
        router.push(`/batches/${j.batch_id}`);
      }
      // Nếu next.job_id === jobId (vẫn còn thao tác trên job này) → giữ nguyên
    } catch {
      // Lỗi gọi next-job → chỉ refetch
    }
  }

  async function handleRetry() {
    setRetrying(true);
    setError(null);
    try {
      if (job?.batch_id) {
        // Retry trong context batch — dùng endpoint riêng để điều chỉnh done_jobs
        setJob(await batchApi.retryBatchJob(job.batch_id, jobId));
      } else {
        setJob(await api.retryJob(jobId));
      }
      setPollKey((k) => k + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không chạy lại được job");
    } finally {
      setRetrying(false);
    }
  }

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const j = await api.getJob(jobId);
        if (cancelled) return;
        setJob(j);
        if (!TERMINAL_STATUSES.has(j.status)) {
          timer = setTimeout(poll, 3000);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Không tải được job");
      }
    }
    poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, pollKey]);

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-10">
      {/* Navigation header */}
      <div className="flex items-center gap-3">
        {job?.batch_id ? (
          <>
            <a
              href={`/batches/${job.batch_id}`}
              className="text-sm text-gray-500 hover:underline"
            >
              ← Quay về Batch
            </a>
            {job.batch_order !== null && batchTotalJobs !== null && (
              <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                Video {job.batch_order} / {batchTotalJobs}
              </span>
            )}
          </>
        ) : (
          <a href="/" className="text-sm text-gray-500 hover:underline">
            ← Tạo job mới
          </a>
        )}
      </div>

      <CookieStatusBanner />

      {error && <p className="text-sm text-red-600">{error}</p>}
      {!job && !error && <p className="text-sm text-gray-500">Đang tải...</p>}

      {job && (
        <div className="flex flex-col gap-6">
          <div>
            <h1 className="text-xl font-semibold break-all">{job.title || job.video_url}</h1>
            <p className="text-sm text-gray-500 break-all">{job.video_url}</p>
          </div>

          <div className="flex flex-col gap-2 rounded-xl border border-gray-200 p-5 dark:border-gray-800">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Trạng thái</span>
              <StatusBadge status={job.status} />
            </div>
            {job.status !== "done" && job.status !== "error" && (
              <div className="mt-2">
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                  <div
                    className="h-full rounded-full bg-black transition-all duration-500 dark:bg-white"
                    style={{ width: `${jobProgressPercent(job)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">{jobProgressPercent(job)}%</p>
              </div>
            )}

            {/* Nhánh nền chạy song song với thao tác của user — hiện riêng để
                thấy máy vẫn đang làm việc trong lúc mình kéo box. */}
            {job.status !== "done" && job.status !== "error" && job.prep_status !== "pending" && (
              <div className="mt-3 rounded-lg bg-gray-50 p-3 text-xs dark:bg-gray-900">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-gray-600 dark:text-gray-400">
                    Máy đang xử lý nền: {PREP_LABELS[job.prep_status] || job.prep_status}
                    {job.prep_status === "synthesizing" && job.progress_total > 0 && (
                      <> — câu {job.progress_current}/{job.progress_total}</>
                    )}
                  </span>
                  <span className="shrink-0 tabular-nums text-gray-500">
                    {prepProgressPercent(job)}%
                  </span>
                </div>
                {AWAITING_STATUSES.has(job.status) && job.prep_status !== "ready" && (
                  <p className="mt-1 text-gray-500">
                    Cứ thao tác bình thường — phần này chạy song song, không phải chờ.
                  </p>
                )}
              </div>
            )}
            {job.status === "error" && (
              <div className="mt-2 flex flex-col items-start gap-2">
                {job.error && (
                  <p className="w-full rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                    {job.error}
                  </p>
                )}
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={retrying}
                  className="rounded-lg bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
                >
                  {retrying ? "Đang chạy lại..." : "Chạy lại"}
                </button>
                <p className="text-xs text-gray-500">
                  Dùng lại video và các phần đã xong, chỉ làm lại phần còn thiếu.
                </p>
              </div>
            )}
          </div>

          {job.status === "awaiting_masks" && (
            <MaskEditor job={job} onSubmitted={afterSubmit} />
          )}
          {job.status === "awaiting_layout" && (
            <LayoutEditor job={job} onSubmitted={afterSubmit} />
          )}

          {job.status === "done" && job.result && (
            <div className="flex flex-col gap-4 rounded-xl border border-gray-200 p-5 dark:border-gray-800">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium">Kết quả</h2>
                {job.batch_id && (
                  <a
                    href={`/batches/${job.batch_id}`}
                    className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                  >
                    Xem trang Batch →
                  </a>
                )}
              </div>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video
                controls
                poster={fileUrl(job.result.thumbnail_url)}
                className="w-full rounded-lg"
                src={fileUrl(job.result.video_url)}
              />

              <div className="flex flex-col gap-2">
                <span className="text-xs text-gray-500">Ảnh thumbnail (khung hình đầu tiên)</span>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={fileUrl(job.result.thumbnail_url)}
                  alt="Thumbnail khung hình đầu tiên của video"
                  className="w-40 rounded-lg border border-gray-200 dark:border-gray-800"
                />
              </div>

              <div className="flex flex-wrap gap-3 text-sm">
                <a className="underline" href={fileUrl(job.result.video_url)} download>
                  Tải video (.mp4)
                </a>
                <a className="underline" href={fileUrl(job.result.srt_url)} download>
                  Tải phụ đề (.srt)
                </a>
                <a className="underline" href={fileUrl(job.result.dub_audio_url)} download>
                  Tải audio giọng đọc (.mp3)
                </a>
                <a className="underline" href={fileUrl(job.result.thumbnail_url)} download>
                  Tải thumbnail (.jpg)
                </a>
              </div>
            </div>
          )}

          <dl className="grid grid-cols-2 gap-y-2 text-sm text-gray-500">
            <dt>Giọng đọc</dt>
            <dd>{job.voice_gender === "male" ? "Nam" : "Nữ"} ({job.provider || "—"})</dd>
            <dt>Âm lượng gốc / giọng đọc</dt>
            <dd>{Math.round(job.volume_goc * 100)}% / {Math.round(job.volume_dub * 100)}%</dd>
            <dt>Ngôn ngữ STT</dt>
            <dd>{job.stt_language || "Tự động"}</dd>
            <dt>Ngôn ngữ đích</dt>
            <dd>{job.target_language}</dd>
            <dt>Độ phân giải</dt>
            <dd>
              {job.target_resolution}p tối đa
              {job.video_width && job.video_height && ` — tải về ${job.video_width}x${job.video_height}`}
              {job.upscale && ` — phóng to lên ${job.target_resolution}p`}
            </dd>
          </dl>
        </div>
      )}
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const label = STATUS_LABELS[status] || status;
  const color =
    status === "done"
      ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300"
      : status === "error"
        ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300"
        : "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300";
  return <span className={`rounded-full px-3 py-1 text-xs font-medium ${color}`}>{label}</span>;
}
