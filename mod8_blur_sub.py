import os
import argparse
import subprocess
import sys
import json
from rich.console import Console

console = Console()

def check_gpu(ffmpeg_cmd):
    """Kiểm tra GPU NVENC."""
    try:
        test = subprocess.run([ffmpeg_cmd, '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in test.stdout
    except Exception:
        return False

def check_hwaccel_cuda(ffmpeg_cmd):
    """Kiểm tra HW Accel CUDA decoder."""
    # Vô hiệu hóa hwaccel cuda để tránh lỗi CUDA_ERROR_MAP_FAILED trên VRAM thấp (4GB)
    return False

def main():
    parser = argparse.ArgumentParser(description="Module 8: Làm mờ vùng (Regional Blur) - Tối ưu GPU")
    parser.add_argument("--video_in", required=True, help="Video đầu vào")
    parser.add_argument("--video_out", required=True, help="Video đầu ra")
    parser.add_argument("--x", type=int, required=True, help="Tọa độ X")
    parser.add_argument("--y", type=int, required=True, help="Tọa độ Y")
    parser.add_argument("--w", type=int, required=True, help="Chiều rộng vùng mờ")
    parser.add_argument("--h", type=int, required=True, help="Chiều cao vùng mờ")
    parser.add_argument("--blur", type=int, default=25, help="Mức độ mờ (mặc định 25, max FFmpeg = 25)")
    parser.add_argument("--ffmpeg_path", default="ffmpeg")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file {args.video_in}")
        return

    ffmpeg_cmd = args.ffmpeg_path
    
    console.print(f"[bold blue]⚡ ĐANG XỬ LÝ LÀM MỜ VÙNG:[/bold blue] {args.video_in}")
    console.print(f"Vùng: x={args.x}, y={args.y}, w={args.w}, h={args.h}, mức mờ={args.blur}")
    
    use_gpu = check_gpu(ffmpeg_cmd)
    has_cuda_dec = check_hwaccel_cuda(ffmpeg_cmd)
    
    if use_gpu:
        console.print("[bold green]✅ GPU NVENC SẴN SÀNG![/bold green]")
        encoder = "h264_nvenc"
        preset = "p4"   # Ưu tiên chất lượng
        # TỐI ƯU: Thêm CUDA HW Decode nếu có → full GPU pipeline
        if has_cuda_dec:
            hw_accel = ["-hwaccel", "cuda"]
            console.print("[dim]  + CUDA Hardware Decode ENABLED[/dim]")
        else:
            hw_accel = []
    else:
        encoder = "libx264"
        preset = "fast"
        hw_accel = []

    # Lấy kích thước video thực tế
    try:
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", args.video_in
        ]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True)
        probe_data = json.loads(probe_res.stdout)
        vw = probe_data['streams'][0]['width']
        vh = probe_data['streams'][0]['height']
        
        # Ép về số chẵn (YUV420P)
        real_x = (max(0, min(args.x, vw - 2)) // 2) * 2
        real_y = (max(0, min(args.y, vh - 2)) // 2) * 2
        real_w = (max(2, min(args.w, vw - real_x)) // 2) * 2
        real_h = (max(2, min(args.h, vh - real_y)) // 2) * 2
        
        console.print(f"📏 Cân chỉnh vùng mờ: {real_w}x{real_h} tại {real_x},{real_y} (Video: {vw}x{vh})")
    except:
        real_x = (args.x // 2) * 2
        real_y = (args.y // 2) * 2
        real_w = (args.w // 2) * 2
        real_h = (args.h // 2) * 2

    script_path = os.path.join(os.path.dirname(args.video_out), "temp_filter_blur.txt")
    
    # TỐI ƯU: Loại bỏ split filter → giảm từ 2 bản copy video xuống 1
    # Dùng crop → gblur → overlay trực tiếp trên video gốc
    # gblur an toàn hơn boxblur và không bị lỗi mảng màu xanh lá (chroma limits)
    sigma_val = max(10, args.blur)
    steps_val = 2
    
    # TỐI ƯU FILTER: Không dùng split. 
    # Cách mới: crop trực tiếp từ [0:v], overlay lên [0:v] → chỉ giữ 1 copy + 1 crop nhỏ
    filter_script = (
        f"[0:v] crop={real_w}:{real_h}:{real_x}:{real_y}, "
        f"gblur=sigma={sigma_val}:steps={steps_val} [blurred];\n"
        f"[0:v][blurred] overlay={real_x}:{real_y} [final_video_output]"
    )

    try:
        os.makedirs(os.path.dirname(args.video_out), exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(filter_script)

        # Ưu tiên chất lượng: CQ 24
        encoder_args = ["-c:v", encoder, "-preset", preset, "-cq", "24"] if "nvenc" in encoder else ["-c:v", encoder, "-preset", preset, "-crf", "23"]

        cmd = [
            ffmpeg_cmd, "-y",
        ] + hw_accel + [
            "-i", args.video_in,
            "-filter_complex_script", script_path,
            "-map", "[final_video_output]",
            "-map", "0:a?",
        ] + encoder_args + [
            "-c:a", "copy",
            "-loglevel", "error",
            args.video_out
        ]

        subprocess.run(cmd, check=True)
        
        # Cleanup
        if os.path.exists(script_path): os.remove(script_path)
            
        console.print(f"[bold green]✨ XỬ LÝ BLUR THÀNH CÔNG![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Lỗi khi xử lý video qua FFmpeg:[/bold red] {str(e)}")
        if os.path.exists(script_path): os.remove(script_path)

if __name__ == "__main__":
    main()
