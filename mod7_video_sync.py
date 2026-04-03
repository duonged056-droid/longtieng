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
    parser.add_argument("--bgm_in", help="File nhạc nền (không lời) để đồng bộ")
    parser.add_argument("--bgm_out", help="Đường dẫn lưu file nhạc nền đã đồng bộ")
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

    # 4. Xây dựng Filtergraph Script (Video & Audio Stretching)
    filter_script_path = "sync_filter.txt"
    filter_lines = []
    concat_v_inputs = ""
    concat_a_inputs = ""
    
    # Nếu có BGM, ta sẽ xử lý cả audio trong filtergraph
    has_bgm = args.bgm_in and os.path.exists(args.bgm_in)
    input_bgm = f'-i "{args.bgm_in}" ' if has_bgm else ""
    
    for i, seg in enumerate(new_segments):
        s_sec = seg["start"] / 1000.0
        e_sec = (seg["start"] + seg["dur"]) / 1000.0
        slow_factor = seg["new_dur"] / seg["dur"] if seg["dur"] > 0 else 1.0
        
        # 1. Video Filter
        filter_lines.append(f"[0:v]trim=start={s_sec:.3f}:end={e_sec:.3f},setpts={slow_factor:.6f}*(PTS-STARTPTS)[v{i}];")
        concat_v_inputs += f"[v{i}]"
        
        # 2. Audio Filter (Nếu có BGM - Stretch BGM theo tỷ lệ video)
        if has_bgm:
            # Tốc độ âm thanh = 1 / slow_factor
            speed = 1.0 / slow_factor
            # FFmpeg atempo giới hạn [0.5, 2.0]. Nếu chậm hơn 0.5 (slow_factor > 2), phải xích nhiều atempo
            atempo_str = ""
            temp_speed = speed
            while temp_speed < 0.5:
                atempo_str += "atempo=0.5,"
                temp_speed /= 0.5
            while temp_speed > 2.0:
                atempo_str += "atempo=2.0,"
                temp_speed /= 2.0
            atempo_str += f"atempo={temp_speed:.6f}"
            
            filter_lines.append(f"[1:a]atrim=start={s_sec:.3f}:end={e_sec:.3f},asetpts=PTS-STARTPTS,{atempo_str}[a{i}];")
            concat_a_inputs += f"[a{i}]"

    # Kết hợp
    filter_lines.append(f"{concat_v_inputs}concat=n={len(new_segments)}:v=1:a=0[outv];")
    if has_bgm:
        filter_lines.append(f"{concat_a_inputs}concat=n={len(new_segments)}:v=0:a=1[outa]")
    
    with open(filter_script_path, "w", encoding="utf-8") as f:
        f.write("".join(filter_lines))

    # 5. Chạy FFmpeg
    console.print(f"[bold cyan]⚡ ĐANG ĐỒNG BỘ VIDEO & NHẠC NỀN (Smart Stretching - GPU)...[/bold cyan]")
    use_gpu = check_gpu(ffmpeg_cmd)
    
    hw_args = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"] if use_gpu else []
    encoder = "h264_nvenc" if use_gpu else "libx264"
    preset = "p4" if use_gpu else "fast"
    
    temp_bgm_wav = "temp_stretched_bgm.wav"
    
    cmd = [ffmpeg_cmd, '-y'] + hw_args + ['-i', args.video_in]
    if has_bgm:
        cmd += ['-i', args.bgm_in]
        
    cmd += [
        '-filter_complex_script', filter_script_path,
        '-map', '[outv]',
        '-c:v', encoder, '-preset', preset,
        '-r', f'{fps:.2f}',
        '-loglevel', 'error'
    ]
    
    if has_bgm:
        # Xuất audio stretched ra file tạm rồi mới overlay TTS
        cmd_v = cmd + [args.video_out]
        cmd_a = [
            ffmpeg_cmd, '-y',
            '-i', args.video_in, '-i', args.bgm_in,
            '-filter_complex_script', filter_script_path,
            '-map', '[outa]', '-loglevel', 'error', temp_bgm_wav
        ]
        try:
            subprocess.run(cmd_v, check=True)
            subprocess.run(cmd_a, check=True)
        except Exception as e:
            console.print(f"[red]❌ Lỗi FFmpeg: {e}[/red]")
            return
    else:
        cmd += [args.video_out]
        subprocess.run(cmd, check=True)

    # 6. Rebuild Audio: Đây là chìa khóa để khớp tiếng
    console.print("[cyan]🎵 Đang hòa trộn Lồng tiếng & Nhạc nền...[/cyan]")
    if has_bgm and os.path.exists(temp_bgm_wav):
        bgm_final_audio = AudioSegment.from_file(temp_bgm_wav)
        # Nếu yêu cầu xuất bgm_out riêng biệt
        if args.bgm_out:
            bgm_final_audio[:current_new_time_ms].export(args.bgm_out, format="wav")
            console.print(f"[green]✅ Đã xuất riêng Nhạc nền đồng bộ: {args.bgm_out}[/green]")
    else:
        bgm_final_audio = AudioSegment.silent(duration=current_new_time_ms + 1000)
    
    # Tạo track lồng tiếng riêng
    vocal_final_audio = AudioSegment.silent(duration=current_new_time_ms + 1000)
    for seg in new_segments:
        if seg["type"] == "sub":
            wav_p = os.path.join(args.aligned_dir, f"aligned_{seg['index']}.wav")
            if os.path.exists(wav_p):
                vocal_final_audio = vocal_final_audio.overlay(AudioSegment.from_file(wav_p), position=seg["new_start"])
    
    # Cắt chính xác theo thời gian mới
    vocal_out_audio = vocal_final_audio[:current_new_time_ms]
    vocal_out_audio.export(args.audio_out, format="wav")
    console.print(f"[green]✅ Đã xuất riêng Lồng tiếng đồng bộ: {args.audio_out}[/green]")

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
    if os.path.exists(temp_bgm_wav): os.remove(temp_bgm_wav)

    # Cleanup
    if os.path.exists(filter_script_path): os.remove(filter_script_path)
    shutil.rmtree("temp", ignore_errors=True)

    elapsed = time.time() - t_start
    console.print(f"[bold green]✨ HOÀN TẤT PERFECT SYNC! ({elapsed:.1f}s)[/bold green]")

if __name__ == "__main__":
    main()
