import os
import asyncio
import argparse
import requests
import base64
import subprocess
import pysrt
from pydub import AudioSegment
from rich.console import Console
from tqdm import tqdm
import edge_tts

console = Console()

def align_audio(input_wav: str, target_duration: float, output_wav: str):
    """
    Sử dụng FFmpeg filter 'atempo' để thay đổi tốc độ audio khớp với thời gian SRT.
    """
    # Lấy thời gian thực tế của file vừa tải về
    audio = AudioSegment.from_file(input_wav)
    actual_duration = len(audio) / 1000.0 # sang giây
    
    if actual_duration == 0:
        return input_wav

    # Tỷ lệ scale: speed = actual / target
    # VD: Thực tế 5s, mục tiêu 4s -> speed = 1.25x
    speed = actual_duration / target_duration
    
    # Giới hạn speed để tránh méo tiếng quá mức (thường 0.5x - 2.0x)
    speed = max(0.5, min(2.0, speed))
    
    # Nếu sự sai khác nhỏ (< 5% hoặc < 100ms), không cần scale
    if abs(speed - 1.0) < 0.05:
        return input_wav
    
    console.print(f"[dim]Căn chỉnh tốc độ {speed:.2f}x cho đoạn: {input_wav}[/dim]")
    
    # Xử lý chuỗi filter atempo (atempo chỉ hỗ trợ 0.5 - 2.0, nếu > 2.0 phải lặp lại)
    # Ở đây chúng ta đã giới hạn 0.5 - 2.0 nên dùng 1 filter là đủ
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_wav,
        "-filter:a", f"atempo={speed}",
        output_wav
    ]
    subprocess.run(cmd, check=True)
    return output_wav

def gen_tiktok_tts(text, voice, output_path):
    """Gọi TikTok TTS Unofficial API."""
    url = "https://tiktok-tts.weilnet.workers.dev/api/generation"
    try:
        response = requests.post(url, json={"text": text, "voice": voice}, timeout=30)
        data = response.json()
        if data.get("success"):
            audio_base64 = data["data"]
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_base64))
            return True
        else:
            console.print(f"[red]Lỗi TikTok API:[/red] {data.get('error')}")
    except Exception as e:
        console.print(f"[red]Lỗi gọi TikTok TTS:[/red] {e}")
    return False

async def gen_edge_tts(text, voice, output_path):
    """Gọi Edge TTS Library."""
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception as e:
        console.print(f"[red]Lỗi Edge TTS:[/red] {e}")
    return False

async def main_async():
    parser = argparse.ArgumentParser(description="Module 4: Lồng tiếng và Khớp nhịp (2026 Edition)")
    parser.add_argument("--srt_vi_in", required=True, help="File phụ đề tiếng Việt đã dịch")
    parser.add_argument("--tts_out", required=True, help="File audio lồng tiếng hoàn chỉnh (WAV)")
    parser.add_argument("--engine", choices=["edge", "tiktok"], default="tiktok", help="Engine lồng tiếng")
    parser.add_argument("--voice", help="Voice ID (Edge: vi-VN-HoaiMyNeural, TikTok: vi_vn_002)")
    
    args = parser.parse_args()
    
    # Thiết lập Voice mặc định
    if not args.voice:
        args.voice = "vi_vn_002" if args.engine == "tiktok" else "vi-VN-HoaiMyNeural"
        
    if not os.path.exists(args.srt_vi_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file {args.srt_vi_in}")
        return

    os.makedirs("temp_tts", exist_ok=True)
    subs = pysrt.open(args.srt_vi_in)
    
    # Tính tổng chiều dài video dựa trên sub cuối cùng
    total_ms = (subs[-1].end.ordinal) if subs else 0
    full_audio = AudioSegment.silent(duration=total_ms + 1000) # Thêm 1s đệm
    
    console.print(f"[bold blue]Bắt đầu lồng tiếng: {len(subs)} câu thoại ({args.engine} engine)...[/bold blue]")
    
    for i, sub in enumerate(tqdm(subs, desc="Lồng tiếng")):
        text = sub.text.replace('\n', ' ')
        start_ms = sub.start.ordinal
        end_ms = sub.end.ordinal
        duration_sec = (end_ms - start_ms) / 1000.0
        
        tmp_raw = f"temp_tts/raw_{i}.wav"
        tmp_aligned = f"temp_tts/aligned_{i}.wav"
        
        success = False
        if args.engine == "tiktok":
            # Retry tiktok 3 lần
            for _ in range(3):
                if gen_tiktok_tts(text, args.voice, tmp_raw):
                    success = True
                    break
        else:
            if await gen_edge_tts(text, args.voice, tmp_raw):
                success = True
                
        if success:
            # Khớp nhịp
            final_segment_path = align_audio(tmp_raw, duration_sec, tmp_aligned)
            segment_audio = AudioSegment.from_file(final_segment_path)
            
            # Chèn vào đúng vị trí trên track chính
            full_audio = full_audio.overlay(segment_audio, position=start_ms)
        else:
            console.print(f"[yellow]Bỏ qua dòng {i+1} do lỗi TTS.[/yellow]")

    # Xuất file kết quả
    full_audio.export(args.tts_out, format="wav")
    console.print(f"[bold green]LỒNG TIẾNG HOÀN TẤT![/bold green] -> {args.tts_out}")
    
    # Dọn dẹp
    import shutil
    shutil.rmtree("temp_tts")

if __name__ == "__main__":
    asyncio.run(main_async())
