import os
import sys
import argparse
import torch
import gc
import whisperx
from rich.console import Console
from transformers import Wav2Vec2Processor

# Vá lỗi sampling_rate cho tiếng Trung trong transformers (Yêu cầu 2026)
if not hasattr(Wav2Vec2Processor, 'sampling_rate'):
    Wav2Vec2Processor.sampling_rate = 16000

console = Console()

def format_srt_time(seconds: float) -> str:
    """Định dạng giây sang SRT time (00:00:00,000)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msecs = int(round((seconds % 1) * 1000))
    if msecs == 1000: # Xử lý làm tròn lên
        secs += 1
        msecs = 0
    return f"{hrs:02}:{mins:02}:{secs:02},{msecs:03}"

def save_as_srt(segments, srt_path):
    """Lưu kết quả transcription thành file SRT."""
    console.print(f"[bold blue]Đang ghi file SRT:[/bold blue] {srt_path}")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = format_srt_time(seg['start'])
            end = format_srt_time(seg['end'])
            text = seg['text'].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

def run_asr(audio_in: str, srt_out: str):
    """Quy trình nhận dạng: Whisper -> Alignment -> Export."""
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        console.print("[bold red]LỖI:[/bold red] Module ASR yêu cầu GPU NVIDIA để chạy WhisperX mượt mà.")
        # Tuy nhiên vẫn cho chạy cpu nếu người dùng kiên trì
    else:
        console.print(f"[bold green]GPU Đang chạy:[/bold green] {torch.cuda.get_device_name(0)}")

    download_root = 'models/ASR/whisper'
    os.makedirs(download_root, exist_ok=True)

    # Bước 1: Load WhisperX Model
    console.print(f"[bold cyan]Đang nạp mô hình WhisperX (large-v3)...[/bold cyan]")
    # int8_float16 tối ưu cho card 4GB VRAM
    compute_type = "int8_float16" if device == "cuda" else "int8"
    
    try:
        model = whisperx.load_model("large-v3", device, compute_type=compute_type, download_root=download_root)
        
        console.print(f"[bold yellow]Đang tiến hành nhận dạng tiếng Trung (zh)...[/bold yellow]")
        result = model.transcribe(audio_in, batch_size=4, language='zh')
        
        # Giải phóng model ngay để dọn chỗ cho Alignment (Tối ưu RAM)
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        # Bước 2: Alignment (Làm khớp thời gian millisecond)
        console.print(f"[bold cyan]Đang khớp thời gian (Alignment)...[/bold cyan]")
        model_a, metadata = whisperx.load_align_model(language_code="zh", device=device, model_dir=download_root)
        
        # Vá lỗi sampling_rate cho align_model
        target = getattr(model_a, "processor", model_a)
        if target is not None and not hasattr(target, 'sampling_rate'):
            target.sampling_rate = 16000
            
        aligned_result = whisperx.align(result["segments"], model_a, metadata, audio_in, device, return_char_alignments=False)
        
        # Bước 3: Xuất kết quả
        save_as_srt(aligned_result["segments"], srt_out)
        
        console.print(f"[bold green]NHẬN DẠNG HOÀN TẤT![/bold green]")
        console.print(f"- SRT Output: {srt_out}")

        # Dọn dẹp GPU (Yêu cầu 2026)
        del model_a, metadata, result, aligned_result
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    except Exception as e:
        console.print(f"[bold red]Lỗi Module 2:[/bold red] {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Module 2: Nhận dạng giọng nói Trung Quốc (LongTieng 2026 Edition)")
    parser.add_argument("--vocal_in", required=True, help="File vocal sạch")
    parser.add_argument("--srt_out", default="zh_output.srt", help="File SRT tiếng Trung")
    
    args = parser.parse_args()
    
    try:
        run_asr(args.vocal_in, args.srt_out)
    except Exception as e:
        console.print(f"[bold red]Lỗi hệ thống:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()
