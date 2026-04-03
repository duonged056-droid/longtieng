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
        hw_accel = []

    # --- MIST BLUR (GAUSSIAN FADE) LOGIC ---
    # Để đạt hiệu ứng "sương mù/mờ dần" (Mist) ở cạnh trên:
    # 1. Ta tạo một vùng mờ đồng màu bằng delogo + gblur
    # 2. Ta tạo một MASK (lớp mặt nạ) có độ dốc (gradient) từ đen (trong suốt) sang trắng (đậm)
    # 3. Ta dùng maskedmerge để trộn vùng gốc và vùng mờ theo MASK này.

    # Lấy kích thước video thực tế để tránh lỗi "Outside of frame"
    try:
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", args.video_in
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        probe_data = json.loads(probe_res.stdout)
        vw = probe_data['streams'][0]['width']
        vh = probe_data['streams'][0]['height']
        
        # Tự động cắt (clip) tọa độ nếu vượt quá khung hình
        real_x = max(0, min(args.x, vw - 1))
        real_y = max(0, min(args.y, vh - 1))
        real_w = max(1, min(args.w, vw - real_x))
        real_h = max(1, min(args.h, vh - real_y))
        
        console.print(f"📏 Cân chỉnh vùng mờ: {real_w}x{real_h} tại {real_x},{real_y} (Video: {vw}x{vh})")
    except:
        real_x, real_y, real_w, real_h = args.x, args.y, args.w, args.h

    # Đường dẫn file script tạm để tránh lỗi dấu ngoặc vuông [...]
    script_path = os.path.join(os.path.dirname(args.video_out), "temp_filter_blur.txt")
    
    # Cấu trúc Filter Complex:
    # 1. delogo trên TOÀN BỘ khung hình để nó có dữ liệu xung quanh (tránh lỗi outside or interpolation error)
    # 2. crop + gblur để làm dải mờ mịn
    # 3. overlay ngược lại
    filter_script = (
        f"[0:v] split [orig_full][src_full];\n"
        f"[src_full] delogo=x={real_x}:y={real_y}:w={real_w}:h={real_h} [delogo_full];\n"
        f"[delogo_full] crop={real_w}:{real_h}:{real_x}:{real_y}, gblur=sigma=30:steps=3 [blurred_part];\n"
        f"nullsrc=size={real_w}x{real_h}, geq=lum='255*pow(Y/H, 3.5)' [mask_mist];\n"
        f"[orig_full] crop={real_w}:{real_h}:{real_x}:{real_y} [original_part];\n"
        f"[original_part][blurred_part][mask_mist] maskedmerge [merged_part];\n"
        f"[orig_full][merged_part] overlay={real_x}:{real_y} [final_video_output]"
    )

    try:
        os.makedirs(os.path.dirname(args.video_out), exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(filter_script)

        cmd = [
            ffmpeg_cmd, "-y",
        ] + hw_accel + [
            "-i", args.video_in,
            "-filter_complex_script", script_path,
            "-map", "[final_video_output]",
            "-map", "0:a?",
            "-c:v", encoder,
            "-preset", preset,
            "-c:a", "copy",
            "-loglevel", "error",
            args.video_out
        ]

        subprocess.run(cmd, check=True)
        
        # Cleanup
        if os.path.exists(script_path): os.remove(script_path)
            
        console.print(f"[bold green]✨ XỬ LÝ MIST BLUR THÀNH CÔNG![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Lỗi khi xử lý video qua FFmpeg:[/bold red] {str(e)}")
        if os.path.exists(script_path): os.remove(script_path)

if __name__ == "__main__":
    main()
