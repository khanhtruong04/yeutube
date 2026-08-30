# Đặc tả hệ thống: Web Lồng Giọng Đọc Tự Động Cho Video (Video Dubbing System)

> Tài liệu này mô tả việc **xây dựng phiên bản web** cho công cụ tải video + lồng tiếng Việt vốn chạy dưới dạng **CLI Python + Claude Code Agent Skills** tại project này. Lớp web (API + UI) bọc lên engine Python có sẵn trong [backend/](backend/), không viết lại từ đầu.
>
> **Trạng thái: Phase 0 → 2 đã hoàn thành và chạy được end-to-end.** Cách chạy xem [README.md](README.md). Phase 3–4 (tuỳ biến nâng cao, đa người dùng) còn ở dạng kế hoạch — xem mục 10.
>
> **Đã mở rộng thêm ngoài Phase 0-2 gốc**: job giờ dừng lại **2 lần chờ thao tác tay** — vẽ box che (mask, blur/màu đặc, theo khoảng thời gian) sau khi tải video, và đặt vùng vị trí phụ đề (burn-in cứng, theo khoảng thời gian) sau khi dịch xong. Xem chi tiết ở mục 4b bên dưới. Đã test end-to-end qua API thật, xác nhận bằng mắt (trích frame) mask + subtitle burn đúng vị trí/thời điểm.

---

## 0. Hiện trạng dự án (bắt buộc đọc trước khi triển khai)

Dự án hiện tại **chưa có web/API** — toàn bộ pipeline chạy qua CLI (`backend/.venv/bin/python3 -m backend ...`) hoặc qua 3 Claude Code skill: `/video-download`, `/douyin-crawler`, `/voice-over`.

