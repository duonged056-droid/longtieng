import os
import json
import argparse
import subprocess
import sys
import time
import shutil
from pydub import AudioSegment
import pysrt
from rich.console import Console

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
        fps_raw = lines[0]
        if '/' in fps_raw:
            a, b = fps_raw.split('/')
            fps = float(a) / float(b)
        else:
            fps = float(fps_raw)
        duration = int(float(lines[1]) * 1000)
        return duration, fps
    except Exception as e:
        console.print(f"[yellow]⚠️ Lỗi ffprobe: {e}[/yellow]")
        return 0, 30.0

def check_gpu(ffmpeg_cmd):
    """Kiểm tra GPU NVENC."""
    try:
        test = subprocess.run([ffmpeg_cmd, '-encoders'], capture_output=True, text=True)
        return 'h264_nvenc' in test.stdout
    except Exception:
        return False

def main():
    parser = argparse.ArgumentParser(description="Module 7: Đồng bộ Video — Perfect Frame-Accurate Sync")
    parser.add_argument("--video_in", required=True)
    parser.add_argument("--timing_json", required=True)
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--aligned_dir", default="temp", help="Thư mục chứa aligned_*.wav")
    parser.add_argument("--video_out", required=True)
    parser.add_argument("--audio_out", required=True)
    parser.add_argument("--srt_out", required=True)
    parser.add_argument("--ffmpeg_path", default="ffmpeg")

    args = parser.parse_args()
    ffmpeg_cmd = args.ffmpeg_path
    ffprobe_cmd = ffmpeg_cmd.replace("ffmpeg.exe", "ffprobe.exe") if sys.platform == "win32" and "ffmpeg.exe" in ffmpeg_cmd else "ffprobe"

    t_start = time.time()

    # 1. Lấy thông tin video
    video_dur_ms, fps = get_video_info(ffprobe_cmd, args.video_in)
    if video_dur_ms <= 0:
        console.print("[red]❌ Lỗi đọc video![/red]")
        return

    # 2. Đọc timing
    with open(args.timing_json, "r", encoding="utf-8") as f:
        timing_data = json.load(f)

    # 3. Tính toán Timeline Shifting
    new_segments = []
    current_new_time_ms = 0
    prev_orig_end_ms = 0

    for item in timing_data:
        orig_start = item["sub_start_ms"]
        orig_end = item["sub_end_ms"]
        tts_dur = item["tts_duration_ms"]
        orig_dur = item["sub_duration_ms"]

        # Gap
        if orig_start > prev_orig_end_ms:
            gap_dur = orig_start - prev_orig_end_ms
            new_segments.append({
                "type": "gap", "start": prev_orig_end_ms, "end": orig_start,
                "dur": gap_dur, "new_dur": gap_dur, "new_start": current_new_time_ms
            })
            current_new_time_ms += gap_dur

        # Sub
        target_dur = max(orig_dur, tts_dur)
        new_segments.append({
            "type": "sub", "index": item["index"], "start": orig_start, "end": orig_end,
            "dur": orig_dur, "new_dur": target_dur, "new_start": current_new_time_ms
        })
        current_new_time_ms += target_dur
        prev_orig_end_ms = orig_end

    # Đoạn cuối
    if prev_orig_end_ms < video_dur_ms:
        gap_dur = video_dur_ms - prev_orig_end_ms
        new_segments.append({
            "type": "gap", "start": prev_orig_end_ms, "end": video_dur_ms,
            "dur": gap_dur, "new_dur": gap_dur, "new_start": current_new_time_ms
        })
        current_new_time_ms += gap_dur

    # 4. Xây dựng Filtergraph Script (CỰC KỲ QUAN TRỌNG ĐỂ KHỚP HÌNH/TIẾNG)
    # Chúng ta dùng trim và setpts để kéo dãn từng đoạn ngay trong 1 lệnh duy nhất
    filter_script_path = "sync_filter.txt"
    filter_lines = []
    concat_inputs = ""
    
    for i, seg in enumerate(new_segments):
        s_sec = seg["start"] / 1000.0
        e_sec = (seg["start"] + seg["dur"]) / 1000.0
        slow_factor = seg["new_dur"] / seg["dur"] if seg["dur"] > 0 else 1.0
        
        # Trim đoạn video gốc
        # Dùng setpts=PTS-STARTPTS để reset thời gian về 0 cho mỗi đoạn trước khi slow
        # Sau đó slow bằng slow_factor
        filter_lines.append(f"[0:v]trim=start={s_sec:.3f}:end={e_sec:.3f},setpts={slow_factor:.6f}*(PTS-STARTPTS)[v{i}];")
        concat_inputs += f"[v{i}]"

    # Nối tất cả lại
    filter_lines.append(f"{concat_inputs}concat=n={len(new_segments)}:v=1:a=0[outv]")
    
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write("".join(filter_lines))

    # 5. Chạy FFmpeg với filter script
    console.print(f"[bold cyan]⚡ ĐANG ĐỒNG BỘ PERFECT SYNC (Frame-Accurate)...[/bold cyan]")
    use_gpu = check_gpu(ffmpeg_cmd)
    encoder = "h264_nvenc" if use_gpu else "libx264"
    preset = "p4" if use_gpu else "fast"
    
    cmd = [
        ffmpeg_cmd, '-y',
        '-i', args.video_in,
        '-filter_complex_script', filter_script_path,
        '-map', '[outv]',
        '-c:v', encoder, '-preset', preset,
        '-r', f'{fps:.2f}', # Giữ nguyên FPS chuẩn
        '-loglevel', 'error',
        args.video_out
    ]

    try:
        subprocess.run(cmd, check=True)
    except Exception as e:
        console.print(f"[red]❌ Lỗi FFmpeg Filtergraph: {e}[/red]")
        # Gỡ filter script nếu lỗi
        if os.path.exists(filter_script_path): os.remove(filter_script_path)
        return

    # 6. Rebuild Audio: Đây là chìa khóa để khớp tiếng
    console.print("[cyan]🎵 Đang rebuild audio khớp timeline mới...[/cyan]")
    full_audio = AudioSegment.silent(duration=current_new_time_ms + 1000)
    for seg in new_segments:
        if seg["type"] == "sub":
            wav_p = os.path.join(args.aligned_dir, f"aligned_{seg['index']}.wav")
            if os.path.exists(wav_p):
                full_audio = full_audio.overlay(AudioSegment.from_file(wav_p), position=seg["new_start"])
    full_audio[:current_new_time_ms].export(args.audio_out, format="wav")

    # 7. Xuất SRT đồng bộ
    console.print("[cyan]📝 Đang xuất SRT đồng bộ...[/cyan]")
    subs = pysrt.open(args.srt_vi_in, encoding='utf-8')
    new_subs = pysrt.SubRipFile()
    sub_map = {s["index"]: s for s in new_segments if s["type"] == "sub"}
    for i, sub in enumerate(subs):
        if i in sub_map:
            s_info = sub_map[i]
            new_subs.append(pysrt.SubRipItem(
                index=i+1,
                start=pysrt.SubRipTime(milliseconds=s_info["new_start"]),
                end=pysrt.SubRipTime(milliseconds=s_info["new_start"] + s_info["new_dur"]),
                text=sub.text
            ))
    new_subs.save(args.srt_out, encoding='utf-8')

    # Cleanup
    if os.path.exists(filter_script_path): os.remove(filter_script_path)
    shutil.rmtree("temp", ignore_errors=True)

    elapsed = time.time() - t_start
    console.print(f"[bold green]✨ HOÀN TẤT PERFECT SYNC! ({elapsed:.1f}s)[/bold green]")

if __name__ == "__main__":
    main()
