"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Job, type Language } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [videoUrl, setVideoUrl] = useState("");
  const [voiceGender, setVoiceGender] = useState<"male" | "female">("female");
  const [volumeGoc, setVolumeGoc] = useState(10);
  const [volumeDub, setVolumeDub] = useState(100);
  const [sttLanguage, setSttLanguage] = useState(""); // "" = auto-detect
  const [targetLanguage, setTargetLanguage] = useState("vi");
  const [languages, setLanguages] = useState<Language[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getLanguages().then(setLanguages).catch(() => {});
    api.listJobs().then(setJobs).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!videoUrl.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.createJob({
        video_url: videoUrl.trim(),
        voice_gender: voiceGender,
        stt_language: sttLanguage || null,
        target_language: targetLanguage,
        volume_goc: volumeGoc / 100,
        volume_dub: volumeDub / 100,
      });
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Video Dubbing</h1>
        <p className="text-sm text-gray-500">
          Dán link video, chọn giọng đọc và ngôn ngữ — hệ thống tự động tải, dịch, lồng tiếng.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-xl border border-gray-200 p-6 dark:border-gray-800">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="video_url" className="text-sm font-medium">
            Link video
          </label>
          <input
            id="video_url"
            type="text"
            required
            placeholder="https://www.douyin.com/... hoặc https://www.youtube.com/..."
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black dark:border-gray-700 dark:focus:border-white"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Giọng đọc</span>
          <div className="flex gap-4">
            {(["female", "male"] as const).map((g) => (
              <label key={g} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="voice_gender"
                  checked={voiceGender === g}
                  onChange={() => setVoiceGender(g)}
                />
                {g === "female" ? "Nữ" : "Nam"}
              </label>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="stt_language" className="text-sm font-medium">
              Ngôn ngữ gốc (STT)
            </label>
            <select
              id="stt_language"
              value={sttLanguage}
              onChange={(e) => setSttLanguage(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-700"
            >
              <option value="">Tự động nhận diện</option>
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="target_language" className="text-sm font-medium">
              Ngôn ngữ đích (dịch + .srt)
            </label>
            <select
              id="target_language"
              value={targetLanguage}
              onChange={(e) => setTargetLanguage(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm dark:border-gray-700"
            >
              {languages.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="volume_goc" className="text-sm font-medium">
              Âm lượng video gốc: {volumeGoc}%
            </label>
            <input
              id="volume_goc"
              type="range"
              min={0}
              max={100}
              value={volumeGoc}
              onChange={(e) => setVolumeGoc(Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="volume_dub" className="text-sm font-medium">
              Âm lượng giọng đọc: {volumeDub}%
            </label>
            <input
              id="volume_dub"
              type="range"
              min={0}
              max={100}
              value={volumeDub}
              onChange={(e) => setVolumeDub(Number(e.target.value))}
            />
          </div>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-black px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
        >
          {submitting ? "Đang tạo job..." : "Xử lý"}
        </button>
      </form>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-gray-500">Job gần đây</h2>
        {jobs.length === 0 && <p className="text-sm text-gray-400">Chưa có job nào.</p>}
        <ul className="flex flex-col gap-2">
          {jobs.map((j) => (
            <li key={j.id}>
              <a
                href={`/jobs/${j.id}`}
                className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-2.5 text-sm hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-900"
              >
                <span className="truncate">{j.title || j.video_url}</span>
                <span className="ml-3 shrink-0 text-xs text-gray-500">{j.status}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
