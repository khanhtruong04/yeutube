"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  batchApi,
  fileUrl,
  jobProgressPercent,
  prepProgressPercent,
  PREP_LABELS,
  STATUS_LABELS,
  BATCH_STATUS_LABELS,
  type Job,
  type Language,
  type JobCreatePayload,
  type BatchCreatePayload,
  type FreeVoice,
  type Batch,
  voicePreviewUrl,
} from "@/lib/api";
import CookieStatusBanner from "@/components/CookieStatusBanner";
import BatchInputTable, { type BatchRow } from "@/components/BatchInputTable";

type InputMode = "single" | "batch";

export default function HomePage() {
  const router = useRouter();

  // ── Chế độ nhập ──────────────────────────────────────────────────────────
  const [mode, setMode] = useState<InputMode>("single");

  // ── Single mode ──────────────────────────────────────────────────────────
  const [videoUrl, setVideoUrl] = useState("");

  // ── Batch mode ───────────────────────────────────────────────────────────
  const [batchRows, setBatchRows] = useState<BatchRow[]>([
    { order: 1, url: "" },
    { order: 2, url: "" },
  ]);

  // ── Cài đặt chung ───────────────────────────────────────────────────────
  const [voiceGender, setVoiceGender] = useState<"male" | "female">("female");
  const [volumeGoc, setVolumeGoc] = useState(10);
  const [volumeDub, setVolumeDub] = useState(100);
  const [sttLanguage, setSttLanguage] = useState(""); // "" = auto-detect
  const [targetLanguage, setTargetLanguage] = useState("vi");
  const [resolution, setResolution] = useState<720 | 1080>(1080);
  const [upscale, setUpscale] = useState(false);
  const [languages, setLanguages] = useState<Language[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freeVoices, setFreeVoices] = useState<FreeVoice[]>([]);
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // voice_id đang tải/đang phát nghe thử
  const [previewLoading, setPreviewLoading] = useState<string | null>(null);
  const [previewPlaying, setPreviewPlaying] = useState<string | null>(null);

  function stopPreview() {
    audioRef.current?.pause();
    audioRef.current = null;
    setPreviewLoading(null);
    setPreviewPlaying(null);
  }

  function togglePreview(v: FreeVoice) {
    const wasThis = previewPlaying === v.voice_id || previewLoading === v.voice_id;
    stopPreview();
    if (wasThis) return;
    const audio = new Audio(voicePreviewUrl(v.voice_id, v.provider || "nghitts"));
    audioRef.current = audio;
    setPreviewLoading(v.voice_id);
    audio.onplaying = () => {
      setPreviewLoading(null);
      setPreviewPlaying(v.voice_id);
    };
    audio.onended = () => {
      if (audioRef.current === audio) stopPreview();
    };
    audio.onerror = () => {
      if (audioRef.current === audio) {
        stopPreview();
        setError(`Không nghe thử được giọng ${v.model_name}`);
      }
    };
    audio.play().catch(() => {});
  }

  useEffect(() => () => audioRef.current?.pause(), []);

  useEffect(() => {
    api.getLanguages().then(setLanguages).catch(() => {});
    api.listJobs().then(setJobs).catch(() => {});
    batchApi.listBatches().then(setBatches).catch(() => {});
    api
      .getFreeVoices()
      .then((voices) => {
        setFreeVoices(voices);
        // Tự động chọn giọng đầu tiên theo gender mặc định (female)
        const firstFemale = voices.find((v) => v.gender === "female");
        if (firstFemale) setSelectedVoiceId(firstFemale.voice_id);
      })
      .catch(() => {});
  }, []);

  // Lọc giọng theo gender đang chọn
  const femaleVoices = freeVoices.filter((v) => v.gender === "female");
  const maleVoices = freeVoices.filter((v) => v.gender === "male");
  const filteredVoices = voiceGender === "female" ? femaleVoices : maleVoices;

  // Khi đổi gender, tự động chọn giọng đầu tiên của gender mới
  const handleGenderChange = (g: "male" | "female") => {
    setVoiceGender(g);
    const voiceList = g === "female" ? femaleVoices : maleVoices;
    if (voiceList.length > 0) {
      setSelectedVoiceId(voiceList[0].voice_id);
    } else {
      setSelectedVoiceId("");
    }
  };

  // ── Submit ───────────────────────────────────────────────────────────────

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      if (mode === "single") {
        await handleSubmitSingle();
      } else {
        await handleSubmitBatch();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Có lỗi xảy ra");
      setSubmitting(false);
    }
  }

  async function handleSubmitSingle() {
    if (!videoUrl.trim()) return;
    const payload: JobCreatePayload = {
      video_url: videoUrl.trim(),
      voice_gender: voiceGender,
      stt_language: sttLanguage || null,
      target_language: targetLanguage,
      volume_goc: volumeGoc / 100,
      volume_dub: volumeDub / 100,
      target_resolution: resolution,
      upscale,
    };
    if (selectedVoiceId) {
      payload.voice_code = selectedVoiceId;
      const matched = freeVoices.find((v) => v.voice_id === selectedVoiceId);
      payload.provider = matched?.provider || "nghitts";
    }
    const job = await api.createJob(payload);
    router.push(`/jobs/${job.id}`);
  }

  async function handleSubmitBatch() {
    const validRows = batchRows.filter((r) => r.url.trim().length > 0);
    if (validRows.length === 0) {
      setError("Vui lòng nhập ít nhất 1 link video.");
      setSubmitting(false);
      return;
    }

    // Kiểm tra link trùng
    const urls = validRows.map((r) => r.url.trim());
    const unique = new Set(urls);
    if (unique.size !== urls.length) {
      setError("Có link video bị trùng. Vui lòng kiểm tra lại.");
      setSubmitting(false);
      return;
    }

    const payload: BatchCreatePayload = {
      videos: validRows.map((r, i) => ({ order: i + 1, video_url: r.url.trim() })),
      voice_gender: voiceGender,
      stt_language: sttLanguage || null,
      target_language: targetLanguage,
      volume_goc: volumeGoc / 100,
      volume_dub: volumeDub / 100,
      target_resolution: resolution,
      upscale,
    };
    if (selectedVoiceId) {
      payload.voice_code = selectedVoiceId;
      const matched = freeVoices.find((v) => v.voice_id === selectedVoiceId);
      payload.provider = matched?.provider || "nghitts";
    }
    const batch = await batchApi.createBatch(payload);
    router.push(`/batches/${batch.id}`);
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold">Video Dubbing</h1>
        <p className="text-sm text-gray-500">
          Dán link video, chọn giọng đọc và ngôn ngữ — hệ thống tự động tải, dịch, lồng tiếng.
        </p>
      </header>

      <CookieStatusBanner />

      <form onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-xl border border-gray-200 p-6 dark:border-gray-800">
        {/* Toggle: Video đơn / Batch */}
        <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
          {(["single", "batch"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={[
                "flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                mode === m
                  ? "bg-white text-black shadow-sm dark:bg-gray-700 dark:text-white"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200",
              ].join(" ")}
            >
              {m === "single" ? "🎬 Video đơn" : "📦 Batch — Nhiều video"}
            </button>
          ))}
        </div>

        {/* Nhập liệu theo chế độ */}
        {mode === "single" ? (
          <div className="flex flex-col gap-1.5">
            <label htmlFor="video_url" className="text-sm font-medium">
              Link video
            </label>
            <input
              id="video_url"
              type="text"
              required={mode === "single"}
              placeholder="https://www.douyin.com/... hoặc https://www.youtube.com/..."
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-black dark:border-gray-700 dark:focus:border-white"
            />
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">
              Danh sách video (tối đa 9 link)
            </span>
            <BatchInputTable rows={batchRows} onChange={setBatchRows} />
          </div>
        )}

        {/* Chọn giọng đọc theo giới tính */}
        <div className="flex flex-col gap-3">
          <span className="text-sm font-medium">Giọng đọc</span>

          {/* Toggle Nữ / Nam */}
          <div className="flex gap-2">
            {(["female", "male"] as const).map((g) => (
              <button
                key={g}
                type="button"
                id={`gender-${g}`}
                onClick={() => handleGenderChange(g)}
                className={[
                  "flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                  voiceGender === g
                    ? "border-black bg-black text-white dark:border-white dark:bg-white dark:text-black"
                    : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-transparent dark:text-gray-300 dark:hover:bg-gray-800",
                ].join(" ")}
              >
                <span>{g === "female" ? "♀" : "♂"}</span>
                <span>{g === "female" ? "Giọng nữ" : "Giọng nam"}</span>
                {/* Badge số lượng */}
                {(g === "female" ? femaleVoices : maleVoices).length > 0 && (
                  <span
                    className={[
                      "rounded-full px-1.5 py-0.5 text-xs",
                      voiceGender === g
                        ? "bg-white/20 text-white dark:bg-black/20 dark:text-black"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
                    ].join(" ")}
                  >
                    {(g === "female" ? femaleVoices : maleVoices).length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Danh sách giọng theo gender đang chọn */}
          {filteredVoices.length > 0 ? (
            <div className="flex flex-col gap-2 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
              <span className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-400">
                {voiceGender === "female" ? "Danh sách giọng nữ" : "Danh sách giọng nam"}
              </span>
              <div className="flex flex-col gap-1.5">
                {filteredVoices.map((v) => (
                  <label
                    key={v.voice_id}
                    htmlFor={`voice-${v.voice_id}`}
                    className={[
                      "flex cursor-pointer flex-col rounded-lg border px-3 py-2.5 transition-colors",
                      selectedVoiceId === v.voice_id
                        ? "border-black bg-black/5 dark:border-white dark:bg-white/5"
                        : "border-transparent hover:border-gray-200 hover:bg-gray-50 dark:hover:border-gray-700 dark:hover:bg-gray-800/50",
                    ].join(" ")}
                  >
                    <div className="flex items-center gap-2">
                      <input
                        type="radio"
                        id={`voice-${v.voice_id}`}
                        name="freeVoice"
                        value={v.voice_id}
                        checked={selectedVoiceId === v.voice_id}
                        onChange={() => setSelectedVoiceId(v.voice_id)}
                        className="accent-black dark:accent-white"
                      />
                      <span className="text-sm font-medium">{v.model_name}</span>
                      <button
                        type="button"
                        id={`preview-${v.voice_id}`}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          togglePreview(v);
                        }}
                        title="Nghe thử giọng đọc"
                        className="ml-auto flex shrink-0 items-center gap-1 rounded-full border border-gray-300 px-2.5 py-1 text-xs hover:bg-gray-100 dark:border-gray-700 dark:hover:bg-gray-800"
                      >
                        {previewLoading === v.voice_id
                          ? "⏳ Đang tạo..."
                          : previewPlaying === v.voice_id
                            ? "⏹ Dừng"
                            : "▶ Nghe thử"}
                      </button>
                    </div>
                    {v.description && (
                      <p className="ml-5 mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                        {v.description}
                      </p>
                    )}
                  </label>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-400">
              Đang tải danh sách giọng...
            </p>
          )}
        </div>

        {/* Độ phân giải */}
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-medium">Độ phân giải video</span>
          <div className="flex gap-4">
            {([1080, 720] as const).map((r) => (
              <label key={r} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="resolution"
                  checked={resolution === r}
                  onChange={() => setResolution(r)}
                />
                {r === 1080 ? "1080p (HD)" : "720p"}
              </label>
            ))}
          </div>
          <p className="text-xs text-gray-500">
            Đây là mức tối đa. Video gốc không có sẵn độ phân giải này thì lấy bản cao nhất bên dưới.
          </p>

          <label className="mt-1 flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={upscale}
              onChange={(e) => setUpscale(e.target.checked)}
            />
            <span>
              Phóng to cho đủ {resolution}p nếu video gốc thấp hơn
              <span className="block text-xs text-gray-500">
                Chỉ kéo giãn khung hình — không nét thêm, file nặng hơn và render lâu hơn. Bật khi nơi đăng bắt buộc độ phân giải tối thiểu.
              </span>
            </span>
          </label>
        </div>

        {/* Ngôn ngữ */}
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

        {/* Âm lượng */}
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
          {submitting
            ? mode === "single"
              ? "Đang tạo job..."
              : "Đang tạo batch..."
            : mode === "single"
              ? "Xử lý"
              : `Xử lý ${batchRows.filter((r) => r.url.trim()).length} video`}
        </button>
      </form>

      {/* Batch gần đây */}
      {batches.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-gray-500">Batch gần đây</h2>
          <ul className="flex flex-col gap-2">
            {batches.map((b) => (
              <li key={b.id}>
                <a
                  href={`/batches/${b.id}`}
                  className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-2.5 text-sm hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-900"
                >
                  <span className="truncate">
                    📦 Batch {b.total_jobs} video
                    <span className="ml-2 text-xs text-gray-400">
                      ({b.done_jobs}/{b.total_jobs} xong)
                    </span>
                  </span>
                  <span className="ml-3 shrink-0 text-xs text-gray-500">
                    {BATCH_STATUS_LABELS[b.status] || b.status}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

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
