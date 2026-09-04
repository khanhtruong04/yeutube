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

**Có card NVIDIA?** Bước nhận diện giọng nói (Whisper) tự dùng GPU nếu có, nhanh hơn CPU đáng kể — đo trên RTX 3050: model `base` nhanh **gấp 4**, model `small` nhanh **gấp 8.8**. Cần cài thêm 2 gói CUDA:

```bash
# Windows
backend\.venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Không có GPU, hoặc GPU lỗi giữa chừng, hệ thống **tự lùi về CPU** chứ không hỏng job. Muốn ép chạy CPU thì thêm `WHISPER_DEVICE=cpu` vào `.env`.

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
backend\.venv\Scripts\python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
# macOS/Linux: backend/.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend (port 3000)
cd frontend
npm run dev
```

> **Đừng đóng 2 cửa sổ terminal này** — đóng là server tắt, web sẽ báo lỗi kết nối. Khi job lỗi, traceback đầy đủ hiện ở cửa sổ backend.

Mở `http://localhost:3000` — nhập link video, chọn giọng đọc Nam/Nữ, chọn độ phân giải (**1080p HD** hoặc **720p**), chỉnh âm lượng gốc/dub, chọn ngôn ngữ STT + ngôn ngữ đích, bấm **Xử lý**.

> Độ phân giải là **mức trần**, tính theo **cạnh ngắn** khung hình nên đúng cho cả video ngang (1920x1080) lẫn video dọc kiểu Douyin/TikTok (1080x1920). Nguồn không có sẵn mức đã chọn thì lấy bản cao nhất bên dưới.
>
> Rất nhiều clip Douyin **chỉ có tối đa 720x1280** trên server — không phụ thuộc cookies hay tài khoản. Muốn file xuất ra đúng khung 1080p, tick thêm ô **"Phóng to cho đủ 1080p"**: ffmpeg sẽ kéo giãn khung hình lúc render (720x1280 → 1080x1920). Lưu ý đây chỉ là giãn pixel — **không nét thêm chút nào**, file nặng hơn ~50% và render lâu hơn. Chỉ nên bật khi nơi đăng bắt buộc độ phân giải tối thiểu. Job giờ dừng lại **2 lần chờ bạn thao tác** trước khi ra kết quả:

```
tải xong ─┬─> [bạn vẽ box che] ──> [bạn đặt vị trí phụ đề] ─┐
          └─> STT ─> dịch ─> TTS ──────────────────────────┴─> ghép video → xong
```

Phần máy làm (STT, dịch, TTS) **chạy song song** với lúc bạn thao tác chuột, vì các bước đó không phụ thuộc vào box che hay vị trí phụ đề. Thời gian bạn ngồi kéo box là "miễn phí". Nhánh nào xong sau thì nhánh đó khởi động bước ghép video cuối cùng — trang job hiện riêng tiến độ nền để bạn thấy máy vẫn đang chạy.

1. **Chờ chọn vùng che** — video gốc hiện ra, kéo/resize box che (mờ hoặc màu đặc) lên vùng có text/logo gốc cần ẩn. Mỗi box áp cho toàn video hoặc 1 khoảng thời gian riêng. Không thêm box nào cũng được, bấm "Xác nhận" để bỏ qua.
2. **Chờ đặt vị trí phụ đề** — đã có sẵn 1 vùng mặc định ở đáy khung hình cho cả video; chỉ cần thêm vùng mới nếu muốn phụ đề đổi chỗ ở 1 đoạn cụ thể (vd. tránh đè lên vùng che).

Sau đó job tự chạy tiếp TTS + burn mask/phụ đề vào video (không còn `-c:v copy` — re-encode nên chậm hơn trước), xong thì xem/tải `output_vi.mp4` (đã che + phụ đề cứng) + `subtitle_vi.srt` rời ngay trên trình duyệt.

Ghi chú:
- Job chạy nền trong tiến trình FastAPI (không cần Redis/Celery) — đủ dùng cho 1 người, vài job cùng lúc.
- Kết quả lưu tại `downloads/web/<job_id>/`; danh sách job lưu trong `jobs.db` (SQLite, tách biệt hoàn toàn với `index.csv` của CLI, không ảnh hưởng lẫn nhau).
- Bước dịch bắt buộc có `OPENROUTER_API_KEY` trong `.env` — thiếu key thì job sẽ báo lỗi rõ ràng ở bước "translating".
- Giọng đọc Nam/Nữ chọn tự động theo provider TTS khả dụng (ưu tiên Vbee → ElevenLabs → Edge TTS → OmniVoice). Nếu provider bị lỗi (hết quota, sai key, server tắt) hệ thống **tự chuyển sang provider kế tiếp**, không fail cả job.

### Cho máy khác cùng mạng LAN dùng chung

Chạy đúng 2 lệnh ở trên (backend đã có `--host 0.0.0.0`, frontend Next tự mở ra mạng) rồi đưa người dùng địa chỉ **IP LAN của máy chủ** thay cho `localhost`:

```
http://192.168.1.6:3000        ← thay bằng IP thật của máy bạn
```

Xem IP máy mình:

```
:: Windows — Command Prompt (cmd)
ipconfig
```

```powershell
# Windows — PowerShell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '10.*' }
```

```bash
# macOS/Linux
ifconfig | grep "inet "
```

Không cần sửa cấu hình gì thêm: frontend tự suy ra địa chỉ backend theo hostname đang truy cập (mở bằng `192.168.1.6` thì gọi API ở `192.168.1.6:8000`).

Nếu máy khác vào không được dù đã đúng IP, gần như chắc chắn do **Windows Firewall chặn cổng vào**. Chạy 1 lần trên máy chủ, **bắt buộc quyền Administrator** (Start → gõ `cmd` → chuột phải → *Run as administrator*):

```
:: Command Prompt (cmd)
netsh advfirewall firewall add rule name="Video Dubbing web" dir=in action=allow protocol=TCP localport=3000,8000 profile=private
```

```powershell
# PowerShell
New-NetFirewallRule -DisplayName "Video Dubbing web" -Direction Inbound -Protocol TCP -LocalPort 3000,8000 -Action Allow -Profile Private
```

> Hai lệnh trên là **của 2 shell khác nhau, không dùng lẫn** — gõ lệnh PowerShell trong cmd sẽ báo `'New-NetFirewallRule' is not recognized`.
>
> `profile=private` giới hạn ở mạng bạn đã đặt là "Private" (mạng nhà/công ty), không mở khi nối vào Wi-Fi công cộng.

**Lưu ý an toàn:** web app **không có đăng nhập**. Ai vào được địa chỉ trên đều tạo job được và xem/tải được mọi video trong `downloads/` qua đường dẫn `/files/...`. Chỉ chạy `--host 0.0.0.0` trong mạng bạn tin tưởng; đừng mở cổng (port forwarding) ra Internet.

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
backend\.venv\Scripts\python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

## License

[MIT](LICENSE)
