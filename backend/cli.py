import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import prosody
from .crawler import crawl_jingxuan, crawl_user_profile, crawl_single_url
from .downloader import download_videos
from .transcribe import transcribe_video
from .voices import registry

console = Console()


def _print_video_table(videos: list[dict]) -> None:
    table = Table(title=f"Tìm thấy {len(videos)} video", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Tác giả", style="cyan", max_width=20)
    table.add_column("Tiêu đề", max_width=50)
    table.add_column("ID", style="dim", max_width=20)
    for i, v in enumerate(videos, 1):
        table.add_row(str(i), v["author"], v["title"], v["aweme_id"])
    console.print(table)


@click.group()
def cli():
    """Douyin Video Downloader — tải video không watermark từ Douyin."""
    pass


@cli.command()
@click.option("--url", default="https://www.douyin.com/jingxuan", show_default=True)
@click.option("--max", "max_videos", default=50, show_default=True)
@click.option("--scroll", default=10, show_default=True)
@click.option("--out", "output_dir", default="downloads/jingxuan", show_default=True)
@click.option("--concurrency", default=4, show_default=True)
@click.option("--cookies", "cookies_file", default=None)
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--dry-run", is_flag=True, help="Chỉ liệt kê, không tải")
def jingxuan(url, max_videos, scroll, output_dir, concurrency, cookies_file, headless, dry_run):
    """Tải video từ trang Tinh Tuyển hoặc bất kỳ feed URL Douyin nào."""
    console.rule("[bold cyan]Douyin Jingxuan Downloader[/bold cyan]")

    async def run():
        videos = []
        console.print(f"[yellow]Đang crawl {url} (max={max_videos}, scroll={scroll})...[/yellow]")
        async for video in crawl_jingxuan(
            max_videos=max_videos, scroll_count=scroll,
            headless=headless, cookies_file=cookies_file, start_url=url,
        ):
            videos.append(video)
            if len(videos) >= max_videos:
                break

        if not videos:
            console.print("[red]Không tìm thấy video. Thử --no-headless.[/red]")
            return

        _print_video_table(videos)

        if dry_run:
            console.print("[yellow]Dry-run mode: không tải xuống.[/yellow]")
            return

        console.print(f"\n[green]Tải {len(videos)} video vào '{output_dir}'...[/green]")
        success, fail = await download_videos(videos, output_dir=output_dir, concurrency=concurrency)
        console.rule()
        console.print(f"[green]✓ Thành công: {success}[/green]  [red]✗ Thất bại: {fail}[/red]")

    asyncio.run(run())


@cli.command()
@click.argument("url")
@click.option("--max", "max_videos", default=100, show_default=True)
@click.option("--out", "output_dir", default="downloads/user", show_default=True)
@click.option("--concurrency", default=4, show_default=True)
@click.option("--cookies", "cookies_file", default=None)
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--dry-run", is_flag=True)
def user(url, max_videos, output_dir, concurrency, cookies_file, headless, dry_run):
    """Tải toàn bộ video từ profile người dùng."""
    console.rule("[bold cyan]Douyin User Downloader[/bold cyan]")

    async def run():
        videos = []
        console.print(f"[yellow]Đang crawl profile: {url}[/yellow]")
        async for video in crawl_user_profile(
            user_url=url, max_videos=max_videos,
            headless=headless, cookies_file=cookies_file,
        ):
            videos.append(video)
            if len(videos) >= max_videos:
                break

        if not videos:
            console.print("[red]Không tìm thấy video. Thử --no-headless hoặc --cookies.[/red]")
            return

        _print_video_table(videos)
        if dry_run:
            console.print("[yellow]Dry-run mode.[/yellow]")
            return

        console.print(f"\n[green]Tải {len(videos)} video vào '{output_dir}'...[/green]")
        success, fail = await download_videos(videos, output_dir=output_dir, concurrency=concurrency)
        console.rule()
        console.print(f"[green]✓ Thành công: {success}[/green]  [red]✗ Thất bại: {fail}[/red]")

    asyncio.run(run())


@cli.command()
@click.argument("url")
@click.option("--out", "output_dir", default="downloads/jingxuan", show_default=True)
@click.option("--cookies", "cookies_file", default=None)
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--dry-run", is_flag=True)
def dl(url, output_dir, cookies_file, headless, dry_run):
    """Tải 1 video từ link detail Douyin."""
    console.rule("[bold cyan]Douyin Single Download[/bold cyan]")

    async def run():
        console.print(f"[yellow]Crawl video từ: {url}[/yellow]")
        video = await crawl_single_url(url=url, headless=headless, cookies_file=cookies_file)

        if not video:
            console.print("[red]Không lấy được thông tin video. Thử --no-headless.[/red]")
            return

        console.print(f"[green]Tìm thấy:[/green] [{video['author']}] {video['title'][:60]}")

        if dry_run:
            console.print(f"[dim]URL: {video['download_url'][:80]}...[/dim]")
            return

        success, _ = await download_videos([video], output_dir=output_dir)
        if success:
            console.print(f"[green]✓ Đã tải xong vào '{output_dir}'[/green]")
        else:
            console.print("[red]✗ Tải thất bại.[/red]")

    asyncio.run(run())


@cli.command()
@click.argument("video_path")
@click.option(
    "--model", default="base", show_default=True,
    type=click.Choice(["tiny", "base", "small", "medium", "large", "large-v3-turbo"], case_sensitive=False),
)
@click.option("--language", default=None, help="zh, en, vi... để trống để auto-detect")
@click.option("--id", "aweme_id", default=None)
def transcribe(video_path, model, language, aweme_id):
    """Transcribe video bằng Whisper và cập nhật index.csv."""
    console.rule("[bold cyan]Douyin Transcribe[/bold cyan]")

    async def run():
        try:
            await transcribe_video(video_path=video_path, model=model, language=language, aweme_id=aweme_id)
        except (FileNotFoundError, RuntimeError) as e:
            console.print(f"[red]{e}[/red]")
        except ImportError:
            console.print("[red]Chưa cài faster-whisper.[/red]\nChạy: [yellow]pip install faster-whisper[/yellow]")

    asyncio.run(run())


@cli.command()
@click.argument("source")
@click.option("--out", "-o", "output", default=None, help="File mp3 xuất ra (mặc định: cạnh file kịch bản)")
@click.option("--provider", default=None,
              type=click.Choice(["vbee", "elevenlabs", "omnivoice", "edgetts"], case_sensitive=False))
@click.option("--voice", "voice_code", default=None)
@click.option("--gender", default=None, help="male | female — dùng khi không chỉ định --voice")
@click.option("--speed", default=None, type=float, help="Tốc độ nền của giọng (vbee/omnivoice)")
@click.option("--pause-scale", default=1.0, show_default=True, help="Nhân toàn bộ khoảng nghỉ")
@click.option("--max-pause", default=None, type=float, help="Trần khoảng nghỉ, giây")
@click.option("--flat-connectives", is_flag=True, help="Không tách liên từ ra đọc lướt")
@click.option("--concurrency", default=2, show_default=True)
@click.option("--dry-run", is_flag=True, help="Chỉ in bảng ngữ điệu, không gọi TTS")
def speak(source, output, provider, voice_code, gender, speed, pause_scale,
          max_pause, flat_connectives, concurrency, dry_run):
    """Đọc kịch bản thành mp3 CÓ NGỮ ĐIỆU (SOURCE là file .txt/.md/.json, hoặc '-' cho stdin).

    Lướt qua liên từ/đưa đẩy, ngắt ở dấu phẩy - dấu chấm, nhấn mạnh chữ in đậm
    (**...**), im hẳn ở chỗ ghi 【DỪNG 2 GIÂY】 hay (dừng 3 giây...).
    """
    console.rule("[bold cyan]Đọc kịch bản theo ngữ điệu[/bold cyan]")

    if source == "-":
        text = sys.stdin.read()
        out_path = Path(output or "speak.mp3")
    else:
        src = Path(source)
        if not src.is_file():
            console.print(f"[red]Không thấy file kịch bản: {src}[/red]")
            raise SystemExit(1)
        raw = src.read_text(encoding="utf-8")
        if src.suffix.lower() == ".json":
            # transcript-vi.json: nối các segment lại, mỗi câu một dòng — xuống
            # dòng chính là nhịp ngắt giữa câu, chứ `text` top-level đã bị nối
            # dính liền nên mất hết chỗ ngắt.
            data = json.loads(raw)
            segments = data.get("segments") or []
            raw = "\n".join(s["text"].strip() for s in segments if s.get("text", "").strip()) \
                or data.get("text", "")
        text = raw
        out_path = Path(output) if output else src.with_suffix(".mp3")

    chunks, lead = prosody.parse(
        text, fast_connectives=not flat_connectives,
        pause_scale=pause_scale, max_pause=max_pause,
    )
    if not chunks:
        console.print("[red]Kịch bản không có nội dung nào đọc được.[/red]")
        raise SystemExit(1)

    if dry_run:
        table = Table(title=f"{len(chunks)} mẩu — nghỉ tổng {sum(c.pause_after for c in chunks) + lead:.1f}s")
        table.add_column("#", style="dim", width=4)
        table.add_column("Tốc độ", width=7)
        table.add_column("Nhấn", width=6)
        table.add_column("Nghỉ sau", width=9)
        table.add_column("Nội dung", max_width=70)
        for i, c in enumerate(chunks, 1):
            table.add_row(str(i), f"{c.speed:.2f}x",
                          f"+{c.gain_db:.0f}dB" if c.gain_db else "",
                          f"{c.pause_after:.2f}s", c.text)
        console.print(table)
        return

    locked: dict[str, str] = {}

    async def tts(chunk_text: str, out_file: str) -> None:
        if locked:
            await registry.run_tts(locked["provider"], chunk_text, voice_code=locked["voice_code"],
                                   speed=speed, output=out_file, log=None)
            return
        result = await registry.synthesize(chunk_text, gender=gender, provider=provider,
                                           voice_code=voice_code, speed=speed, output=out_file, log=None)
        locked.update(provider=result["provider"], voice_code=result["voice_code"])

    async def run():
        result = await prosody.render(
            text, tts=tts, work_dir=out_path.parent / f".prosody_{out_path.stem}",
            output=str(out_path), pause_scale=pause_scale, max_pause=max_pause,
            fast_connectives=not flat_connectives, concurrency=concurrency, log=print,
        )
        console.print(
            f"[green]✓[/green] {out_path} — {result['bytes']:,} bytes, "
            f"{result['chunks']} mẩu, giọng {locked.get('provider')}/{locked.get('voice_code')}"
        )

    try:
        asyncio.run(run())
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
