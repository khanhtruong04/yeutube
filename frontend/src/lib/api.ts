const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

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
  status: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  result: JobResult | null;
};

export type JobCreatePayload = {
  video_url: string;
  voice_gender: "male" | "female";
  stt_language?: string | null;
  target_language: string;
  volume_goc: number;
  volume_dub: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
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
  return `${API_BASE}${path}`;
}

export const api = {
  getProviders: () => request<Provider[]>("/api/providers"),
  getLanguages: () => request<Language[]>("/api/languages"),
  createJob: (payload: JobCreatePayload) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Đang chờ",
  downloading: "Đang tải video",
  transcribing: "Đang nhận diện giọng nói (STT)",
  translating: "Đang dịch",
  synthesizing: "Đang tổng hợp giọng đọc (TTS)",
  mixing: "Đang trộn âm thanh & ghép video",
  done: "Hoàn tất",
  error: "Lỗi",
};
