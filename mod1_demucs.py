import os
import sys
import argparse
import subprocess
import torch
import gc
import numpy as np
from scipy.io import wavfile
from rich.console import Console

# Thêm submodule vào đường dẫn nếu cần
sys.path.append(os.path.join(os.path.dirname(__file__), "submodules", "demucs"))

# Import demucs sau khi set path
try:
    from demucs.api import Separator
except ImportError:
    # Nếu không import được từ API, thử install nếu cần (nhưng ở đây giả định có sẵn)
    print("Cảnh báo: Không thể nạp Demucs từ submodules. Đang thử nạp từ hệ thống...")
    from demucs.api import Separator

console = Console()

def extract_audio(video_path: str, audio_path: str):
    """Trích xuất âm thanh gốc từ video (44.1kHz Stereo)."""
    console.print(f"[bold blue]Đang trích xuất âm thanh từ:[/bold blue] {video_path}")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "44100", "-ac", "2",
        audio_path
    ]
    subprocess.run(cmd, check=True)
    console.print("[green]Trích xuất hoàn tất.[/green]")

def save_wav(wav: np.ndarray, output_path: str, sample_rate: int = 44100):
    """Lưu mảng numpy (float32) thành file WAV (int16)."""
    wav_norm = wav * 32767
    wavfile.write(output_path, sample_rate, wav_norm.astype(np.int16))

def separate_audio(audio_path: str, vocal_out: str, bgm_out: str):
    """Sử dụng Demucs (htdemucs) tách lời và nhạc nền."""
    
    # Kiểm tra GPU NVIDIA (Yêu cầu 2026)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        console.print("[bold red]CẢNH BÁO:[/bold red] Không tìm thấy GPU NVIDIA, đang chạy trên CPU (Tốc độ sẽ rất chậm).")
    else:
        console.print(f"[bold green]GPU Đang chạy:[/bold green] {torch.cuda.get_device_name(0)}")

    console.print(f"[bold cyan]Đang khởi tạo Demucs (htdemucs)...[/bold cyan]")
    
    # Tối ưu: shifts=0 để đạt tốc độ tối đa cho reup
    separator = Separator(model="htdemucs", device=device, shifts=0)
    
    console.print(f"[bold yellow]Đang tiến hành tách âm thanh... (Vui lòng đợi)[/bold yellow]")
    origin, separated = separator.separate_audio_file(audio_path)
    
    # Separated là dict chứa các track: vocals, drums, bass, other
    # Track 1: Vocals (Giọng nói)
    vocals = separated['vocals'].numpy().T
    save_wav(vocals, vocal_out)
    
    # Track 2: BGM (Tổng hợp drums + bass + other)
    # Chúng ta cộng gộp các track không phải vocals
    instruments = None
    for k, v in separated.items():
        if k == 'vocals': continue
        if instruments is None:
            instruments = v
        else:
            instruments += v
            
    bgm = instruments.numpy().T
    save_wav(bgm, bgm_out)
    
    console.print(f"[bold green]TÁCH ÂM THÀNH CÔNG![/bold green]")
    console.print(f"- Vocal: {vocal_out}")
    console.print(f"- BGM: {bgm_out}")

    # Giải phóng VRAM ngay lập tức (Yêu cầu 2026)
    del separator, origin, separated
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

def main():
    parser = argparse.ArgumentParser(description="Module 1: Tách âm thanh Vocals & BGM (LongTieng 2026 Edition)")
    parser.add_argument("--video_in", required=True, help="Video đầu vào")
    parser.add_argument("--vocal_out", default="vocal.wav", help="File vocal đầu ra")
    parser.add_argument("--bgm_out", default="bgm.wav", help="File nhạc nền đầu ra")
    
    args = parser.parse_args()
    
    temp_audio = "temp_full_audio.wav"
    
    try:
        # Bước 1: Trích xuất audio
        extract_audio(args.video_in, temp_audio)
        # Bước 2: Tách âm
        separate_audio(temp_audio, args.vocal_out, args.bgm_out)
    except Exception as e:
        console.print(f"[bold red]Lỗi Module 1:[/bold red] {str(e)}")
    finally:
        # Dọn dẹp file tạm
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
            console.print("[dim]Đã dọn dẹp file tạm.[/dim]")

if __name__ == "__main__":
    main()
