import os
import argparse
import cv2
import numpy as np
from moviepy import VideoFileClip
from rich.console import Console
from tqdm import tqdm

console = Console()

def apply_regional_blur(frame, x, y, w, h, blur_radius=51):
    """Làm mờ vùng chỉ định bằng OpenCV Gaussian Blur."""
    # Đảm bảo bán kính lẻ
    r = blur_radius if blur_radius % 2 != 0 else blur_radius + 1
    
    # Lấy vùng ROI
    roi = frame[y:y+h, x:x+w]
    if roi.size == 0:
        return frame
        
    # Làm mờ
    blurred_roi = cv2.GaussianBlur(roi, (r, r), 0)
    
    # Ghi đè lại vào frame gốc
    new_frame = frame.copy()
    new_frame[y:y+h, x:x+w] = blurred_roi
    return new_frame

def main():
    parser = argparse.ArgumentParser(description="Module 8: Làm mờ vùng (Regional Blur) cho Video")
    parser.add_argument("--video_in", required=True, help="Video đầu vào")
    parser.add_argument("--video_out", required=True, help="Video đầu ra")
    parser.add_argument("--x", type=int, required=True, help="Tọa độ X")
    parser.add_argument("--y", type=int, required=True, help="Tọa độ Y")
    parser.add_argument("--w", type=int, required=True, help="Chiều rộng vùng mờ")
    parser.add_argument("--h", type=int, required=True, help="Chiều cao vùng mờ")
    parser.add_argument("--blur", type=int, default=51, help="Độ mức độ mờ (mặc định 51)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file {args.video_in}")
        return

    console.print(f"[bold blue]Đang xử lý làm mờ vùng:[/bold blue] {args.video_in}")
    console.print(f"Vùng: x={args.x}, y={args.y}, w={args.w}, h={args.h}, mức mờ={args.blur}")
    
    try:
        clip = VideoFileClip(args.video_in)
        
        # Xử lý từng frame
        # MoviePy transformation (fl_image áp dụng cho mảng numpy)
        blurred_clip = clip.image_transform(lambda frame: apply_regional_blur(frame, args.x, args.y, args.w, args.h, args.blur))
        
        # Xuất video
        os.makedirs(os.path.dirname(args.video_out), exist_ok=True)
        # Sử dụng codec libx264 để đảm bảo chất lượng và tương thích
        blurred_clip.write_videofile(
            args.video_out, 
            codec="libx264", 
            audio_codec="aac",
            temp_audiofile="temp-audio.m4a", 
            remove_temp=True,
            threads=4,
            logger='bar'
        )
        
        clip.close()
        console.print(f"[bold green]XỬ LÝ THÀNH CÔNG![/bold green] File: {args.video_out}")
        
    except Exception as e:
        console.print(f"[bold red]Lỗi khi xử lý video:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()
