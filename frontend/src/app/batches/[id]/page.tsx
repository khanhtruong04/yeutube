"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  batchApi,
  fileUrl,
  BATCH_STATUS_LABELS,
  STATUS_LABELS,
  PREP_LABELS,
  type Batch,
} from "@/lib/api";

const POLL_MS = 3000;

export default function BatchDetailPage() {
  const params = useParams();
  const router = useRouter();
  const batchId = params.id as string;

  const [batch, setBatch] = useState<Batch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mergeLoading, setMergeLoading] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchBatch = useCallback(async () => {
    try {
      const b = await batchApi.getBatch(batchId);
      setBatch(b);
      return b;
    } catch {
      return null;
    }
  }, [batchId]);

  useEffect(() => {
    fetchBatch();
    timerRef.current = setInterval(fetchBatch, POLL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchBatch]);

  // Dừng polling khi batch ở trạng thái cuối
  useEffect(() => {
    if (batch && (batch.status === "done" || batch.status === "error")) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, [batch?.status]);

  async function handleMerge() {
    setMergeLoading(true);
    setError(null);
    try {
      const b = await batchApi.approveMerge(batchId);
      setBatch(b);
      // Restart polling để theo dõi trạng thái merge
      if (!timerRef.current) {
        timerRef.current = setInterval(fetchBatch, POLL_MS);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi khi ghép video");
    }
    setMergeLoading(false);
  }

  async function handleSkip() {
    setMergeLoading(true);
    setError(null);
    try {
      const b = await batchApi.skipMerge(batchId);
      setBatch(b);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
    setMergeLoading(false);
  }

  async function handleRetryJob(jobId: string) {
    setRetryingJobId(jobId);
    setError(null);
    try {
      await batchApi.retryBatchJob(batchId, jobId);
      // Restart polling
      if (!timerRef.current) {
        timerRef.current = setInterval(fetchBatch, POLL_MS);
      }
      await fetchBatch();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể retry job này");
    } finally {
      setRetryingJobId(null);
    }
  }

  async function goToNextJob() {
    try {
      const next = await batchApi.getNextJob(batchId);
      if (next.job_id) {
        router.push(`/jobs/${next.job_id}`);
      }
    } catch {
      setError("Không tìm được job tiếp theo");
    }
  }

  if (!batch) {
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
        <p className="text-sm text-gray-400">Đang tải batch...</p>
      </main>
    );
  }

  const doneCount = batch.jobs.filter((j) => j.status === "done").length;
  const errorCount = batch.jobs.filter((j) => j.status === "error").length;
  const needsActionJobs = batch.jobs.filter(
    (j) => j.status === "awaiting_masks" || j.status === "awaiting_layout"
  );
  const progressPercent = Math.round((batch.done_jobs / batch.total_jobs) * 100);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-10">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push("/")}
          className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
        >
          ← Trang chủ
        </button>
      </div>

      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">
          📦 Batch — {batch.total_jobs} video
        </h1>
        <div className="flex items-center gap-3">
          <span
            className={[
              "rounded-full px-2.5 py-1 text-xs font-medium",
              batch.status === "done"
                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                : batch.status === "error"
                  ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                  : batch.status === "awaiting_merge"
                    ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                    : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
            ].join(" ")}
          >
            {BATCH_STATUS_LABELS[batch.status] || batch.status}
          </span>
          <span className="text-xs text-gray-500">
            {batch.done_jobs}/{batch.total_jobs} video xong
          </span>
        </div>
      </header>

      {/* Progress bar */}
      {batch.status === "processing" && (
        <div className="flex flex-col gap-1">
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs text-gray-500">{progressPercent}% hoàn tất</span>
        </div>
      )}

      {/* Banner CTA: còn job cần thao tác */}
      {batch.status === "processing" && needsActionJobs.length > 0 && (
        <div className="flex items-center justify-between rounded-xl border-2 border-blue-400 bg-blue-50 px-5 py-4 dark:border-blue-600 dark:bg-blue-900/10">
          <div>
            <p className="text-sm font-semibold text-blue-800 dark:text-blue-300">
              🎨 {needsActionJobs.length} video đang chờ bạn thao tác
            </p>
            <p className="text-xs text-blue-600 dark:text-blue-400">
              Vẽ vùng che và đặt vị trí phụ đề — máy đang xử lý STT/dịch/TTS song song.
            </p>
          </div>
          <button
            onClick={goToNextJob}
            className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600"
          >
            Thao tác ngay →
          </button>
        </div>
      )}

      {/* Error */}
      {(batch.error || error) && (
        <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {batch.error || error}
        </p>
      )}

      {/* Bảng job con */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500 dark:border-gray-700">
              <th className="w-14 px-4 py-3 text-center">STT</th>
              <th className="px-4 py-3">Video</th>
              <th className="w-36 px-4 py-3">Trạng thái</th>
              <th className="w-36 px-4 py-3">Xử lý nền</th>
              <th className="w-20 px-4 py-3 text-center">Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {batch.jobs.map((job) => (
              <tr
                key={job.id}
                className="border-b border-gray-100 last:border-b-0 dark:border-gray-800"
              >
                <td className="px-4 py-3 text-center font-mono text-gray-500">
                  {job.batch_order}
                </td>
                <td className="max-w-0 px-4 py-3">
                  <p className="truncate text-sm" title={job.title || job.video_url}>
                    {job.title || job.video_url}
                  </p>
                  {job.error && (
                    <p className="mt-0.5 truncate text-xs text-red-500" title={job.error}>
                      {job.error}
                    </p>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={[
                      "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                      job.status === "done"
                        ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                        : job.status === "error"
                          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
                    ].join(" ")}
                  >
                    {STATUS_LABELS[job.status] || job.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500">
                  {PREP_LABELS[job.prep_status] || job.prep_status}
                  {job.prep_status === "synthesizing" && job.progress_total > 0 && (
                    <span className="ml-1">
                      ({job.progress_current}/{job.progress_total})
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-center">
                  {(job.status === "awaiting_masks" || job.status === "awaiting_layout") && (
                    <a
                      href={`/jobs/${job.id}`}
                      className="rounded-md bg-black px-2.5 py-1 text-xs font-medium text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200"
                    >
                      Thao tác
                    </a>
                  )}
                  {job.status === "done" && (
                    <a
                      href={`/jobs/${job.id}`}
                      className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                    >
                      Xem
                    </a>
                  )}
                  {job.status === "error" && (
                    <button
                      onClick={() => handleRetryJob(job.id)}
                      disabled={retryingJobId === job.id}
                      className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50 dark:border-red-700 dark:text-red-400 dark:hover:bg-red-900/20"
                    >
                      {retryingJobId === job.id ? "⏳ Đang retry..." : "🔄 Retry"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Prompt ghép video */}
      {batch.status === "awaiting_merge" && (
        <div className="flex flex-col gap-4 rounded-xl border-2 border-yellow-400 bg-yellow-50 p-6 dark:border-yellow-600 dark:bg-yellow-900/10">
          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold">
              ✅ Tất cả {batch.total_jobs} video đã xử lý xong!
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Bạn có muốn ghép {batch.total_jobs} video trên thành 1 video theo thứ tự STT không?
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={handleMerge}
              disabled={mergeLoading}
              className="rounded-lg bg-black px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-200"
            >
              {mergeLoading ? "Đang xử lý..." : "🎬 Ghép video"}
            </button>
            <button
              onClick={handleSkip}
              disabled={mergeLoading}
              className="rounded-lg border border-gray-300 px-5 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              Giữ riêng lẻ
            </button>
          </div>
        </div>
      )}

      {/* Đang ghép */}
      {batch.status === "merging" && (
        <div className="flex items-center gap-3 rounded-xl border border-blue-200 bg-blue-50 p-5 dark:border-blue-800 dark:bg-blue-900/10">
          <span className="animate-spin text-lg">⏳</span>
          <p className="text-sm font-medium text-blue-700 dark:text-blue-400">
            Đang ghép {batch.total_jobs} video thành 1... Vui lòng đợi.
          </p>
        </div>
      )}

      {/* Kết quả ghép xong */}
      {batch.status === "done" && batch.merge_approved && batch.merged_video_url && (
        <div className="flex flex-col gap-4 rounded-xl border border-green-200 bg-green-50 p-6 dark:border-green-800 dark:bg-green-900/10">
          <h2 className="text-lg font-semibold text-green-700 dark:text-green-400">
            🎬 Video đã ghép xong!
          </h2>
          <video
            controls
            className="w-full rounded-lg"
            src={fileUrl(batch.merged_video_url)}
          >
            Trình duyệt không hỗ trợ video.
          </video>
          <a
            href={fileUrl(batch.merged_video_url)}
            download
            className="self-start rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
          >
            ⬇ Tải merged_output.mp4
          </a>
        </div>
      )}

      {/* Done nhưng không ghép */}
      {batch.status === "done" && batch.merge_approved === false && (
        <div className="rounded-xl border border-green-200 bg-green-50 p-5 dark:border-green-800 dark:bg-green-900/10">
          <p className="text-sm font-medium text-green-700 dark:text-green-400">
            ✅ Tất cả video đã xong! Bạn đã chọn giữ riêng lẻ — xem từng video ở bảng trên.
          </p>
        </div>
      )}
    </main>
  );
}
