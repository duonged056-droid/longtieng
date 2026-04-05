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
    print("Cảnh báo: Không thể nạp Demucs từ submodules. Đang thử nạp từ hệ thống...")
    from demucs.api import Separator

# Ép thư viện không dùng ký tự điều khiển động để chống tắc ống dẫn UI
console = Console(force_terminal=False, force_interactive=False)

# --- Cấu hình Tối ưu ---
SEGMENT_DURATION_SEC = 1800  # 30 phút mỗi đoạn
OVERLAP_SEC = 10             # 10 giây overlap để tránh artifact ở ranh giới
LONG_VIDEO_THRESHOLD_SEC = 7200  # >2h mới dùng segment mode

def get_audio_duration_sec(audio_path):
    """Lấy duration bằng ffprobe (nhanh, không load file)."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return 0

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

def extract_audio_segment(video_path: str, audio_path: str, start_sec: float, duration_sec: float):
    """Trích xuất một đoạn audio từ video (Fast Seek + Exact Trim)."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{start_sec:.3f}",
        "-i", video_path,
        "-t", f"{duration_sec:.3f}",
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "44100", "-ac", "2",
        audio_path
    ]
    subprocess.run(cmd, check=True)

def save_wav(wav: np.ndarray, output_path: str, sample_rate: int = 44100):
    """Lưu mảng numpy (float32) thành file WAV dùng FFmpeg để hỗ trợ RF64 (>4GB)."""
    # wav shape: [Samples, Channels] hoặc [Channels, Samples]
    # Demucs output thường là [Samples, Channels] sau khi .T
    if wav.ndim > 1:
        channels = wav.shape[1]
    else:
        channels = 1
    
    # Chuẩn hóa về int16 để tiết kiệm dung lượng và tương thích cao
    wav_norm = np.clip(wav * 32767, -32768, 32767).astype(np.int16)
    
    # Dùng FFmpeg để ghi file từ raw pcm_s16le
    # FFmpeg sẽ tự động xử lý RF64 nếu file > 4GB
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels),
        "-i", "pipe:0",
        "-acodec", "pcm_s16le", 
        output_path
    ]
    
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    process.communicate(input=wav_norm.tobytes())


def separate_single(separator, audio_path: str, vocal_out: str, bgm_out: str):
    """Tách 1 file audio → vocals + bgm."""
    origin, separated = separator.separate_audio_file(audio_path)
    
    # Track 1: Vocals
    vocals = separated['vocals'].numpy().T
    save_wav(vocals, vocal_out)
    
    # Track 2: BGM (drums + bass + other)
    instruments = None
    for k, v in separated.items():
        if k == 'vocals':
            continue
        if instruments is None:
            instruments = v
        else:
            instruments += v
    bgm = instruments.numpy().T
    save_wav(bgm, bgm_out)
    
    # Giải phóng tensor ngay
    del origin, separated, vocals, instruments, bgm
    gc.collect()

def concat_wav_files(file_list, output_path, overlap_sec=0, sample_rate=44100):
    """Ghép nối danh sách WAV files với crossfade ở overlap."""
    overlap_samples = int(overlap_sec * sample_rate)
    
    combined = None
    for i, fpath in enumerate(file_list):
        sr, data = wavfile.read(fpath)
        data = data.astype(np.float32) / 32767.0
        
        if combined is None:
            combined = data
        else:
            if overlap_samples > 0 and i > 0:
                # Crossfade: linear blend ở vùng overlap
                ol = min(overlap_samples, len(combined), len(data))
                if ol > 0:
                    fade_out = np.linspace(1.0, 0.0, ol).reshape(-1, 1) if data.ndim > 1 else np.linspace(1.0, 0.0, ol)
                    fade_in = np.linspace(0.0, 1.0, ol).reshape(-1, 1) if data.ndim > 1 else np.linspace(0.0, 1.0, ol)
                    combined[-ol:] = combined[-ol:] * fade_out + data[:ol] * fade_in
                    combined = np.concatenate([combined, data[ol:]])
                else:
                    combined = np.concatenate([combined, data])
            else:
                combined = np.concatenate([combined, data])
        
        # Giải phóng data segment ngay
        del data
    
    if combined is not None:
        save_wav(combined, output_path, sample_rate)
        del combined
    gc.collect()

