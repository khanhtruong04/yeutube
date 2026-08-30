# Video Downloader & Voice Over

Tool **tải video nước ngoài về máy và lồng tiếng Việt (hoặc ngôn ngữ bạn muốn)** để xem offline — không cần hiểu tiếng nước đó.

Hỗ trợ hầu hết các nền tảng phổ biến: YouTube, TikTok, Douyin, Instagram, Facebook, Bilibili, Twitter/X, Vimeo và 1000+ trang khác.

Có 2 cách dùng, chạy song song không xung đột nhau:

1. **CLI + Claude Code skills** — gõ lệnh trong Claude Code, mọi thứ tự động.
2. **Web app** (FastAPI + Next.js) — giao diện web, nhập link + chọn tuỳ chọn rồi bấm "Xử lý".

---

## Cài đặt

Yêu cầu: **Python 3.11+**, **ffmpeg**, **Node.js 18+** (chỉ cần cho web app).

```bash
# 1. ffmpeg (nếu chưa có)
#    Windows:  winget install Gyan.FFmpeg   (hoặc choco install ffmpeg)
#    macOS:    brew install ffmpeg

# 2. Python venv cho backend — BỎ QUA bước tạo mới nếu backend/.venv đã tồn tại sẵn
cd backend
python -m venv .venv

# Windows:
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium

# macOS/Linux:
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

cd ..
```

> **Máy có nhiều bản Python?** Nếu lệnh `python -m venv .venv` báo lỗi kiểu `ModuleNotFoundError: No module named 'encodings'`, nghĩa là bản `python` đầu tiên trong PATH bị cài lỗi/thiếu file — không liên quan tới project. Cách né nhanh nhất: dùng thẳng `backend\.venv\Scripts\python.exe` (Windows) mọi lúc thay vì gõ `python` trơn — mọi lệnh trong README này đều đã dùng đường dẫn đầy đủ đó.

> `yt-dlp` được cài kèm trong `requirements.txt` (dùng qua Python, không cần cài CLI riêng).

Tạo file `.env` ở project root:

```env
# Chọn 1 provider TTS (bỏ qua hết nếu dùng OmniVoice server LAN mặc định)
VBEE_TOKEN=...
VBEE_APP_ID=...
ELEVENLABS_API_KEY=...
OPENAI_API_KEY=...

# Bắt buộc để dùng web app (dịch transcript tự động qua OpenRouter)
OPENROUTER_API_KEY=...
```

Nếu dùng web app, cài thêm frontend:

```bash
cd frontend
npm install
cd ..
```

---

## Chạy dự án

### Cách 1 — CLI + Claude Code skills

Mở project trong Claude Code rồi gõ lệnh:

```
/video-download https://www.youtube.com/watch?v=...
/voice-over downloads/youtube/<video-folder>
```

