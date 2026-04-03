import os
import argparse
import subprocess
import torch
from rich.console import Console

console = Console()

def mux_video(video_in, tts_in, bgm_in, srt_vi_in, blur_box, video_out):
    """
    Sử dụng FFmpeg -filter_complex để hoàn thiện video (GPU Accelerated).
    """
    if not all(os.path.exists(f) for f in [video_in, tts_in, srt_vi_in]):
        console.print("[bold red]LỖI:[/bold red] Thiếu tệp đầu vào cho quá trình Muxing (video, tts, srt).")
        return

    has_bgm = os.path.exists(bgm_in)

    # Bước 1: Video Filters (Chỉ giữ lại Blur nếu có, bỏ Subtitles)
    video_filters = ""
    if blur_box and blur_box != "none":
        x, y, w, h = blur_box.split(",")
        video_filters = f"boxblur=10:1:enable='between(t,0,99999)':x={x}:y={y}:w={w}:h={h}"

    # Bước 2: Audio Filters (Mixing TTS + BGM)
    if has_bgm:
        audio_filters = "[1:a]volume=1.2[vocal];[2:a]volume=0.2[bgm];[vocal][bgm]amix=inputs=2:duration=longest[outa]"
    else:
        audio_filters = "[1:a]volume=1.2[outa]"

    if video_filters:
        v_stream = f"[0:v]{video_filters}[outv]"
        v_map = "[outv]"
    else:
        v_stream = ""
        v_map = "0:v"

    # Lệnh FFmpeg tổng hợp
    cmd = [
        "ffmpeg", "-y",
        "-hwaccel", "cuda",
        "-i", video_in,
        "-i", tts_in
    ]
    if has_bgm:
        cmd += ["-i", bgm_in]
        
    filter_expr = f"{v_stream};{audio_filters}" if v_stream else audio_filters
    
    cmd += [
        "-filter_complex", filter_expr,
        "-map", v_map,
        "-map", "[outa]",
        "-c:v", "h264_nvenc", # Sử dụng NVIDIA GPU
        "-preset", "p4",        # Cân bằng chất lượng/tốc độ
        "-b:v", "5M",          # Bitrate 5Mbps cho chất lượng HD
        "-c:a", "aac", "-b:a", "192k",
        video_out
    ]

    console.print(f"[bold cyan]>>> Đang khởi tạo Render bằng NVIDIA GPU (NVENC)...[/bold cyan]")
    if blur_box:
        console.print(f"[dim]Vùng Blur: {blur_box}[/dim]")

    try:
        process = subprocess.run(cmd, check=True, capture_output=True, text=True)
        console.print(f"[bold green]RENDER THÀNH CÔNG![/bold green] -> {video_out}")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Lỗi Render:[/bold red] {e.stderr}")

def main():
    parser = argparse.ArgumentParser(description="Module 5: Render Video Hardsub & Mix Audio (2026)")
    parser.add_argument("--video_in", required=True)
    parser.add_argument("--tts_in", required=True)
    parser.add_argument("--bgm_in", required=True)
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--blur_box", help="x,y,w,h (Tọa độ từ tool_get_blur_box)")
    parser.add_argument("--video_out", default="final_result.mp4")
    
    args = parser.parse_args()
    
    try:
        mux_video(args.video_in, args.tts_in, args.bgm_in, args.srt_vi_in, args.blur_box, args.video_out)
    except Exception as e:
        console.print(f"[bold red]Lỗi hệ thống:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()
