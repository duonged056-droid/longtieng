import os
import sys
import argparse
import torch
import gc
import whisperx
import warnings
from rich.console import Console
from transformers import Wav2Vec2Processor

# Tắt các cảnh báo không cần thiết từ thư viện (torchaudio, pyannote, v.v.)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*backend.*")
warnings.filterwarnings("ignore", message=".*ReproducibilityWarning.*")

# Tối ưu hóa hiệu năng cho GPU NVIDIA (RTX 30 series trở lên)
if torch.cuda.is_available():
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

if os.name == 'nt':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_dir = os.path.join(base_dir, "env", "Lib", "site-packages", "nvidia")
    if os.path.exists(env_dir):
        for d in os.listdir(env_dir):
            bin_dir = os.path.join(env_dir, d, "bin")
            if os.path.exists(bin_dir):
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, 'add_dll_directory'):
                    try:
                        os.add_dll_directory(bin_dir)
                    except Exception:
                        pass

# Vá lỗi sampling_rate cho tiếng Trung trong transformers (Yêu cầu 2026)
if not hasattr(Wav2Vec2Processor, 'sampling_rate'):
    Wav2Vec2Processor.sampling_rate = 16000

console = Console()

import cv2
import numpy as np

def format_srt_time(seconds: float) -> str:
    """Định dạng giây sang SRT time (00:00:00,000)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msecs = int(round((seconds % 1) * 1000))
    if msecs == 1000:
        secs += 1
        msecs = 0
    return f"{hrs:02}:{mins:02}:{secs:02},{msecs:03}"

def filter_roi(frame, roi):
    x, y, w, h = map(int, roi.split(":"))
    return frame[y:y+h, x:x+w]

def extract_visual_blocks(video_in, roi, sim_thresh=0.85, fps_target=10.0, min_dur=0.05):
    """Quét video theo ROI - TỐI ƯU: đọc tuần tự thay vì random seek, downsample ROI."""
    cap = cv2.VideoCapture(video_in)
    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    if not orig_fps or orig_fps <= 0:
        orig_fps = 25.0
        
    frame_skip = int(max(1, round(orig_fps / fps_target)))
    
    # TỐI ƯU: Đọc kích thước ROI target để downsample
    roi_x, roi_y, roi_w, roi_h = map(int, roi.split(":"))
    # Downsample ROI về max 200px width để tính MSE nhanh hơn
    ds_scale = min(1.0, 200.0 / max(roi_w, 1))
    ds_w = max(1, int(roi_w * ds_scale))
    ds_h = max(1, int(roi_h * ds_scale))
    
    blocks = []
    prev_roi_gray = None
    prev_change_time = 0.0
    
    frame_idx = 0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # TỐI ƯU: Đọc tuần tự + skip frames bằng grab() thay vì cap.set() random seek
    # Random seek trên SSD vẫn chậm hơn sequential read + skip
    while frame_idx < total_frames:
        ret = cap.grab()
        if not ret:
            break
            
        if frame_idx % frame_skip == 0:
            ret, frame = cap.retrieve()
            if not ret:
                frame_idx += 1
                continue
                
            current_time = frame_idx / orig_fps
            roi_img = frame[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]
            
            # TỐI ƯU: Downsample trước khi grayscale + blur → ít pixel hơn = nhanh hơn
            if ds_scale < 1.0:
                roi_img = cv2.resize(roi_img, (ds_w, ds_h), interpolation=cv2.INTER_AREA)
            
            roi_gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
            roi_gray = cv2.GaussianBlur(roi_gray, (3, 3), 0)
            
            if prev_roi_gray is not None:
                # Tính MSE
                err = np.sum((prev_roi_gray.astype("float") - roi_gray.astype("float")) ** 2)
                err /= float(prev_roi_gray.shape[0] * prev_roi_gray.shape[1])
                sim = 1.0 - min(err / 255.0, 1.0) 
                
                if sim < sim_thresh:
                    dur = current_time - prev_change_time
                    if dur >= min_dur:
                        blocks.append({'start': prev_change_time, 'end': current_time})
                    prev_change_time = current_time
                    prev_roi_gray = roi_gray
            else:
                prev_roi_gray = roi_gray
                prev_change_time = current_time
                
        frame_idx += 1
        
    cap.release()
    
    if frame_idx > 0 and (frame_idx / orig_fps) - prev_change_time >= min_dur:
        blocks.append({'start': prev_change_time, 'end': frame_idx / orig_fps})
        
    return blocks

def align_words_to_blocks(words, blocks):
    """Nhét các từ vào trong các block visual timeline."""
    new_segments = []
    
    block_idx = 0
    current_text = ""
    current_words = []
    
    for w in words:
        if 'start' not in w or 'end' not in w:
            continue
            
        w_mid = (w['start'] + w['end']) / 2.0
        
        while block_idx < len(blocks) - 1 and w_mid > blocks[block_idx]['end']:
            if current_words:
                new_segments.append({
                    'start': current_words[0]['start'],
                    'end': current_words[-1]['end'],
                    'text': current_text.strip(),
                    'words': current_words
                })
                current_words = []
                current_text = ""
            block_idx += 1
            
        current_words.append(w)
        current_text += w.get('word', '')
        
    if current_words:
        new_segments.append({
            'start': current_words[0]['start'],
            'end': current_words[-1]['end'],
            'text': current_text.strip(),
            'words': current_words
        })
        
    return new_segments

def split_segments(segments, max_chars=18, max_gap=0.5, video_in=None, roi=None, sim=0.85, fps=10.0):
    """Chia câu thông minh như thuật toán Smart Subtitle của CapCut."""
    if video_in and roi and str(video_in).lower() != "none" and str(roi).lower() != "none":
        console.print("[bold cyan]Đang chạy quét Visual OCR Timeline để khớp phụ đề 100% với video...[/bold cyan]")
        
        blocks = extract_visual_blocks(video_in, roi, sim_thresh=sim, fps_target=fps)
        
        all_words = []
        for seg in segments:
            if 'words' in seg:
                all_words.extend(seg['words'])
                
        if blocks and all_words:
            aligned = align_words_to_blocks(all_words, blocks)
            if aligned:
                console.print(f"[bold green]Visual Scan thành công: Tạo ra {len(aligned)} câu![/bold green]")
                segments = aligned

    # THUẬT TOÁN AUDIO SMART NLP
    all_units = []
    for seg in segments:
        if 'words' in seg and seg['words']:
            for w in seg['words']:
                if w.get('word', '').strip():
                    all_units.append(w)
        elif seg.get('text', '').strip():
            all_units.append({
                'word': seg['text'].strip(),
                'start': seg.get('start', 0),
                'end': seg.get('end', 0)
            })

    if not all_units:
        return segments

    new_segments = []
    current_words = []
    current_text = ""
    
    sentence_ends = ['。', '！', '？', '；', '!', '?', ';', '…']
    particles = ['了', '啊', '吗', '呢', '吧', '的', '呐', '呀']

    for i, w in enumerate(all_units):
        word_text = w.get('word', '').strip()
        current_words.append(w)
        current_text += word_text
        
        is_last = (i == len(all_units) - 1)
        next_gap = 0
        if not is_last:
            next_unit = all_units[i+1]
            if 'start' in next_unit and 'end' in w:
                next_gap = max(0, next_unit['start'] - w['end'])

        should_split = False
        
        if any(p in word_text for p in sentence_ends):
            should_split = True
        elif next_gap > 1.0:
            should_split = True
        elif next_gap > max_gap:
            if len(current_text) >= 10:
                should_split = True
        elif len(current_text) >= 15:
            if any(p in word_text for p in particles + [',', '，']):
                if next_gap > 0.1:
                    should_split = True
        elif len(current_text) >= 22:
            should_split = True

        if next_gap < 0.1 and not any(p in word_text for p in sentence_ends) and not is_last:
            should_split = False

        if should_split or is_last:
            start_time = current_words[0]['start']
            end_time = current_words[-1]['end']
            
            if is_last and end_time - start_time < 0.8:
                end_time = start_time + 0.8

            new_segments.append({
                'start': start_time,
                'end': end_time,
                'text': current_text.strip(),
                'words': current_words
            })
            current_words = []
            current_text = ""

    return new_segments

def save_as_srt(segments, srt_path, video_in=None, roi=None, sim=0.85, fps=10.0):
    """Lưu kết quả transcription thành file SRT."""
    segments = split_segments(segments, max_chars=18, max_gap=0.5, video_in=video_in, roi=roi, sim=sim, fps=fps)
    
    console.print(f"[bold blue]Đang ghi file SRT:[/bold blue] {srt_path}")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = format_srt_time(seg['start'])
            end = format_srt_time(seg['end'])
            text = seg['text'].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

def get_optimal_batch_size():
    """Tự động chọn batch_size dựa trên VRAM."""
    if not torch.cuda.is_available():
        return 2
    vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
    if vram_mb < 4096:    # <4GB VRAM
        return 1
    elif vram_mb < 6144:  # <6GB VRAM
        return 2
    elif vram_mb < 8192:  # <8GB VRAM
        return 4
    else:
        return 8

def run_asr(audio_in: str, srt_out: str, batch_size: int = 4, mode="normal", video_in=None, roi=None, sim=0.85, fps=2.0):
    """Quy trình nhận dạng: Whisper -> Alignment -> Export.
    TỐI ƯU: Auto batch_size, synchronize trước empty_cache, tuần tự model load."""
            
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        console.print("[bold red]LỖI:[/bold red] Module ASR yêu cầu GPU NVIDIA.")
    else:
        vram_mb = torch.cuda.get_device_properties(0).total_memory / (1024**2)
        console.print(f"[bold green]GPU:[/bold green] {torch.cuda.get_device_name(0)} ({vram_mb:.0f} MB VRAM)")

    # TỐI ƯU: Auto-detect VRAM và giảm batch_size
    optimal_bs = get_optimal_batch_size()
    if batch_size > optimal_bs:
        console.print(f"[yellow]⚡ Auto-tune batch_size: {batch_size} → {optimal_bs} (phù hợp VRAM)[/yellow]")
        batch_size = optimal_bs

    download_root = 'models/ASR/whisper'
    os.makedirs(download_root, exist_ok=True)

    # Bước 1: Load WhisperX Model
    console.print(f"[bold cyan]Đang nạp mô hình WhisperX (large-v3) [batch={batch_size}]...[/bold cyan]")
    compute_type = "int8_float16" if device == "cuda" else "int8"
    
    try:
        model = whisperx.load_model("large-v3", device, compute_type=compute_type, download_root=download_root)
        
        console.print(f"[bold yellow]Đang tiến hành nhận dạng tiếng Trung (zh)...[/bold yellow]")
        result = model.transcribe(audio_in, batch_size=batch_size, language='zh')
        
        # TỐI ƯU: Đảm bảo GPU xong hoàn toàn trước khi free
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()  # Chờ GPU xong tất cả operations
            torch.cuda.empty_cache()
            
        # Bước 2: Alignment
        console.print(f"[bold cyan]Đang khớp thời gian (Alignment)...[/bold cyan]")
        model_a, metadata = whisperx.load_align_model(language_code="zh", device=device, model_dir=download_root)
        
        target = getattr(model_a, "processor", model_a)
        if target is not None and not hasattr(target, 'sampling_rate'):
            target.sampling_rate = 16000
            
        aligned_result = whisperx.align(result["segments"], model_a, metadata, audio_in, device, return_char_alignments=False)
        
        # Bước 3: Xuất kết quả
        save_as_srt(aligned_result["segments"], srt_out, video_in=video_in, roi=roi, sim=sim, fps=fps)
        
        console.print(f"[bold green]NHẬN DẠNG HOÀN TẤT![/bold green]")
        console.print(f"- SRT Output: {srt_out}")

        del model_a, metadata, result, aligned_result
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()

    except Exception as e:
        console.print(f"[bold red]Lỗi Module 2:[/bold red] {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Module 2: Nhận dạng giọng nói Trung Quốc (Tối ưu VRAM)")
    parser.add_argument("--audio_in", required=True, help="File vocal sạch")
    parser.add_argument("--output_dir", required=True, help="Thư mục xuất SRT")
    parser.add_argument("--batch_size", type=int, default=4, help="Batch size Whisper (auto-tuned)")
    parser.add_argument("--out_name", type=str, default="zh_output", help="Tên file đầu ra")
    parser.add_argument("--mode", type=str, default="normal", help="Chế độ xử lý")
    parser.add_argument("--video_in", type=str, help="Video đầu vào (dùng cho Phim Review)")
    parser.add_argument("--roi", type=str, help="Tọa độ ROI: x:y:w:h")
    parser.add_argument("--sim_thresh", type=float, default=0.85, help="Similarity threshold")
    parser.add_argument("--fps", type=float, default=2.0, help="Video FPS target for ROI")
    parser.add_argument("--min_dur", type=float, default=0.05, help="Min duration for block")
    
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    srt_out = os.path.join(args.output_dir, f"{args.out_name}.srt")
    
    try:
        run_asr(args.audio_in, srt_out, args.batch_size, args.mode, args.video_in, args.roi, args.sim_thresh, args.fps)
    except Exception as e:
        console.print(f"[bold red]Lỗi hệ thống:[/bold red] {str(e)}")

if __name__ == "__main__":
    main()