Tool tự động transcript → dịch → TTS → ghép video, không hỏi lại. Chi tiết từng skill xem mục [Skills](#skills) bên dưới.

### Cách 2 — Web app

Mở 2 terminal:

```bash
# Terminal 1 — backend API (port 8000), chạy từ project root
backend\.venv\Scripts\python -m uvicorn backend.api.main:app --port 8000
# macOS/Linux: backend/.venv/bin/python -m uvicorn backend.api.main:app --port 8000

# Terminal 2 — frontend (port 3000)
cd frontend
npm run dev
```

Mở `http://localhost:3000` — nhập link video, chọn giọng đọc Nam/Nữ, chỉnh âm lượng gốc/dub, chọn ngôn ngữ STT + ngôn ngữ đích, bấm **Xử lý**. Trang tự cập nhật tiến trình, xong thì xem/tải video + file `.srt` ngay trên trình duyệt.

Ghi chú:
- Job chạy nền trong tiến trình FastAPI (không cần Redis/Celery) — đủ dùng cho 1 người, vài job cùng lúc.
- Kết quả lưu tại `downloads/web/<job_id>/`; danh sách job lưu trong `jobs.db` (SQLite, tách biệt hoàn toàn với `index.csv` của CLI, không ảnh hưởng lẫn nhau).
- Bước dịch bắt buộc có `OPENROUTER_API_KEY` trong `.env` — thiếu key thì job sẽ báo lỗi rõ ràng ở bước "translating".
- Giọng đọc Nam/Nữ chọn tự động theo provider TTS khả dụng (ưu tiên Vbee → ElevenLabs → Edge TTS → OmniVoice). Nếu provider bị lỗi (hết quota, sai key, server tắt) hệ thống **tự chuyển sang provider kế tiếp**, không fail cả job.

### Tải video Douyin trên web app — cần cookies

Web app tải video bằng **yt-dlp** cho mọi nền tảng. Riêng Douyin bắt buộc có cookies (`Fresh cookies are needed`), làm 1 lần:

1. Đăng nhập douyin.com trên trình duyệt.
2. Dùng extension **Cookie-Editor** → Export → JSON.
3. Dán vào file `cookies_playwright.json` ở project root.

Hệ thống tự chuyển sang định dạng yt-dlp cần (`cookies_netscape.txt`). Cookies hết hạn thì lặp lại 3 bước trên.

> Vì sao không dùng Playwright crawler cho link video đơn lẻ? Douyin trả **403** cho API `aweme/detail` khi phát hiện browser tự động hoá — kể cả khi cookies đăng nhập còn hạn. `crawler.py` vẫn được giữ cho CLI crawl hàng loạt theo feed/profile (endpoint khác, không bị chặn).

---

## Skills

| Skill | Mô tả |
|-------|-------|
| `/video-download <url>` | Tải video từ YouTube, TikTok, Instagram, Facebook, Bilibili, Douyin, v.v. |
| `/voice-over <folder>` | Tự động dịch + lồng tiếng Việt → xuất `output_vi.mp4` |
| `/douyin-crawler <url>` | Tải hàng loạt video từ profile hoặc feed page Douyin |

---

## /video-download

Tải video chất lượng cao bằng **yt-dlp**, lưu về máy theo cấu trúc thư mục gọn gàng.

```bash
# Một video
/video-download https://www.youtube.com/watch?v=...

# Nhiều link cùng lúc
/video-download https://... https://...

# Tải cả playlist
/video-download https://www.youtube.com/playlist?list=... tải cả playlist
```

Output lưu tại `downloads/<platform>/<title>__<id>/index.mp4` — dùng được luôn với `/voice-over`.

---

## /voice-over

Tự động hoá toàn bộ pipeline từ video gốc đến video tiếng Việt:

```
index.mp4 → transcript → dịch Việt → TTS → ghép audio → output_vi.mp4
```

```bash
/voice-over downloads/youtube/<video-folder>

# Chỉ định giọng đọc
/voice-over downloads/youtube/<video-folder> --voice sg_female_thaotrinh_full_44k-phg.mp3

# Chỉ định provider TTS
/voice-over downloads/youtube/<video-folder> --provider vbee
```

Tool tự đọc `.env` để phát hiện provider đang có, tự chọn giọng phù hợp với nội dung — không hỏi user.

### Providers TTS hỗ trợ

| Key trong `.env` | Provider |
|---|---|
| `VBEE_TOKEN` + `VBEE_APP_ID` | Vbee |
| `ELEVENLABS_API_KEY` | ElevenLabs |
| `OPENAI_API_KEY` | OpenAI |
| (không có key) | OmniVoice (server LAN) |

---

## /douyin-crawler

Tải hàng loạt video từ Douyin (feed page, profile, hoặc link detail).

```bash
# Feed page Tinh Tuyển
/douyin-crawler https://www.douyin.com/jingxuan

# Profile người dùng
/douyin-crawler https://www.douyin.com/user/MS4wLjABAAAA...

# Chỉ định số lượng
/douyin-crawler https://www.douyin.com/jingxuan --max 30
```

> Nếu tải được 0 video, thêm `--no-headless` để browser hiện lên — có thể cần đăng nhập hoặc vượt captcha.

---

## Cấu trúc thư mục sau khi tải

```
downloads/<platform>/<video-title>__<id>/
  ├── index.mp4           ← video gốc
  ├── index.info.json     ← metadata
  ├── transcript.json     ← transcript gốc (Whisper)
  ├── transcript-vi.json  ← bản dịch tiếng Việt
  ├── subtitle_vi.srt     ← subtitle tiếng Việt
  ├── dub_vi.mp3          ← audio TTS
  └── output_vi.mp4       ← video hoàn chỉnh
```

Job tạo từ **web app** dùng cùng bộ file trên nhưng lưu tại `downloads/web/<job_id>/` (Douyin có thêm 1 cấp folder con `<author>__<title>__<id>/` bên trong, do dùng chung crawler với CLI).

---

## Miễn trừ trách nhiệm

Tool này được xây dựng **chỉ cho mục đích cá nhân** — giúp người dùng tải và hiểu nội dung video nước ngoài để xem offline.

Người dùng chịu trách nhiệm đảm bảo việc sử dụng tool tuân thủ điều khoản dịch vụ của nền tảng tương ứng và pháp luật hiện hành. Tác giả không chịu trách nhiệm với bất kỳ hành vi sử dụng nào ngoài mục đích trên.

---

## License

[MIT](LICENSE)
