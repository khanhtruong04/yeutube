"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, fileUrl, STATUS_LABELS, type Job } from "@/lib/api";

const TERMINAL_STATUSES = new Set(["done", "error"]);

export default function JobPage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }, [jobId]);

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-10">
      <a href="/" className="text-sm text-gray-500 hover:underline">
        ← Tạo job mới
      </a>

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
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                <div className="h-full w-1/2 animate-pulse rounded-full bg-black dark:bg-white" />
              </div>
            )}
            {job.status === "error" && job.error && (
              <p className="mt-2 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                {job.error}
              </p>
            )}
          </div>

          {job.status === "done" && job.result && (
            <div className="flex flex-col gap-4 rounded-xl border border-gray-200 p-5 dark:border-gray-800">
              <h2 className="text-sm font-medium">Kết quả</h2>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video controls className="w-full rounded-lg" src={fileUrl(job.result.video_url)} />
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
