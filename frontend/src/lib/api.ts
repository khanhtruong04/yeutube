const API_PORT = process.env.NEXT_PUBLIC_API_PORT || "8000";

/** Địa chỉ backend, suy ra theo hostname trình duyệt đang mở.
 *
 * Không hardcode "localhost" được: khi máy khác trong mạng mở trang qua IP LAN
 * thì "localhost" trỏ về chính máy họ, không phải máy chạy server. Lấy hostname
 * hiện tại nên mọi máy đều gọi đúng, không cần cấu hình riêng.
 * Tính trong hàm (không phải hằng ở module scope) để chạy lúc render trên trình
 * duyệt, vì khi render phía server thì chưa có `window`.
 */
function apiBase(): string {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${API_PORT}`;
  }
  return `http://localhost:${API_PORT}`;
}

export type Provider = { name: string; available: boolean; reason: string | null };
export type Language = { code: string; name: string };
export type CookieStatus = {
  ok: boolean;
  reason: "missing" | "expired" | null;
  message: string | null;
  expires_at: string | null;
  updated_at: string | null;
};
export type JobResult = {
  video_url: string;
  srt_url: string;
  dub_audio_url: string;
  thumbnail_url: string;
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
  prep_status: string;
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
  // optional override for voice selection
  provider?: string;
  voice_code?: string;
};
export type FreeVoice = {
  voice_id: string;
  model_name: string;
  gender: string;
  provider?: string;
  description?: string;
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
  getFreeVoices: () => request<FreeVoice[]>("/api/free-voices"),
  getCookieStatus: () => request<CookieStatus>("/api/cookies/status"),
  createJob: (payload: JobCreatePayload) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  retryJob: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
  submitMasks: (id: string, masks: MaskBox[]) =>
    request<Job>(`/api/jobs/${id}/masks`, { method: "POST", body: JSON.stringify({ masks }) }),
  submitLayout: (id: string, layout: TextLayoutZone[], enabled: boolean) =>
    request<Job>(`/api/jobs/${id}/layout`, { method: "POST", body: JSON.stringify({ layout, enabled }) }),
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Đang chờ",
  downloading: "Đang tải video",
  awaiting_masks: "Chờ chọn vùng che",
  awaiting_layout: "Chờ đặt vị trí phụ đề",
  waiting_prep: "Đang chờ máy xử lý xong",
  rendering: "Đang ghép video (có thể mất vài phút)",
  done: "Hoàn tất",
  error: "Lỗi",
};

/** Việc máy đang làm nền, song song với thao tác của người dùng. */
export const PREP_LABELS: Record<string, string> = {
  pending: "Đang chờ",
  transcribing: "Đang nhận diện giọng nói (STT)",
  translating: "Đang dịch",
  synthesizing: "Đang tổng hợp giọng đọc (TTS)",
  ready: "Đã xong, sẵn sàng ghép",
  error: "Lỗi",
};

const PREP_PROGRESS: Record<string, number> = {
  pending: 0,
  transcribing: 20,
  translating: 45,
  synthesizing: 60,
  ready: 100,
  error: 0,
};

const SYNTHESIZING_BAND: [number, number] = [PREP_PROGRESS.synthesizing, 100];

/** Tiến độ phần máy làm nền (STT -> dịch -> TTS). */
export function prepProgressPercent(job: Job): number {
  if (job.prep_status === "synthesizing" && job.progress_total > 0) {
    const [start, end] = SYNTHESIZING_BAND;
    return Math.round(start + (end - start) * (job.progress_current / job.progress_total));
  }
  return PREP_PROGRESS[job.prep_status] ?? 0;
}

/** Tiến độ tổng thể hiển thị cho người dùng. */
export function jobProgressPercent(job: Job): number {
  if (job.status === "done") return 100;
  if (job.status === "error") return 0;
  if (job.status === "downloading" || job.status === "queued") return 10;
  if (job.status === "rendering") return 95;
  // Giai đoạn user thao tác: tiến độ thật nằm ở nhánh nền, quy về khoảng 15-90%.
  return 15 + Math.round(prepProgressPercent(job) * 0.75);
}
