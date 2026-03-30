import cv2
import argparse
import sys
import os
from rich.console import Console

console = Console()

def get_blur_box(video_path: str):
    """
    Trích xuất một khung hình từ video và cho phép người dùng chọn vùng che sub (ROI).
    """
    if not os.path.exists(video_path):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file video: {video_path}")
        return

    console.print(f"[bold blue]Đang xử lý video:[/bold blue] {video_path}")
    cap = cv2.VideoCapture(video_path)
    
    # Lấy frame tại giây thứ 5 (hoặc frame đầu tiên nếu video ngắn)
    fps = cap.get(cv2.CAP_PROP_FPS)
    target_frame = int(fps * 5.0)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    
    ret, frame = cap.read()
    if not ret:
        # Nếu giây thứ 5 không lấy được, lấy frame đầu tiên
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
    
    cap.release()

    if not ret:
        console.print("[bold red]Lỗi:[/bold red] Không thể đọc khung hình từ video.")
        return

    # Hiển thị UI chọn vùng
    console.print("[bold yellow]HÀNH ĐỘNG:[/bold yellow] Hãy dùng chuột kéo vẽ hình chữ nhật đè lên vùng phụ đề cũ.")
    console.print("[bold cyan]Lưu ý:[/bold cyan] Nhấn [bold white]ENTER[/bold white] để xác nhận hoặc [bold white]ESC[/bold white] để hủy.")
    
    # Mở cửa sổ chọn ROI
    # showCrosshair=True giúp căn chỉnh tốt hơn
    roi = cv2.selectROI("Chon vung che Sub (LongTieng 2026)", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    
    # ROI: (x, y, w, h)
    x, y, w, h = [int(v) for v in roi]
    
    if w > 0 and h > 0:
        blur_box_str = f"{x},{y},{w},{h}"
        console.print("\n" + "="*50)
        console.print(f"[bold green]XÁC NHẬN TỌA ĐỘ THÀNH CÔNG![/bold green]")
        console.print(f"Tham số cho bước Mux Video là:")
        console.print(f"[bold magenta]--blur_box \"{blur_box_str}\"[/bold magenta]")
        console.print("="*50 + "\n")
        
        # Lưu vào file tạm để dễ copy
        with open("blur_box.txt", "w") as f:
            f.write(blur_box_str)
        console.print(f"[dim]Tọa độ đã được lưu vào file 'blur_box.txt'[/dim]")
    else:
        console.print("[bold yellow]Cảnh báo:[/bold yellow] Bạn đã hủy chọn hoặc chọn vùng không hợp lệ.")

def main():
    parser = argparse.ArgumentParser(description="Công cụ lấy tọa độ che sub (LongTieng 2026 Edition)")
    parser.add_argument("--video_in", required=True, help="Đường dẫn file video MP4")
    
    # Xử lý trường hợp chạy không có GUI (server)
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
        
    args = parser.parse_args()
    
    try:
        get_blur_box(args.video_in)
    except Exception as e:
        console.print(f"[bold red]Lỗi hệ thống:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()