def separate_audio(audio_path: str, vocal_out: str, bgm_out: str, model_name: str = "htdemucs", video_path: str = None):
    """Sử dụng Demucs để tách lời và nhạc nền - Có segment mode cho video dài."""
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        console.print("[bold red]CẢNH BÁO:[/bold red] Không tìm thấy GPU NVIDIA, đang chạy trên CPU.")
    else:
        console.print(f"[bold green]GPU Đang chạy:[/bold green] {torch.cuda.get_device_name(0)}")
        # Hiển thị VRAM
        vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
        console.print(f"[dim]VRAM: {vram_mb:.0f} MB[/dim]")

    console.print(f"[bold cyan]Đang khởi tạo Demucs ({model_name})...[/bold cyan]")
    separator = Separator(model=model_name, device=device, shifts=0)
    
    # Kiểm tra duration để quyết định mode
    audio_dur = get_audio_duration_sec(audio_path)
    
    if audio_dur > LONG_VIDEO_THRESHOLD_SEC:
        # ========== SEGMENT MODE (Video >2h - PREMIUM) ==========
        console.print(f"[bold yellow]📐 VIDEO SIÊU DÀI ({audio_dur/3600:.2f}h)[/bold yellow]")
        console.print(f"[dim]  + Chế độ: SEGMENT MODE (Cắt lát {SEGMENT_DURATION_SEC//60}p)[/dim]")
        
        temp_dir = os.path.dirname(vocal_out)
        vocal_parts = []
        bgm_parts = []
        
        seg_idx = 0
        current_sec = 0
        total_segments = int(np.ceil(audio_dur / SEGMENT_DURATION_SEC))

        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeRemainingColumn
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            main_task = progress.add_task("Đang tách âm thanh đa tầng...", total=total_segments)
            
            while current_sec < audio_dur:
                seg_start = max(0, current_sec - OVERLAP_SEC) if seg_idx > 0 else 0
                seg_dur = SEGMENT_DURATION_SEC + (OVERLAP_SEC if seg_idx > 0 else 0)
                seg_dur = min(seg_dur, audio_dur - seg_start)
                
                seg_audio = os.path.join(temp_dir, f"_seg_audio_{seg_idx}.wav")
                seg_vocal = os.path.join(temp_dir, f"_seg_vocal_{seg_idx}.wav")
                seg_bgm = os.path.join(temp_dir, f"_seg_bgm_{seg_idx}.wav")
                
                progress.update(main_task, description=f"Đang xử lý Đoạn {seg_idx+1}/{total_segments}...")
                
                # Extract segment audio
                source = video_path if video_path else audio_path
                extract_audio_segment(source, seg_audio, seg_start, seg_dur)
                
                # Tách
                separate_single(separator, seg_audio, seg_vocal, seg_bgm)
                
                vocal_parts.append(seg_vocal)
                bgm_parts.append(seg_bgm)
                
                # Xóa segment audio tạm ngay
                if os.path.exists(seg_audio):
                    os.remove(seg_audio)
                
                # TỐI ƯU CỰC ĐỘ: Force GPU cleanup triệt để
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                gc.collect()
                
                progress.advance(main_task)
                seg_idx += 1
                current_sec += SEGMENT_DURATION_SEC
        
        # Ghép nối kết quả
        console.print("[bold cyan]🔄 Đang hợp nhất các lát cắt (Merging segments)...[/bold cyan]")
        concat_wav_files(vocal_parts, vocal_out, overlap_sec=OVERLAP_SEC if len(vocal_parts) > 1 else 0)
        concat_wav_files(bgm_parts, bgm_out, overlap_sec=OVERLAP_SEC if len(bgm_parts) > 1 else 0)
        
        # Cleanup segment files
        for f in vocal_parts + bgm_parts:
            if os.path.exists(f):
                os.remove(f)
    else:
        # ========== NORMAL MODE (Video <=2h) ==========
        console.print(f"[bold yellow]⚡ Đang tiến hành tách âm thanh trực tiếp...[/bold yellow]")
        separate_single(separator, audio_path, vocal_out, bgm_out)

    console.print(f"[bold green]✅ TÁCH ÂM THÀNH CÔNG![/bold green]")
    console.print(f" [dim]• Vocals: {os.path.basename(vocal_out)}[/dim]")
    console.print(f" [dim]• BGM:    {os.path.basename(bgm_out)}[/dim]")

    # Giải phóng VRAM toàn phần
    del separator
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()

def main():
    parser = argparse.ArgumentParser(description="Module 1: Tách âm thanh Vocals & BGM (Tối ưu RAM/VRAM)")
    parser.add_argument("--video_in", required=True, help="Video đầu vào")
    parser.add_argument("--output_dir", required=True, help="Thư mục đầu ra")
    parser.add_argument("--model", default="htdemucs", help="Model Demucs (htdemucs, htdemucs_ft, mdx_extra)")
    
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    temp_audio = os.path.join(args.output_dir, "temp_full_audio.wav")
    vocal_out = os.path.join(args.output_dir, "vocal_clean.wav")
    bgm_out = os.path.join(args.output_dir, "bgm_clean.wav")
    
    try:
        # Bước 1: Trích xuất audio
        extract_audio(args.video_in, temp_audio)
        # Bước 2: Tách âm (tự động chọn mode theo duration)
        separate_audio(temp_audio, vocal_out, bgm_out, args.model, video_path=args.video_in)
    except Exception as e:
        console.print(f"[bold red]Lỗi Module 1:[/bold red] {str(e)}")
    finally:
        # Dọn dẹp file tạm
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
            console.print("[dim]Đã dọn dẹp file tạm.[/dim]")

if __name__ == "__main__":
    main()