| Thành phần | Đã có sẵn (tái dùng được) | File |
|---|---|---|
| Tải video đa nền tảng | `yt-dlp` (YouTube, TikTok, Facebook, Instagram, Bilibili, Twitter/X, Vimeo, 1000+ trang) | skill `video-download` |
| Tải video Douyin riêng | Crawler bằng Playwright (feed Tinh Tuyển, profile, link detail) — Douyin không dùng được yt-dlp trực tiếp | [backend/crawler.py](backend/crawler.py), [backend/downloader.py](backend/downloader.py) |
| Speech-to-Text | `faster-whisper` chạy **local** (CPU, int8), model `tiny → large-v3-turbo`, auto-detect ngôn ngữ hoặc chỉ định | [backend/transcribe.py](backend/transcribe.py) |
| Dịch transcript | **Không có API dịch** — hiện do AI agent (Claude) đọc/ghi file trực tiếp trong lúc chạy skill, không phải service tự động | skill `voice-over`, bước 2 |
| Text-to-Speech | 4 provider có sẵn, tự phát hiện qua `.env`: **OmniVoice** (self-host LAN, voice cloning, có tham số `speed` 0.5–2.0 để khớp timing), **Vbee**, **ElevenLabs**, **OpenAI**, ngoài ra còn **Edge TTS** (miễn phí, chưa gắn vào skill) | [backend/voices/](backend/voices/) |
| Danh mục giọng đọc | CSV theo từng provider, có cột `category/gender/age_group/use_case/description` — không chỉ Nam/Nữ mà nhiều giọng vùng miền | [voice/*.csv](voice/) |
| Trộn audio + ghép video | `ffmpeg` filter `amix`, hiện **hardcode** `volume=0.10` (gốc) / `volume=1.0` (dub) | skill `voice-over`, bước 6 |
| Sinh phụ đề SRT | Đã có, sinh từ `transcript-vi.json`, giữ timestamp gốc | skill `voice-over`, bước 5 |
| Lưu trữ | Thư mục local `downloads/<platform>/<title>__<id>/`, kèm `index.csv` track trạng thái | [backend/store.py](backend/store.py) |

**Khoảng trống đã lấp khi lên web** (không có sẵn trong CLI):
- ✅ REST API + job chạy nền (`backend/api/`) — thay cho việc chạy tuần tự trong 1 phiên terminal.
- ✅ Dịch tự động qua OpenRouter (`backend/translate.py`) — thay cho việc Claude Code agent dịch tay.
- ✅ Volume mixing tham số hoá + tự đồng bộ thời lượng (`backend/mixer.py`).
- ✅ DB riêng cho job web: `jobs.db` (SQLite) — `index.csv` của CLI giữ nguyên, không đụng tới.
- ✅ UI web (`frontend/`).
- ❌ Chưa có auth / tài khoản / lịch sử theo user (Phase 4).

---

## 1. Tổng quan

Phiên bản web cho phép người dùng dán link video (bất kỳ trang nào yt-dlp hỗ trợ, hoặc link Douyin), hệ thống tự động: tải video → tách audio → nhận diện giọng nói bằng Whisper (local, không qua API ngoài) → dịch nội dung sang ngôn ngữ đích → tổng hợp giọng đọc mới bằng 1 trong các TTS provider đã tích hợp (OmniVoice / Vbee / ElevenLabs / OpenAI / Edge TTS) → trộn với audio gốc theo tỉ lệ âm lượng người dùng chọn → xuất video hoàn chỉnh kèm phụ đề `.srt`.

Khác với đặc tả gốc (giả định dùng dịch vụ STT/dịch/TTS đám mây từ đầu), hệ thống này **ưu tiên chạy local/self-host trước** (Whisper local, OmniVoice self-host) và chỉ dùng API trả phí (Vbee/ElevenLabs/OpenAI) khi có key trong `.env`, để tối ưu chi phí.

---

## 2. Input (Đầu vào từ người dùng)

| # | Trường dữ liệu | Mô tả | Kiểu dữ liệu |
|---|-----------------|-------|--------------|
| 1 | Link video | URL bất kỳ yt-dlp hỗ trợ (YouTube, TikTok, Facebook, Instagram...) hoặc link Douyin (feed/profile/detail — xử lý qua crawler riêng), hoặc file upload trực tiếp | string / file |
| 2 | Provider TTS | Chọn provider: `omnivoice` (mặc định, miễn phí, cần server LAN), `vbee`, `elevenlabs`, `openai`, `edgetts` — hoặc để hệ thống tự chọn theo key đang cấu hình | enum |
| 3 | Giọng đọc | Chọn 1 voice cụ thể từ danh mục của provider đã chọn (`voice/<provider>.csv`) — lọc theo `gender`, `age_group`, `category`; hoặc để AI/hệ thống tự gợi ý theo nội dung | string (voice code) |
| 4 | Âm lượng video gốc | Tỉ lệ âm lượng audio gốc khi trộn (0–100%, mặc định 10%) | number (slider) |
| 5 | Âm lượng giọng đọc | Tỉ lệ âm lượng giọng đọc TTS khi trộn (0–100%, mặc định 100%) | number (slider) |
| 6 | Model Whisper | Model STT: `tiny/base/small/medium/large/large-v3-turbo` (đánh đổi tốc độ ↔ độ chính xác) | dropdown |
| 7 | Ngôn ngữ STT | Ngôn ngữ nhận diện giọng gốc — để trống để Whisper tự auto-detect | dropdown/select |
| 8 | Ngôn ngữ đích | Ngôn ngữ dịch + TTS đầu ra (mặc định: Tiếng Việt) | dropdown/select |
| 9 | Tốc độ đọc (speed) | Riêng cho OmniVoice: 0.5–2.0, dùng để khớp timing giọng đọc với đoạn gốc | number (slider) |

---

## 3. Output (Đầu ra hệ thống trả về)

| # | Sản phẩm đầu ra | Mô tả | Tương ứng file hiện có |
|---|------------------|-------|-------|
| 1 | Video đã lồng giọng | Video hoàn chỉnh, audio gốc + giọng đọc mới trộn theo đúng tỉ lệ đã chọn | `output_vi.mp4` |
| 2 | File phụ đề `.srt` | Phụ đề đúng ngôn ngữ đích, timeline khớp video (đã implement) | `subtitle_vi.srt` |
| 3 | Audio giọng đọc riêng | File TTS gốc, cho phép tải riêng để dùng nơi khác | `dub_vi.mp3` |
| 4 | Transcript gốc + bản dịch (JSON) | Có timestamp từng đoạn, phục vụ chỉnh sửa tay trước khi TTS lại | `transcript.json`, `transcript-vi.json` |

---

## 4. Luồng xử lý (Pipeline)

```
[1] Nhận link video / upload
        │
        ▼
[2] Tải video: yt-dlp (đa nền tảng) hoặc crawler Playwright riêng cho Douyin
        │
        ▼
[3] Tách audio (ffmpeg, 16kHz mono wav) + Speech-to-Text bằng faster-whisper (local)
        │
        ▼
[4] Sinh transcript.json (text + segments[start,end,text]) theo ngôn ngữ gốc
        │
        ▼
[5] Dịch nội dung sang ngôn ngữ đích, giữ nguyên timestamp
        (hiện tại: AI agent dịch tay qua Read/Write — cần thay bằng gọi LLM API cho bản web)
        │
        ▼
[6] Text-to-Speech theo provider + voice đã chọn (OmniVoice/Vbee/ElevenLabs/OpenAI/EdgeTTS)
        │
        ▼
[7] (Tuỳ chọn) Đồng bộ thời lượng bằng tham số speed của TTS (OmniVoice hỗ trợ sẵn 0.5–2.0)
        │
        ▼
[8] Trộn audio: ffmpeg filter amix — (gốc × volume_goc) + (dub × volume_dub), tham số hoá thay vì hardcode
        │
        ▼
[9] Mux video + audio đã trộn (ffmpeg, giữ nguyên video stream -c:v copy)
        │
        ▼
[10] Sinh file .srt từ transcript đã dịch (giữ timestamp)
        │
        ▼
[11] Xuất kết quả: output_vi.mp4 + subtitle_vi.srt + dub_vi.mp3, cập nhật trạng thái job
```

---

## 5. Kiến trúc hệ thống (đề xuất)

### 5.1 Nguyên tắc
Tái dùng tối đa code Python trong [backend/](backend/) làm "engine" — **không viết lại** crawler, downloader, transcribe, hay các adapter TTS trong [backend/voices/](backend/voices/). Lớp web chỉ là wrapper gọi các hàm async đã có (`crawl_jingxuan`, `crawl_user_profile`, `crawl_single_url`, `download_videos`, `transcribe_video`, `run_tts`).

### 5.2 Frontend
- Framework: React / Next.js
- Thành phần UI:
  - Ô nhập link video / upload file
  - Chọn provider TTS + giọng đọc (danh sách load từ `/api/voices?provider=...`, hiển thị theo `category/gender/age_group`)
  - Slider âm lượng video gốc / giọng đọc
  - Chọn model Whisper + ngôn ngữ STT + ngôn ngữ đích
  - Nút "Xử lý" + thanh tiến trình (progress bar, poll `GET /api/jobs/{id}`)
  - Khu vực preview video kết quả + nút tải `.srt` / `.mp3` riêng
  - Trình chỉnh sửa transcript (sửa tay `transcript-vi.json` trước khi TTS lại — vì bước dịch AI có thể sai)

### 5.3 Backend
- Framework: **Python FastAPI**, cùng ngôn ngữ với `backend/` hiện có → import trực tiếp module, không cần viết lại bằng ngôn ngữ khác.
- Job queue: Celery / RQ (các hàm trong `backend/` đã là `async` sẵn, dễ wrap thành task) — bắt buộc vì video dài xử lý lâu (tải + Whisper + TTS + ffmpeg).
- Dịch thuật: gọi LLM API (vd. Claude API) thay cho việc AI agent dịch tay như trong skill hiện tại — cần viết module `backend/translate.py` mới.
- Lưu trữ file: giữ nguyên cấu trúc thư mục `downloads/<platform>/<title>__<id>/` đã có; có thể đồng bộ lên S3/MinIO khi cần scale nhiều server.
- DB: thay `index.csv` bằng Postgres/SQLite khi có nhiều user đồng thời (CSV không an toàn khi ghi song song ở quy mô lớn, dù hiện đã có `asyncio.Lock`).
- WebSocket hoặc polling để cập nhật trạng thái tiến trình cho frontend.

### 5.4 Các dịch vụ xử lý AI (Modules) — theo đúng những gì đã tích hợp

| Module | Công cụ đã dùng trong project | Trạng thái |
|--------|----------------|---|
| Tải video đa nền tảng | `yt-dlp` | ✅ Đã có (skill `video-download` + [ytdlp_download.py](backend/ytdlp_download.py)) |
| Tải video Douyin | `yt-dlp` + cookies (extractor Douyin) | ✅ Web app dùng cách này. **Playwright crawler KHÔNG dùng được cho link video đơn lẻ** — Douyin trả 403 ở API `aweme/detail` khi phát hiện browser tự động hoá, kể cả cookies đăng nhập còn hạn. [crawler.py](backend/crawler.py) vẫn dùng tốt cho CLI crawl feed/profile |
| Tách audio / ghép video | `ffmpeg` | ✅ Đã có |
| Speech-to-Text | `faster-whisper` (local, CPU int8) | ✅ Đã có ([transcribe.py](backend/transcribe.py)) |
| Dịch văn bản | OpenRouter API (tương thích OpenAI) | ✅ Đã xây ([translate.py](backend/translate.py)) |
| Text-to-Speech | OmniVoice / Vbee / ElevenLabs / Edge TTS | ✅ Đã có ([backend/voices/](backend/voices/)) + [registry.py](backend/voices/registry.py) tự fallback khi 1 provider lỗi. ⚠️ `openai` có trong `voice/openai.csv` nhưng **chưa có adapter** — không dùng được |
| Đồng bộ thời lượng audio | `ffprobe` + ffmpeg `atempo` | ✅ Đã xây ([mixer.py](backend/mixer.py)), tự khớp dub với độ dài video |
| Trộn âm lượng | `ffmpeg` filter `amix`, `volume` | ✅ Đã tham số hoá trong [mixer.py](backend/mixer.py) |

---

## 6. Chi tiết xử lý âm lượng

```
audio_video_goc  = audio_video_goc  * (volume_video_goc / 100)
audio_giong_doc  = audio_giong_doc  * (volume_giong_doc / 100)
audio_output     = mix(audio_video_goc, audio_giong_doc)
```

Lệnh `ffmpeg` mẫu hiện đang dùng trong skill `voice-over` (cần tham số hoá 2 giá trị volume thay vì hardcode `0.10` / `1.0`):

```bash
ffmpeg -y \
  -i "index.mp4" -i "dub_vi.mp3" \
  -filter_complex "[0:a]volume=${VOLUME_GOC}[orig];[1:a]volume=${VOLUME_DUB}[dub];[orig][dub]amix=inputs=2:normalize=0[mix]" \
  -map 0:v -map "[mix]" -c:v copy -c:a aac -b:a 192k \
  "output_vi.mp4"
```

---

## 7. Định dạng file SRT đầu ra (đã implement)

```
1
00:00:01,000 --> 00:00:04,000
Nội dung phụ đề theo ngôn ngữ đã chọn

2
00:00:04,500 --> 00:00:07,200
...
```

- Timeline SRT khớp với timeline gốc lấy từ Whisper (`segments[].start/end`).
- Bản dịch giữ nguyên timestamp, chỉ đổi `text`.
- Đã có script sinh SRT từ `transcript-vi.json` trong skill `voice-over` (bước 5) — chỉ cần bọc thành API/task khi lên web.

---

## 8. Các vấn đề kỹ thuật cần lưu ý

- **Đồng bộ thời gian (timing)** — ✅ *đã xử lý ở mức tổng thể*: giọng đọc dịch thường dài hơn video gốc đáng kể (đo thực tế: dub 283s cho video 221s, dư 28%). `backend/mixer.py` tự đo độ dài 2 bên bằng `ffprobe` rồi dùng ffmpeg `atempo` co giọng đọc cho vừa video (clamp ≤ 2.0x). Cách này áp dụng cho **mọi provider**, không phụ thuộc tham số `speed` riêng của OmniVoice/Vbee.
  *Còn hạn chế*: mới đồng bộ tổng thời lượng, chưa đồng bộ **từng câu** — giữa video lời thoại có thể lệch so với hình. Muốn khớp chuẩn cần TTS từng segment rồi ghép theo timestamp (xem Phase 3).
- **Server OmniVoice tự host**: đang chạy tại `http://192.168.1.61:8002` trong LAN nội bộ — khi deploy web production (public), server này **không thể truy cập được** trừ khi mở port/VPN hoặc deploy lại OmniVoice lên cloud. Cần quyết định hạ tầng trước khi launch.
- **Giới hạn độ dài video**: cần giới hạn dung lượng/thời lượng để tránh quá tải Whisper (chạy CPU, chậm với video dài) và TTS.
- **Xử lý bất đồng bộ**: hiện tại chạy tuần tự trong 1 phiên CLI — lên web bắt buộc phải có job queue + trạng thái tiến trình, vì mỗi bước (tải, Whisper, TTS, ffmpeg) đều tốn thời gian.
- **Chi phí API**: Vbee/ElevenLabs/OpenAI tính phí theo ký tự/thời lượng — cần theo dõi (rate limit, cost tracking) theo từng user. OmniVoice và Whisper local miễn phí nhưng tốn tài nguyên máy chủ.
- **Bản quyền video**: cần tuân thủ điều khoản dịch vụ của từng nền tảng (YouTube, Douyin, Facebook, TikTok...) — đã có disclaimer trong [README.md](README.md), giữ nguyên tinh thần "chỉ dùng cho mục đích cá nhân" khi lên web, cân nhắc bổ sung điều khoản sử dụng rõ ràng cho người dùng cuối.
- **Chất lượng bản dịch**: bước dịch hiện do AI agent làm tay và khá tốt vì có thể hiểu ngữ cảnh; khi thay bằng gọi LLM API tự động, cần review lại prompt để giữ chất lượng tương đương (văn phong tự nhiên, đúng ngữ cảnh vlog/tin tức/review...).

---

## 9. Danh sách API đề xuất (Backend)

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/jobs` | POST | Tạo job mới: `video_url`, `provider`, `voice_code`, `whisper_model`, `stt_language`, `target_language`, `volume_goc`, `volume_dub`, `speed` |
| `/api/jobs/{id}` | GET | Lấy trạng thái xử lý job (đang tải / đang STT / đang dịch / đang TTS / đang mix / xong / lỗi) |
| `/api/jobs/{id}/result` | GET | Lấy link video kết quả + file `.srt` + `.mp3` |
| `/api/jobs/{id}/transcript` | GET/PATCH | Xem và **sửa tay** bản dịch trước khi TTS lại (đề phòng AI dịch sai) |
| `/api/providers` | GET | Danh sách provider TTS đang khả dụng (dựa theo key cấu hình trên server) |
| `/api/voices?provider=` | GET | Danh sách giọng đọc theo provider, đọc trực tiếp từ `voice/<provider>.csv` |
| `/api/languages` | GET | Danh sách ngôn ngữ hỗ trợ cho STT/dịch |

---

## 10. Roadmap / Task list triển khai

### Phase 0 — Chuẩn bị nền tảng ✅ HOÀN THÀNH
- [x] Viết `backend/translate.py`: dịch `transcript.json` → `transcript-vi.json` qua **OpenRouter** (`OPENROUTER_API_KEY`, model đổi qua `OPENROUTER_MODEL`, mặc định `openai/gpt-4o-mini`), giữ nguyên timestamp, validate số segment khớp.
- [x] `backend/mixer.py`: tham số hoá `volume_goc`/`volume_dub`, sinh SRT, + tự đồng bộ độ dài dub với video.
- [x] `backend/voices/registry.py`: gom 4 adapter TTS, chọn voice theo Nam/Nữ, tự fallback khi provider lỗi.
- [x] `backend/ytdlp_download.py` + `backend/cookies_util.py`: tải video mọi nền tảng qua yt-dlp, tự chuyển cookies JSON → Netscape.
- [x] `backend/jobs_store.py`: SQLite (`jobs.db`) riêng cho job web, không đụng `index.csv` của CLI.
- [ ] *(chưa làm, không chặn)* Tách logic khỏi `rich`/`click` trong `cli.py` — web app hiện gọi thẳng các module engine nên chưa cần.

### Phase 1 — API backend ✅ HOÀN THÀNH
- [x] FastAPI app tại `backend/api/`, import trực tiếp module engine.
- [x] `POST /api/jobs` — tạo job, chạy nền bằng **FastAPI BackgroundTasks** (không dùng Celery/RQ: chạy Windows, quy mô cá nhân, tránh phải cài Redis).
- [x] Pipeline `backend/api/pipeline.py` chạy trọn bước [2]→[11], cập nhật status sau mỗi bước.
- [x] `GET /api/jobs`, `GET /api/jobs/{id}` (kèm link file kết quả khi xong).
- [x] `GET /api/providers`, `GET /api/voices?provider=`, `GET /api/languages`, `GET /api/whisper-models`.
- [x] Phục vụ file kết quả qua `StaticFiles` mount `/files` → `downloads/`.
- [ ] *(chưa làm)* `GET/PATCH /api/jobs/{id}/transcript` — sửa tay bản dịch rồi TTS lại.
- [ ] *(quyết định hạ tầng, chưa cần cho bản local)* OmniVoice server LAN không truy cập được nếu deploy public.

### Phase 2 — Frontend MVP ✅ HOÀN THÀNH
- [x] Form nhập link + chọn giọng Nam/Nữ + 2 slider âm lượng + ngôn ngữ STT/đích (Next.js 16, App Router, Tailwind).
- [x] Trang tiến trình `/jobs/[id]` — poll mỗi 3s, hiển thị trạng thái tiếng Việt, hiện lỗi rõ ràng.
- [x] Trang kết quả: preview video + tải `.mp4` / `.srt` / `.mp3`.
- [x] Danh sách job gần đây ở trang chủ.

### Phase 3 — Tuỳ biến nâng cao
- [ ] UI chọn provider + giọng cụ thể (API `/api/voices` đã sẵn sàng, backend đã hỗ trợ `provider`/`voice_code`; chỉ còn phần UI).
- [ ] UI chọn model Whisper (API đã có, mặc định đang cố định `base`).
- [ ] Trình sửa transcript tay rồi trigger TTS lại mà không tải/STT lại từ đầu.
- [ ] **Đồng bộ theo từng câu**: hiện chỉ co giãn tổng thời lượng (`atempo`) nên lời thoại giữa video có thể lệch hình. Muốn khớp chuẩn cần TTS từng segment rồi ghép theo timestamp `start/end`.

### Phase 4 — Vận hành đa người dùng
- [ ] Tài khoản người dùng + lịch sử job theo user.
- [ ] Giới hạn số job đồng thời / độ dài video theo gói (free/trả phí), do các job dùng CPU nặng (Whisper) và có thể tốn phí (Vbee/ElevenLabs/OpenAI).
- [ ] Cost tracking theo user cho các provider trả phí.
- [ ] Xử lý hàng loạt (batch): cho phép nhập nhiều link cùng lúc hoặc 1 link Douyin profile/feed (tái dùng thẳng `crawl_user_profile`/`crawl_jingxuan` đã có).
- [ ] Dọn dẹp storage tự động (video/audio tạm sau X ngày) vì mỗi job tạo nhiều file (`index.mp4`, `transcript*.json`, `dub_vi.mp3`, `output_vi.mp4`).
