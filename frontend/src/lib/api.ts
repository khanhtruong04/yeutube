const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8000";

/** Địa chỉ backend, suy ra theo hostname trình duyệt đang mở.
 *
 * Không hardcode "localhost" được: khi máy khác trong mạng mở trang qua IP LAN
 * thì "localhost" trỏ về chính máy họ, không phải máy chạy server. Lấy hostname
 * hiện tại nên mọi máy đều gọi đúng, không cần cấu hình riêng.
 * Tính trong hàm (không phải hằng ở module scope) để chạy lúc render trên trình
 * duyệt, vì khi render phía server thì chưa có `window`. */
function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
  }
  return `http://localhost:${API_PORT}`;
}

export type Provider = {
  name: string;
  available: boolean;
  reason: string | null;
};

export type Language = { code: string; name: string };

export type JobResult = {
  video_url: string;
  srt_url: string;
  dub_audio_url: string;
};

export type MaskBox = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  t_start: number;
  t_end: number;
  type: "blur" | "solid";
  color?: string | null;
};

export type TextLayoutZone = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  t_start: number;
  t_end: number;
  font_size?: number | null;
  color?: string | null;
};

export type Job = {
  id: string;
  video_url: string;
  title: string | null;
  platform: string | null;
  provider: string | null;
  voice_code: string | null;
  voice_gender: string;
  whisper_model: string;
  stt_language: string | null;
  target_language: string;
  volume_goc: number;
  volume_dub: number;
  speed: number | null;
  target_resolution: number;
  upscale: boolean;
  status: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  video_width: number | null;
  video_height: number | null;
  video_duration: number | null;
  masks: MaskBox[];
  text_layout: TextLayoutZone[];
  subtitles_enabled: boolean;
  progress_current: number;
  progress_total: number;
  source_video_url: string | null;
  result: JobResult | null;
};

export type JobCreatePayload = {
  video_url: string;
  voice_gender: "male" | "female";
  stt_language?: string | null;
  target_language: string;
  volume_goc: number;
  volume_dub: number;
  target_resolution: 720 | 1080;
  upscale: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function fileUrl(path: string): string {
  return `${apiBase()}${path}`;
}

export const api = {
  getProviders: () => request<Provider[]>("/api/providers"),
  getLanguages: () => request<Language[]>("/api/languages"),
  createJob: (payload: JobCreatePayload) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  submitMasks: (id: string, masks: MaskBox[]) =>
    request<Job>(`/api/jobs/${id}/masks`, { method: "POST", body: JSON.stringify({ masks }) }),
  submitLayout: (id: string, layout: TextLayoutZone[], enabled: boolean) =>
    request<Job>(`/api/jobs/${id}/layout`, {
      method: "POST",
      body: JSON.stringify({ layout, enabled }),
    }),
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Đang chờ",
  downloading: "Đang tải video",
  awaiting_masks: "Chờ chọn vùng che",
  transcribing: "Đang nhận diện giọng nói (STT)",
  translating: "Đang dịch",
  awaiting_layout: "Chờ đặt vị trí phụ đề",
  synthesizing: "Đang tổng hợp giọng đọc (TTS)",
  mixing: "Đang ghép video (có thể mất vài phút)",
  done: "Hoàn tất",
  error: "Lỗi",
};

// % tiến trình ước lượng theo từng bước của pipeline (mốc tĩnh, không đo thời
// gian thật) — riêng "synthesizing" được nội suy mịn hơn bằng progress_current/
// progress_total (số câu đã lồng tiếng / tổng số câu).
export const STATUS_PROGRESS: Record<string, number> = {
  queued: 5,
  downloading: 20,
  awaiting_masks: 30,
  transcribing: 45,
  translating: 60,
  awaiting_layout: 70,
  synthesizing: 80,
  mixing: 92,
  done: 100,
  error: 0,
};

const SYNTHESIZING_BAND: [number, number] = [
  STATUS_PROGRESS.synthesizing,
  STATUS_PROGRESS.mixing,
];

export function jobProgressPercent(job: Job): number {
  if (job.status === "synthesizing" && job.progress_total > 0) {
    const [start, end] = SYNTHESIZING_BAND;
    return Math.round(start + (end - start) * (job.progress_current / job.progress_total));
  }
  return STATUS_PROGRESS[job.status] ?? 0;
}
