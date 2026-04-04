from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
import shutil
import subprocess
import sys
import time
import io
import argparse
import pysrt
from rich.console import Console

# Force UTF-8 for console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except:
        pass

console = Console()

def get_video_info(ffprobe_cmd, video_path):
    """Lấy duration (ms) và fps của video."""
    try:
        cmd = [
            ffprobe_cmd, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'format=duration:stream=r_frame_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        
        fps_val = 30.0
        duration_val = 0
        
        if len(lines) >= 1:
            fps_raw = lines[0]
            if '/' in fps_raw:
                a, b = fps_raw.split('/')
                fps_val = float(a) / float(b)
            else:
                fps_val = float(fps_raw)
        
        if len(lines) >= 2:
            duration_val = int(float(lines[1]) * 1000)
                
        return duration_val, fps_val
    except Exception as e:
        console.print(f"  Loi ffprobe: {e}")
        return 0, 30.0

def check_gpu(ffmpeg_cmd):
    """Kiểm tra GPU NVENC."""
    try:
        test = subprocess.run([ffmpeg_cmd, '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in test.stdout
    except Exception:
        return False

def check_hwaccel_cuda(ffmpeg_cmd):
    """Kiểm tra HW Accel CUDA decoder có sẵn."""
    # Vô hiệu hóa hwaccel cuda để tránh lỗi CUDA_ERROR_MAP_FAILED trên VRAM thấp (4GB)
    return False

def sanitize_timing(timing_data):
    """Sửa lỗi chồng lấn timing giữa các phân đoạn."""
    if not timing_data:
        return []
        
    sanitized = []
    sorted_data = sorted(timing_data, key=lambda x: x["sub_start_ms"])
    
    for i, item in enumerate(sorted_data):
        if i > 0:
            prev_end = sanitized[-1]["sub_end_ms"]
            if item["sub_start_ms"] < prev_end:
                item["sub_start_ms"] = prev_end
                if item["sub_end_ms"] <= item["sub_start_ms"]:
                    item["sub_end_ms"] = item["sub_start_ms"] + 10 
                item["sub_duration_ms"] = item["sub_end_ms"] - item["sub_start_ms"]
        sanitized.append(item)
    return sanitized

def pre_merge_vocals(aligned_dir, timing_data, new_segments, output_wav, ffmpeg_cmd):
    """TỐI ƯU: Pre-merge tất cả vocal segments thành 1 file WAV theo timeline.
    Dùng FFmpeg concat filter thay vì load Pydub vào RAM.
    Giảm số input files cho mỗi chunk từ hàng chục → 1."""
    
    sub_map = {s["index"]: s for s in new_segments if s["type"] == "sub"}
    
    # Tạo concat list cho ffmpeg
    concat_list = os.path.join(os.path.dirname(output_wav), "_vocal_concat.txt")
    silence_file = os.path.join(os.path.dirname(output_wav), "_silence_10s.wav")
    
    # Tạo file silence 10s chuẩn
    subprocess.run([
        ffmpeg_cmd, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono',
        '-t', '10', '-c:a', 'pcm_s16le', '-loglevel', 'error', silence_file
    ], capture_output=True)
    
    with open(concat_list, "w", encoding="utf-8") as f:
        current_ms = 0
        for seg in new_segments:
            if seg["type"] == "sub":
                idx = seg["index"]
                wav_p = os.path.join(aligned_dir, f"aligned_{idx}.wav")
                
                # Khoảng lặng trước segment
                gap_ms = seg["new_start"] - current_ms
                if gap_ms > 0:
                    f.write(f"file '{os.path.abspath(silence_file)}'\n")
                    f.write(f"outpoint {gap_ms / 1000.0:.3f}\n")
                    current_ms += gap_ms
                
                if os.path.exists(wav_p):
                    f.write(f"file '{os.path.abspath(wav_p)}'\n")
                    current_ms += seg["new_dur"]
                else:
                    # Silence thay thế
                    dur_sec = seg["new_dur"] / 1000.0
                    f.write(f"file '{os.path.abspath(silence_file)}'\n")
                    f.write(f"outpoint {dur_sec:.3f}\n")
                    current_ms += seg["new_dur"]
            elif seg["type"] == "gap":
                gap_ms = seg["new_dur"]
                if gap_ms > 0:
                    f.write(f"file '{os.path.abspath(silence_file)}'\n")
                    f.write(f"outpoint {gap_ms / 1000.0:.3f}\n")
                    current_ms += gap_ms
    
    # Merge bằng FFmpeg concat
    subprocess.run([
        ffmpeg_cmd, '-y', '-f', 'concat', '-safe', '0',
        '-i', concat_list, '-c:a', 'pcm_s16le',
        '-loglevel', 'error', output_wav
    ], capture_output=True)
    
    # Cleanup
    for f in [concat_list, silence_file]:
        if os.path.exists(f):
            os.remove(f)
    
    return os.path.exists(output_wav)

def get_optimal_chunk_size(total_segments, video_dur_ms):
    """TỐI ƯU: Auto-tune chunk_size dựa theo độ dài video."""
    hours = video_dur_ms / 3600000.0
    if hours > 4:
        return 30    # Video cực dài → chunk nhỏ
    elif hours > 2:
        return 50    # Video dài
    elif hours > 1:
        return 100   # Video trung bình
    else:
        return 200   # Video ngắn

def run_ffmpeg_chunk(ffmpeg_cmd, cmd_inputs, filter_content, output_ts, use_gpu, has_cuda_dec, fps):
    """Chạy FFmpeg cho một chunk.
    TỐI ƯU SIÊU TỐC VÀ DỌN RÁC RAM/VRAM:
    - Mỗi segment video là một input độc lập (-ss) loại bỏ hoàn toàn bộ đệm RAM của filter split!
    - Thêm HW decoder nếu có.
    """
    
    if use_gpu and has_cuda_dec:
        hw_args = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
    else:
        hw_args = []
    
    encoder = "h264_nvenc" if use_gpu else "libx264"
    preset = "p4" if use_gpu else "fast"
    
    filter_path = output_ts + ".filter.txt"
    with open(filter_path, "w", encoding="utf-8") as f:
        f.write(filter_content)
        
    cmd = [ffmpeg_cmd, '-y', '-loglevel', 'error'] + hw_args
    # Add all inputs natively (each segment as input)
    cmd += cmd_inputs
    
    cmd += ['-filter_complex_script', filter_path]
    cmd += ['-map', '[outv]', '-map', '[outa]', '-map', '[v_vol2]', '-map', '[b_vol2]']
        
    cmd += ['-c:v', encoder, '-preset', preset, '-r', f'{fps:.2f}']
    cmd += ['-c:a', 'aac', '-b:a', '128k'] 
    cmd += ['-f', 'mpegts', output_ts]
    
    try:
        subprocess.run(cmd, check=True)
        if os.path.exists(filter_path):
            os.remove(filter_path)
        return True
    except Exception as e:
        console.print(f"  Loi FFmpeg chunk {output_ts}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Module 7: Dong bo Video (Tối ưu RAM/VRAM/SSD)")
    parser.add_argument("--video_in", required=True)
    parser.add_argument("--timing_json", required=True)
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--aligned_dir", default="temp")
    parser.add_argument("--bgm_in", help="File nhac nen")
    parser.add_argument("--vocal_out", help="Duong dan luu VOCAL dong bo")
    parser.add_argument("--bgm_out", help="Duong dan luu BGM dong bo")
    parser.add_argument("--video_out", required=True)
    parser.add_argument("--audio_out", help="Duong dan luu Full Audio")
    parser.add_argument("--srt_out", required=True)
    parser.add_argument("--ffmpeg_path", default="ffmpeg")
    parser.add_argument("--chunk_size", type=int, default=0, help="0 = auto-tune")
    parser.add_argument("--vocal_vol", type=float, default=1.0)
    parser.add_argument("--bgm_vol", type=float, default=1.0)

    args = parser.parse_args()
    ffmpeg_cmd = args.ffmpeg_path
    ffprobe_cmd = ffmpeg_cmd.replace("ffmpeg.exe", "ffprobe.exe") if "ffmpeg.exe" in ffmpeg_cmd else "ffprobe"

    t_start = time.time()
    use_gpu = check_gpu(ffmpeg_cmd)
    has_cuda_dec = check_hwaccel_cuda(ffmpeg_cmd)
    
    if use_gpu and has_cuda_dec:
        console.print("[bold green]✅ Full GPU Pipeline: CUDA Decode + NVENC Encode[/bold green]")
    elif use_gpu:
        console.print("[bold yellow]⚡ GPU Encode Only (NVENC)[/bold yellow]")

    # 1. Thong tin Video
    video_dur_ms, fps = get_video_info(ffprobe_cmd, args.video_in)
    if video_dur_ms <= 0:
        console.print("  Loi doc video!")
        return

    # 2. Doc va lam sach timing
    timing_data = []
    if os.path.exists(args.timing_json):
        with open(args.timing_json, "r", encoding="utf-8") as f:
            timing_data = json.load(f)
            timing_data = sanitize_timing(timing_data)
    else:
        console.print(f"  Canh bao: Khong tim thay {args.timing_json}.")
        return

    # 3. Tinh toan Timeline Shifting
    new_segments = []
    current_new_time_ms = 0
    prev_orig_end_ms = 0

    for item in timing_data:
        orig_start = item["sub_start_ms"]
        orig_end = item["sub_end_ms"]
        tts_dur = item["tts_duration_ms"]
        orig_dur = item["sub_duration_ms"]

        if orig_start > prev_orig_end_ms:
            gap_dur = orig_start - prev_orig_end_ms
            new_segments.append({
                "type": "gap", "start": prev_orig_end_ms, "end": orig_start,
                "dur": gap_dur, "new_dur": gap_dur, "new_start": current_new_time_ms
            })
            current_new_time_ms += gap_dur

        target_dur = max(orig_dur, tts_dur)
        new_segments.append({
            "type": "sub", "index": item["index"], "start": orig_start, "end": orig_end,
            "dur": orig_dur, "new_dur": target_dur, "new_start": current_new_time_ms
        })
        current_new_time_ms += target_dur
        prev_orig_end_ms = orig_end

    if prev_orig_end_ms < video_dur_ms:
        gap_dur = video_dur_ms - prev_orig_end_ms
        new_segments.append({
            "type": "gap", "start": prev_orig_end_ms, "end": video_dur_ms,
            "dur": gap_dur, "new_dur": gap_dur, "new_start": current_new_time_ms
        })
        current_new_time_ms += gap_dur

    # TỐI ƯU: Pre-merge vocals thành 1 file
    console.print("[cyan]--- Pre-merge vocals thành 1 file (Tiết kiệm RAM) ---[/cyan]")
    vocal_merged = os.path.join(os.path.dirname(args.video_out), "_vocal_merged.wav")
    pre_merge_vocals(args.aligned_dir, timing_data, new_segments, vocal_merged, ffmpeg_cmd)
    has_vocal = os.path.exists(vocal_merged)

    # TỐI ƯU: Auto-tune chunk_size
    chunk_size = args.chunk_size if args.chunk_size > 0 else get_optimal_chunk_size(len(new_segments), video_dur_ms)
    
    # 4. Xu ly theo cum (Chunks)
    console.print(f"--- DANG QUY TRINH CHUNK-BASED SYNC ({len(new_segments)} segments, chunk={chunk_size}) ---")
    chunk_files = []
    # Luôn dọn dẹp thư mục chunks trước khi chạy để tránh nối nhầm file cũ lỗi
    shutil.rmtree("chunks", ignore_errors=True)
    os.makedirs("chunks", exist_ok=True)
    
    has_bgm = args.bgm_in and os.path.exists(args.bgm_in)
    
    num_chunks = (len(new_segments) + chunk_size - 1) // chunk_size
    
    for c_idx in range(num_chunks):
        start_idx = c_idx * chunk_size
        end_idx = min(start_idx + chunk_size, len(new_segments))
        chunk_segs = new_segments[start_idx:end_idx]
        
        chunk_ts = f"chunks/chunk_{c_idx:04d}.ts"
        chunk_files.append(chunk_ts)
        
        if os.path.exists(chunk_ts) and os.path.getsize(chunk_ts) > 1000:
            continue 

        filter_lines = []
        cv_in = ""
        ca_bgm_in = ""
        ca_voc_in = ""
        
        chunk_min_start = min(seg["start"] for seg in chunk_segs) / 1000.0
        vocal_seek = chunk_segs[0]["new_start"] / 1000.0

        cmd_inputs = []
        
        for i, seg in enumerate(chunk_segs):
            s_sec = seg["start"] / 1000.0
            
            eff_dur_ms = max(10, seg["dur"])
            eff_new_dur_ms = max(10, seg["new_dur"])
            dur_sec = eff_dur_ms / 1000.0
            
            # Khởi tạo mỗi Video Segment = 1 input để ngăn ffmpeg đệm (buffer leak) toàn bộ RAM
            cmd_inputs.extend(['-ss', f"{s_sec:.3f}"])
            cmd_inputs.extend(['-t', f"{dur_sec:.3f}"])
            cmd_inputs.extend(['-i', args.video_in])
            
            slow_factor = eff_new_dur_ms / eff_dur_ms
            filter_lines.append(f"[{i}:v]setpts={slow_factor:.6f}*(PTS-STARTPTS)[v{i}];")
            cv_in += f"[v{i}]"
            
        next_in_idx = len(chunk_segs)
        bgm_input_idx = -1
        voc_input_idx = -1
        
        if has_bgm:
            bgm_input_idx = next_in_idx
            cmd_inputs.extend(['-ss', f"{chunk_min_start:.3f}", '-i', args.bgm_in])
            next_in_idx += 1
            
        if has_vocal:
            voc_input_idx = next_in_idx
            cmd_inputs.extend(['-ss', f"{vocal_seek:.3f}", '-i', vocal_merged])
            next_in_idx += 1

        for i, seg in enumerate(chunk_segs):
            s_sec = seg["start"] / 1000.0
            eff_dur_ms = max(10, seg["dur"])
            eff_new_dur_ms = max(10, seg["new_dur"])
            
            dur_sec = eff_dur_ms / 1000.0
            rel_s = max(0, s_sec - chunk_min_start)
            rel_e = rel_s + dur_sec
            
            slow_factor = eff_new_dur_ms / eff_dur_ms
            
            # BGM
            if has_bgm:
                speed = 1.0 / slow_factor
                if eff_dur_ms < 100 or speed < 0.2:
                    target_d = eff_new_dur_ms / 1000.0
                    filter_lines.append(f"[{bgm_input_idx}:a]asetpts=PTS-STARTPTS,atrim=start={rel_s:.3f}:end={rel_e:.3f},asetpts=PTS-STARTPTS,apad,atrim=0:{target_d:.3f}[abgm{i}];")
                else:
                    tspeed = speed
                    atempo_str = ""
                    while tspeed < 0.5: atempo_str += "atempo=0.5,"; tspeed /= 0.5
                    while tspeed > 2.0: atempo_str += "atempo=2.0,"; tspeed /= 2.0
                    atempo_str += f"atempo={tspeed:.6f}"
                    filter_lines.append(f"[{bgm_input_idx}:a]asetpts=PTS-STARTPTS,atrim=start={rel_s:.3f}:end={rel_e:.3f},asetpts=PTS-STARTPTS,{atempo_str}[abgm{i}];")
            else:
                target_d = eff_new_dur_ms / 1000.0
                filter_lines.append(f"aevalsrc=0:d={target_d:.3f}[abgm{i}];")
            ca_bgm_in += f"[abgm{i}]"

            # Vocals
            if has_vocal and voc_input_idx >= 0:
                voc_rel_start = max(0.0, (seg["new_start"] / 1000.0) - vocal_seek)
                voc_rel_end = voc_rel_start + (eff_new_dur_ms / 1000.0)
                filter_lines.append(f"[{voc_input_idx}:a]asetpts=PTS-STARTPTS,atrim=start={voc_rel_start:.3f}:end={voc_rel_end:.3f},asetpts=PTS-STARTPTS[avoc{i}];")
            else:
                target_d = eff_new_dur_ms / 1000.0
                filter_lines.append(f"aevalsrc=0:d={target_d:.3f}[avoc{i}];")
            ca_voc_in += f"[avoc{i}]"
        
        filter_lines.append(f"{cv_in}concat=n={len(chunk_segs)}:v=1:a=0[outv];")
        filter_lines.append(f"{ca_bgm_in}concat=n={len(chunk_segs)}:v=0:a=1[abgm_final];")
        filter_lines.append(f"{ca_voc_in}concat=n={len(chunk_segs)}:v=0:a=1[avoc_final];")
        
        filter_lines.append(f"[avoc_final]volume={args.vocal_vol}[v_vol];")
        filter_lines.append(f"[abgm_final]volume={args.bgm_vol}[b_vol];")
        filter_lines.append(f"[v_vol]asplit[v_vol1][v_vol2];")
        filter_lines.append(f"[b_vol]asplit[b_vol1][b_vol2];")
        filter_lines.append(f"[v_vol1][b_vol1]amix=inputs=2:duration=first[outa]")
            
        console.print(f"  > Render cum {c_idx+1}/{num_chunks} (Tối ưu Zero-Buffer: {len(chunk_segs)} video inputs)...")
        run_ffmpeg_chunk(
            ffmpeg_cmd, cmd_inputs, "\n".join(filter_lines),
            chunk_ts, use_gpu, has_cuda_dec, fps
        )

    # 5. Ghep noi cac cum
    console.print("--- Dang ghep noi cac cum video ---")
    concat_list_path = "chunks_list.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for cf in chunk_files:
            f.write(f"file '{cf}'\n")
            
    cmd_final = [ffmpeg_cmd, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', concat_list_path]
    if has_bgm:
        cmd_final += ['-c', 'copy', '-map', '0:v', '-map', '0:a', args.video_out]
    else:
        cmd_final += ['-c', 'copy', '-map', '0:v', args.video_out]
        
    try:
        subprocess.run(cmd_final, check=True)
    except Exception as e:
        console.print(f"  Loi ghep noi cuoi cung: {e}")
        sys.exit(1)

    # 6. Trich xuat Audio dong bo
    if args.audio_out:
        console.print("--- Dang trich xuat Audio dong bo ---")
        cmd_ext_audio = [ffmpeg_cmd, '-y', '-loglevel', 'error', '-i', args.video_out, '-vn', '-map', '0:a:0', '-c:a', 'pcm_s16le', args.audio_out]
        subprocess.run(cmd_ext_audio)
    
    if args.vocal_out:
        console.print(f"--- Dang trich xuat Vocal dong bo: {args.vocal_out} ---")
        cmd_v = [ffmpeg_cmd, '-y', '-loglevel', 'error', '-i', args.video_out, '-vn', '-map', '0:a:1', '-c:a', 'pcm_s16le', args.vocal_out]
        subprocess.run(cmd_v)
        
    if args.bgm_out:
        console.print(f"--- Dang trich xuat BGM dong bo: {args.bgm_out} ---")
        cmd_b = [ffmpeg_cmd, '-y', '-loglevel', 'error', '-i', args.video_out, '-vn', '-map', '0:a:2', '-c:a', 'pcm_s16le', args.bgm_out]
        subprocess.run(cmd_b)

    # 7. Xuat SRT
    if os.path.exists(args.srt_vi_in):
        subs = pysrt.open(args.srt_vi_in, encoding='utf-8')
        new_subs = pysrt.SubRipFile()
        sub_map = {s["index"]: s for s in new_segments if s["type"] == "sub"}
        
        console.print(f"--- Dang xuat file phu de CapCut ---")
        
        for i, sub in enumerate(subs):
            if i in sub_map:
                s_info = sub_map[i]
                
                # Update SRT
                new_subs.append(pysrt.SubRipItem(
                    index=i+1,
                    start=pysrt.SubRipTime(milliseconds=s_info["new_start"]),
                    end=pysrt.SubRipTime(milliseconds=s_info["new_start"] + s_info["new_dur"]),
                    text=sub.text
                ))
                
        new_subs.save(args.srt_out, encoding='utf-8')

    # Cleanup
    console.print("--- Dang don dep ---")
    # TỐI ƯU: Xóa chunks ngay
    shutil.rmtree("chunks", ignore_errors=True)
    if os.path.exists(concat_list_path): os.remove(concat_list_path)
    if os.path.exists(vocal_merged): os.remove(vocal_merged)
    
    elapsed = time.time() - t_start
    console.print(f"HOAN TAT CHUNK SYNC TRONG {elapsed:.1f}s!")

if __name__ == "__main__":
    main()
