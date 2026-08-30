"use client";

import { useState } from "react";
import BoxEditor, { type EditableBox } from "./BoxEditor";
import { api, type Job, type MaskBox, fileUrl } from "@/lib/api";

type MaskItem = EditableBox & { type: "blur" | "solid"; maskColor: string };

const BLUR_COLOR = "#3b82f6"; // xanh dương — dễ phân biệt với solid
const SOLID_DEFAULT_COLOR = "#000000";

function newMask(duration: number): MaskItem {
  return {
    id: crypto.randomUUID(),
    xFrac: 0.35,
    yFrac: 0.4,
    wFrac: 0.3,
    hFrac: 0.15,
    tStart: 0,
    tEnd: duration,
    wholeVideo: true,
    borderColor: BLUR_COLOR,
    type: "blur",
    maskColor: SOLID_DEFAULT_COLOR,
  };
}

export default function MaskEditor({ job, onSubmitted }: { job: Job; onSubmitted: () => void }) {
  const duration = job.video_duration || 0;
  const [masks, setMasks] = useState<MaskItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!job.source_video_url || !job.video_width || !job.video_height) {
    return <p className="text-sm text-gray-500">Đang chờ thông tin video...</p>;
  }

  function update(id: string, patch: Partial<MaskItem>) {
    setMasks((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }

  function addMask() {
    setMasks((prev) => [...prev, newMask(duration)]);
  }

  function removeMask(id: string) {
    setMasks((prev) => prev.filter((m) => m.id !== id));
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: MaskBox[] = masks.map((m) => ({
        id: m.id,
        x: m.xFrac,
        y: m.yFrac,
        w: m.wFrac,
        h: m.hFrac,
        t_start: m.wholeVideo ? 0 : m.tStart,
        t_end: m.wholeVideo ? duration : m.tEnd,
        type: m.type,
        color: m.type === "solid" ? m.maskColor : null,
      }));
      await api.submitMasks(job.id, payload);
      onSubmitted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">Bước 1/2 — Che vùng cần ẩn (tuỳ chọn)</h2>
        <p className="text-sm text-gray-500">
          Kéo/resize box lên vùng có text/logo gốc cần che. Không thêm box nào cũng được — bấm Xác nhận để bỏ qua.
        </p>
      </div>

      <BoxEditor
        videoUrl={fileUrl(job.source_video_url)}
        videoWidth={job.video_width}
        videoHeight={job.video_height}
        boxes={masks.map((m) => ({ ...m, borderColor: m.type === "blur" ? BLUR_COLOR : m.maskColor }))}
        onChangeBox={update}
      />

      <button
        onClick={addMask}
        className="w-fit rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
      >
        + Thêm box che
      </button>

      <ul className="flex flex-col gap-2">
        {masks.map((m, i) => (
          <li key={m.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-800">
            <span className="font-medium">Box {i + 1}</span>

            <select
              value={m.type}
              onChange={(e) => update(m.id, { type: e.target.value as "blur" | "solid" })}
              className="rounded border border-gray-300 px-2 py-1 dark:border-gray-700"
            >
              <option value="blur">Làm mờ (blur)</option>
              <option value="solid">Màu đặc</option>
            </select>

            {m.type === "solid" && (
              <input
                type="color"
                value={m.maskColor}
                onChange={(e) => update(m.id, { maskColor: e.target.value })}
                className="h-7 w-10 rounded border border-gray-300 dark:border-gray-700"
              />
            )}

            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={m.wholeVideo}
                onChange={(e) => update(m.id, { wholeVideo: e.target.checked })}
              />
              Toàn video
            </label>

            {!m.wholeVideo && (
              <span className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={0}
                  max={duration}
                  value={m.tStart}
                  onChange={(e) => update(m.id, { tStart: Number(e.target.value) })}
                  className="w-16 rounded border border-gray-300 px-1.5 py-1 dark:border-gray-700"
                />
                s →
                <input
                  type="number"
                  min={0}
                  max={duration}
                  value={m.tEnd}
                  onChange={(e) => update(m.id, { tEnd: Number(e.target.value) })}
                  className="w-16 rounded border border-gray-300 px-1.5 py-1 dark:border-gray-700"
                />
                s
              </span>
            )}

            <button onClick={() => removeMask(m.id)} className="ml-auto text-red-600 hover:underline">
              Xoá
            </button>
          </li>
        ))}
      </ul>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="w-fit rounded-lg bg-black px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
      >
        {submitting ? "Đang xử lý..." : "Xác nhận, tiếp tục"}
      </button>
    </div>
  );
}
