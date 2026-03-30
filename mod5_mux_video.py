import os
import argparse
import subprocess
from rich.console import Console

console = Console()

def mux_video(video_in, tts_in, bgm_in, srt_vi_in, blur_box, video_out, fps=30):
    """
    Sử dụng 1 lệnh FFmpeg duy nhất để Render video thành phẩm.
    """
    if not os.path.exists(video_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy video gốc: {video_in}")
        return

    # Đường dẫn font Arial hỗ trợ tiếng Việt
    font_path = "C:/Windows/Fonts/arial.ttf"
    # Xử lý đường dẫn SRT đặc biệt cho FFmpeg filter trên Windows
    escaped_srt = srt_vi_in.replace(':', '\\:').replace('\\', '/')
    
    # 1. Xây dựng Video Filter: Blur vùng sub cũ -> Gắn Hardsub mới
    video_filter = "[0:v]"
    
    # Blur theo tọa đối (x,y,w,h)
    if blur_box:
        try:
            x, y, w, h = blur_box.split(',')
            video_filter += f"split[orig][v_blur];[v_blur]crop={w}:{h}:{x}:{y},boxblur=20:10[blurred];[orig][blurred]overlay={x}:{y}"
        except Exception as e:
            console.print(f"[yellow]Cảnh báo:[/yellow] Tọa độ blur_box sai định dạng. Bỏ qua bước blur. ({e})")
            
    # Gắn Hardsub
    video_filter += f",subtitles='{escaped_srt}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2'"
    
    # 2. Xây dựng Audio Filter: Trộn TTS và BGM (BGM vol 0.3)
    # [1:a] là TTS, [2:a] là BGM
    audio_filter = "[1:a]volume=1.0[v_tts];[2:a]volume=0.3[v_bgm];[v_tts][v_bgm]amix=inputs=2:duration=first"
    
    # 3. Lệnh FFmpeg tổng hợp (Dùng NVIDIA NVENC nếu có)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_in,
        "-i", tts_in,
        "-i", bgm_in,
        "-filter_complex", f"{video_filter};{audio_filter}",
        "-map", f"[v]" if blur_box else "0:v", # Nếu không blur thì lấy gốc, nhưng ở đây filter video_filter luôn kết thúc bằng hardsub nên cần map
        "-map", "[a]",
        "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq", "-b:v", "5M",
        "-c:a", "aac", "-b:a", "192k",
        "-r", str(fps),
        video_out
    ]
    
    # Nếu không dùng nvenc (đối với máy không có NVIDIA), đổi sang libx264
    # Nhưng theo yêu cầu là tối ưu 2026 và máy user có RTX 3050 Ti nên h264_nvenc là chuẩn bài.

    console.print(f"[bold blue]Đang Render video thành phẩm...[/bold blue]")
    try:
        # Nếu lệnh trên bị lỗi map (do logic filter_complex phức tạp), ta fix map đơn giản hơn
        # Gán nhãn cho output video filter
        video_filter_final = f"{video_filter}[v_out]"
        audio_filter_final = f"{audio_filter}[a_out]"
        
        cmd_fixed = [
            "ffmpeg", "-y",
            "-i", video_in,
            "-i", tts_in,
            "-i", bgm_in,
            "-filter_complex", f"{video_filter_final};{audio_filter_final}",
            "-map", "[v_out]",
            "-map", "[a_out]",
            "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq",
            "-c:a", "aac",
            video_out
        ]
        
        subprocess.run(cmd_fixed, check=True)
        console.print(f"[bold green]RENDER VIDEO THÀNH CÔNG![/bold green] -> {video_out}")
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Lỗi Render FFmpeg:[/bold red] {e}")

def main():
    parser = argparse.ArgumentParser(description="Module 5: Render Video Hardsub & Mix Audio (2026 Standard)")
    parser.add_argument("--video_in", required=True, help="Video gốc")
    parser.add_argument("--tts_in", required=True, help="Audio lồng tiếng sạch")
    parser.add_argument("--bgm_in", required=True, help="Nhạc nền")
    parser.add_argument("--srt_vi_in", required=True, help="Phụ đề tiếng Việt")
    parser.add_argument("--blur_box", help="Tọa độ vùng che sub (x,y,w,h)")
    parser.add_argument("--video_out", default="final_video.mp4", help="Video đầu ra")
    parser.add_argument("--fps", type=int, default=30)
    
    args = parser.parse_args()
    
    mux_video(args.video_in, args.tts_in, args.bgm_in, args.srt_vi_in, args.blur_box, args.video_out, args.fps)

if __name__ == "__main__":
    main()
