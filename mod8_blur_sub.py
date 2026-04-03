import os
import argparse
import subprocess
import sys
from rich.console import Console

console = Console()

def check_gpu(ffmpeg_cmd):
    """Kiểm tra GPU NVENC."""
    try:
        test = subprocess.run([ffmpeg_cmd, '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in test.stdout
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="Module 8: Làm mờ vùng (Regional Blur) - GPU Optimized")
    parser.add_argument("--video_in", required=True, help="Video đầu vào")
    parser.add_argument("--video_out", required=True, help="Video đầu ra")
    parser.add_argument("--x", type=int, required=True, help="Tọa độ X")
    parser.add_argument("--y", type=int, required=True, help="Tọa độ Y")
    parser.add_argument("--w", type=int, required=True, help="Chiều rộng vùng mờ")
    parser.add_argument("--h", type=int, required=True, help="Chiều cao vùng mờ")
    parser.add_argument("--blur", type=int, default=51, help="Độ mức độ mờ (mặc định 51)")
    parser.add_argument("--ffmpeg_path", default="ffmpeg")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file {args.video_in}")
        return

    ffmpeg_cmd = args.ffmpeg_path
    
    console.print(f"[bold blue]⚡ ĐANG XỬ LÝ LÀM MỜ VÙNG (GPU ACCELERATED):[/bold blue] {args.video_in}")
    console.print(f"Vùng: x={args.x}, y={args.y}, w={args.w}, h={args.h}, mức mờ={args.blur}")
    
    use_gpu = check_gpu(ffmpeg_cmd)
    if use_gpu:
        console.print("[bold green]✅ GPU NVENC ĐÃ SẴN SÀNG![/bold green]")
        encoder = "h264_nvenc"
        preset = "p4" 
        hw_accel = ["-hwaccel", "cuda"]
    else:
        console.print("[bold yellow]⚠️ Không tìm thấy GPU, sử dụng CPU.[/bold yellow]")
        encoder = "libx264"
        preset = "fast"
        # Sử dụng bộ lọc "delogo" để đạt yêu cầu "cùng màu với nền video đằng sau".
    # delogo nội suy từ các pixel xung quanh vùng chọn để lấp đầy, giúp xóa vết chữ cực kỳ tự nhiên.
    # Ta kết hợp delogo + một chút gblur nhẹ để làm mịn vùng nội suy.
    
    # 1. Trích xuất vùng (crop)
    # 2. Xóa bằng delogo (nội suy màu từ môi trường)
    # 3. Làm mịn bằng gblur (sigma thấp để không bị loang màu)
    f_crop = f"crop={args.w}:{args.h}:{args.x}:{args.y}"
    f_delogo = f"delogo=x=0:y=0:w={args.w}:h={args.h}:band=1" 
    f_blur = f"gblur=sigma=10:steps=1"
    
    filter_chain = f"[0:v]{f_crop},{f_delogo},{f_blur}[b];[0:v][b]overlay={args.x}:{args.y}[vout]"

    cmd = [
        ffmpeg_cmd, "-y",
    ] + hw_accel + [
        "-i", args.video_in,
        "-filter_complex", filter_chain,
        "-map", "[vout]",
        "-map", "0:a?",
        "-c:v", encoder,
        "-preset", preset,
        "-c:a", "copy",
        "-loglevel", "error",
        args.video_out
    ]

    try:
        os.makedirs(os.path.dirname(args.video_out), exist_ok=True)
        subprocess.run(cmd, check=True)
        console.print(f"[bold green]✨ XỬ LÝ GPU HOÀN TẤT![/bold green] File: {args.video_out}")
    except Exception as e:
        console.print(f"[bold red]Lỗi khi xử lý video qua FFmpeg:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()
