"use client";

import { useState } from "react";
import BoxEditor, { type EditableBox } from "./BoxEditor";
import { api, type Job, type TextLayoutZone, fileUrl } from "@/lib/api";

type LayoutItem = EditableBox & { fontSize: number; textColor: string };

const ZONE_COLOR = "#22c55e"; // xanh lá — phân biệt với mask
const DEFAULT_W = 0.5;
const DEFAULT_H = 0.08;

function newZone(duration: number, centerX: number, centerY: number): LayoutItem {
  return {
    id: crypto.randomUUID(),
    xFrac: centerX - DEFAULT_W / 2,
    yFrac: centerY - DEFAULT_H / 2,
    wFrac: DEFAULT_W,
    hFrac: DEFAULT_H,
    tStart: 0,
    tEnd: duration,
    wholeVideo: true,
    borderColor: ZONE_COLOR,
    label: "Vị trí phụ đề",
    fontSize: 28,
    textColor: "#FFFFFF",
  };
}

export default function LayoutEditor({ job, onSubmitted }: { job: Job; onSubmitted: () => void }) {
  const duration = job.video_duration || 0;
  const [enabled, setEnabled] = useState(true);
  const [zones, setZones] = useState<LayoutItem[]>(() => [newZone(duration, 0.5, 0.9)]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!job.source_video_url || !job.video_width || !job.video_height) {
    return <p className="text-sm text-gray-500">Đang chờ thông tin video...</p>;
  }

  function update(id: string, patch: Partial<LayoutItem>) {
    setZones((prev) => prev.map((z) => (z.id === id ? { ...z, ...patch } : z)));
  }

  function addZone() {
    setZones((prev) => [...prev, newZone(duration, 0.5, 0.9)]);
  }

  function removeZone(id: string) {
    setZones((prev) => prev.filter((z) => z.id !== id));
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const payload: TextLayoutZone[] = zones.map((z) => ({
        id: z.id,
        x: z.xFrac + z.wFrac / 2, // backend neo TÂM vùng, không phải góc trên-trái
        y: z.yFrac + z.hFrac / 2,
        w: z.wFrac,
        h: z.hFrac,
        t_start: z.wholeVideo ? 0 : z.tStart,
        t_end: z.wholeVideo ? duration : z.tEnd,
        font_size: z.fontSize,
        color: z.textColor,
      }));
      await api.submitLayout(job.id, enabled ? payload : [], enabled);
      onSubmitted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Bước 2/2 — Đặt vị trí phụ đề</h2>
          <p className="text-sm text-gray-500">
            Kéo/resize box để chỉnh vị trí và bề rộng dòng chữ, giống hệt thao tác ở bước che vùng.
            Thêm vùng mới nếu muốn phụ đề đổi vị trí ở 1 đoạn thời gian cụ thể.
          </p>
        </div>
        <label className="flex shrink-0 items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Hiển thị text đã dịch
        </label>
      </div>

      {!enabled && (
        <p className="rounded-lg bg-gray-50 p-3 text-sm text-gray-500 dark:bg-gray-900">
          Đã tắt — video xuất ra sẽ không burn phụ đề vào hình (file .srt rời vẫn được tạo bình thường).
        </p>
      )}

      {enabled && (
        <>
          <BoxEditor
            videoUrl={fileUrl(job.source_video_url)}
            videoWidth={job.video_width}
            videoHeight={job.video_height}
            boxes={zones}
            onChangeBox={update}
          />

          <button
            onClick={addZone}
            className="w-fit rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
          >
            + Thêm vùng vị trí
          </button>

          <ul className="flex flex-col gap-2">
            {zones.map((z, i) => (
              <li key={z.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-800">
                <span className="font-medium">Vùng {i + 1}</span>

                <label className="flex items-center gap-1.5">
                  Cỡ chữ
                  <input
                    type="number"
                    min={12}
                    max={72}
                    value={z.fontSize}
                    onChange={(e) => update(z.id, { fontSize: Number(e.target.value) })}
                    className="w-16 rounded border border-gray-300 px-1.5 py-1 dark:border-gray-700"
                  />
                </label>

                <input
                  type="color"
                  value={z.textColor}
                  onChange={(e) => update(z.id, { textColor: e.target.value })}
                  className="h-7 w-10 rounded border border-gray-300 dark:border-gray-700"
                />

                <label className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={z.wholeVideo}
                    onChange={(e) => update(z.id, { wholeVideo: e.target.checked })}
                  />
                  Toàn video
                </label>

                {!z.wholeVideo && (
                  <span className="flex items-center gap-1.5">
                    <input
                      type="number"
                      min={0}
                      max={duration}
                      value={z.tStart}
                      onChange={(e) => update(z.id, { tStart: Number(e.target.value) })}
                      className="w-16 rounded border border-gray-300 px-1.5 py-1 dark:border-gray-700"
                    />
                    s →
                    <input
                      type="number"
                      min={0}
                      max={duration}
                      value={z.tEnd}
                      onChange={(e) => update(z.id, { tEnd: Number(e.target.value) })}
                      className="w-16 rounded border border-gray-300 px-1.5 py-1 dark:border-gray-700"
                    />
                    s
                  </span>
                )}

                {zones.length > 1 && (
                  <button onClick={() => removeZone(z.id)} className="ml-auto text-red-600 hover:underline">
                    Xoá
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="w-fit rounded-lg bg-black px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
      >
        {submitting ? "Đang xử lý..." : "Xác nhận, tạo video"}
      </button>
    </div>
  );
}
