import os
import re
import json
import asyncio
import argparse
import subprocess
import sys
import time
import base64
import io

# Fix encoding for Windows Console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment
import pysrt
import requests
import edge_tts
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeRemainingColumn

console = Console()

# --- Cấu hình song song ---
MAX_TTS_WORKERS = 6       # Số luồng TikTok TTS
MAX_ALIGN_WORKERS = 12    # Số luồng align audio (CPU-bound)

# --- TikTok TTS Implementation ---
def get_tiktok_session():
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TIKTOK_SESSION_ID="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

def tiktok_tts(text, voice, output_path):
    session_id = get_tiktok_session()
    if not session_id:
        return False, "Thiếu TIKTOK_SESSION_ID"

    url = "https://api16-normal-v6.tiktokv.com/media/api/text/speech/invoke/"
    headers = {
        "User-Agent": "com.zhiliaoapp.musically/2022600036 (Linux; U; Android 7.1.2; en_US; SM-G988N; Build/NRD90M;tt-ok/3.12.13.1)",
        "Cookie": f"sessionid={session_id}"
    }
    params = {
        "text_speaker": voice,
        "req_text": text,
        "speaker_map_type": 0,
        "aid": 1233
    }
    try:
        response = requests.post(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("message") == "success" and data.get("data"):
                v_str = data["data"]["v_str"]
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(v_str))
                return True, ""
            else:
                return False, data.get("status_msg", "Unknown Error")
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)

# --- Edge TTS Implementation ---
async def edge_tts_gen(text, voice, output_path):
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception:
        return False

async def edge_tts_batch(tasks_list, progress=None, task_id=None):
    """Chạy nhiều Edge TTS đồng thời qua asyncio.gather có giới hạn Semaphore 10."""
    sem = asyncio.Semaphore(10) # BỘ ĐẾM GIỚI HẠN 10 LUỒNG

    async def _single(text, voice, output_path):
        async with sem:
            success = await edge_tts_gen(text, voice, output_path)
            if progress and task_id is not None:
                progress.advance(task_id)
            return success
    
    coros = [_single(t, v, o) for t, v, o in tasks_list]
    return await asyncio.gather(*coros)

def get_audio_duration_fast(path):
    """TỐI ƯU: Đo duration bằng pydub in-process thay vì subprocess ffprobe.
    Nhanh hơn ~10x cho hàng ngàn files nhỏ."""
    try:
        audio = AudioSegment.from_file(path)
        dur_sec = len(audio) / 1000.0
        del audio
        return dur_sec
    except Exception:
        # Fallback: dùng file size estimation cho mp3
        try:
            size = os.path.getsize(path)
            # Rough estimate: 16kbps mp3 ≈ 2KB/sec
            return size / 2000.0
        except Exception:
            return 1.0

def get_audio_duration(ffprobe_cmd, path):
    """Legacy ffprobe-based duration (dùng cho file lớn hoặc format đặc biệt)."""
    try:
        cmd = [
            ffprobe_cmd, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return 1.0

# --- Audio Alignment ---
def align_audio(ffmpeg_cmd, ffprobe_cmd, input_audio, duration_target, output_wav, max_speed_ratio=1.25, cleanup_raw=True):
    """Align audio with speed adjustment.
    TỐI ƯU: Dùng pydub đo duration, xóa raw file ngay sau align."""
    # TỐI ƯU: Dùng pydub thay vì ffprobe subprocess
    current_dur = get_audio_duration_fast(input_audio)
    ratio = current_dur / max(0.1, duration_target)
    
    # Clip speed ratio
    if ratio < 0.5: ratio = 0.5
    if ratio > max_speed_ratio: ratio = max_speed_ratio
    
    # Standardize: 24kHz, 1ch, mono
    subprocess.run([
        ffmpeg_cmd, '-y', '-i', input_audio,
        '-filter:a', f'atempo={ratio}',
        '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le',
        '-loglevel', 'error',
        output_wav
    ], capture_output=True)
    
    # TỐI ƯU: Xóa raw file ngay sau align để giải phóng SSD
    if cleanup_raw and os.path.exists(input_audio) and input_audio != output_wav:
        try:
            os.remove(input_audio)
        except Exception:
            pass
    
    return output_wav

def main():
    parser = argparse.ArgumentParser(description="Module 4: Professional TTS Dubbing Pipeline (Tối ưu I/O)")
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--tts_out", required=True)
    parser.add_argument("--speaker_mapping", help="JSON mapping")
    parser.add_argument("--speed_rate", default="1.0", help="Tốc độ đọc cơ bản")
    parser.add_argument("--max_speed_ratio", default="1.25", help="Tốc độ tối đa")
    parser.add_argument("--ffmpeg_path", default="ffmpeg", help="Đường dẫn ffmpeg")
    parser.add_argument("--keep_segments", action="store_true", help="Giữ lại temp/aligned_*.wav")
    
    args = parser.parse_args()
    speed_rate = float(args.speed_rate)
    max_speed_ratio = float(args.max_speed_ratio)
    ffmpeg_cmd = args.ffmpeg_path
    ffprobe_cmd = ffmpeg_cmd.replace("ffmpeg.exe", "ffprobe.exe") if "ffmpeg.exe" in ffmpeg_cmd else "ffprobe"

    # THÊM 3 DÒNG SAU ĐỂ TRÁNH LỖI TRÊN MÁY KHÁC (Pydub FFmpeg mapping):
    AudioSegment.converter = ffmpeg_cmd
    from pydub.utils import get_prober_name
    AudioSegment.ffprobe = ffprobe_cmd

    mapping = {}
    if args.speaker_mapping:
        mapping = json.loads(args.speaker_mapping)
    
    subs = pysrt.open(args.srt_vi_in, encoding='utf-8-sig')
    subs = sorted(subs, key=lambda s: s.start.ordinal)
    os.makedirs("temp", exist_ok=True)
    
    last_sub_end = subs[-1].end.ordinal if subs else 0
    canvas_duration_ms = last_sub_end + 3000
    skip_full_audio = canvas_duration_ms > 15 * 60 * 1000 # > 15 mins skip mixing

    t_start = time.time()
    console.print(f"[bold cyan]BAT DAU DU AN LONG TIENG: {len(subs)} cau thoai[/bold cyan]")

    all_tasks = []
    for i, sub in enumerate(subs):
        match = re.match(r"\[(SPEAKER_\d+)\] (.*)", sub.text)
        spk_id, content = (match.group(1), match.group(2)) if match else ("SPEAKER_00", sub.text)
        cfg = mapping.get(spk_id, {"engine": "tiktok", "voice": "vi_vn_002"})
        all_tasks.append({
            "idx": i, "sub": sub, "engine": cfg.get("engine", "tiktok"),
            "voice": cfg.get("voice", "vi_vn_002"), "content": content,
            "raw_path": f"temp/raw_{i}.mp3", "aligned_path": f"temp/aligned_{i}.wav"
        })

    # --- PHASE 1: GENERATE RAW AUDIO ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        main_task_id = progress.add_task("Dang tao giong doc (TTS)...", total=len(subs))
        
        tiktok_queue = [t for t in all_tasks if t["engine"] == "tiktok"]
        edge_queue = [t for t in all_tasks if t["engine"] != "tiktok"]
        fallback_tasks = []
        gen_results = {}

        if tiktok_queue:
            with ThreadPoolExecutor(max_workers=MAX_TTS_WORKERS) as pool:
                futures = {pool.submit(tiktok_tts, t["content"], t["voice"], t["raw_path"]): t for t in tiktok_queue}
                for f in as_completed(futures):
                    t = futures[f]
                    success, err = f.result()
                    if success:
                        gen_results[t["idx"]] = True
                        progress.advance(main_task_id)
                    else:
                        fallback_voice = "vi-VN-NamMinhNeural" if t["voice"] == "vi_vn_001" else "vi-VN-HoaiMyNeural"
                        fallback_tasks.append((t["content"], fallback_voice, t["raw_path"], t["idx"]))

        # Edge & Fallback Generation (Batch)
        edge_batch_inputs = [(t["content"], t["voice"], t["raw_path"]) for t in edge_queue]
        edge_batch_inputs += [(c, v, p) for c, v, p, _ in fallback_tasks]
        
        if edge_batch_inputs:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            res = loop.run_until_complete(edge_tts_batch(edge_batch_inputs, progress, main_task_id))
            
            for t, ok in zip(edge_queue, res[:len(edge_queue)]):
                gen_results[t["idx"]] = ok
            for (_, _, _, idx), ok in zip(fallback_tasks, res[len(edge_queue):]):
                gen_results[idx] = ok

        # --- PHASE 2: ALIGN AUDIO ---
        align_task_id = progress.add_task("Dang khop nhip video (Align)...", total=len(subs))
        align_results = []

        with ThreadPoolExecutor(max_workers=MAX_ALIGN_WORKERS) as pool:
            futures = []
            for t in all_tasks:
                if gen_results.get(t["idx"]) and os.path.exists(t["raw_path"]) and os.path.getsize(t["raw_path"]) > 100:
                    target_sec = max(0.1, (t["sub"].end.ordinal - t["sub"].start.ordinal) / 1000.0 / speed_rate)
                    # TỐI ƯU: cleanup_raw=True → xóa raw_*.mp3 ngay sau align
                    futures.append(pool.submit(
                        align_audio, ffmpeg_cmd, ffprobe_cmd, 
                        t["raw_path"], target_sec, t["aligned_path"], 
                        max_speed_ratio, cleanup_raw=True
                    ))
                else:
                    futures.append(None)

            for i, f in enumerate(futures):
                sub = subs[i]
                if f:
                    try:
                        aligned_wav = f.result()
                        # TỐI ƯU: Dùng pydub đo duration thay vì ffprobe subprocess
                        actual_dur = get_audio_duration_fast(aligned_wav)
                        align_results.append((i, sub.start.ordinal, aligned_wav, int(actual_dur * 1000)))
                    except Exception:
                        align_results.append((i, sub.start.ordinal, None, sub.end.ordinal - sub.start.ordinal))
                else:
                    align_results.append((i, sub.start.ordinal, None, sub.end.ordinal - sub.start.ordinal))
                
                if i % 50 == 0 or i == len(subs) - 1:
                    console.print(f"[PROGRESS] Aligned {i+1}/{len(subs)} segments...")
                
                progress.advance(align_task_id)

    # --- PHASE 3: FINALIZE WITH FFmpeg CONCAT ---
    console.print("[cyan]Dang ket xuat am thanh cuoi cung (FFmpeg Concat)...[/cyan]")
    
    silence_60s = "temp/silence_60s.wav"
    subprocess.run([
        ffmpeg_cmd, '-y', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono', 
        '-t', '60', '-c:a', 'pcm_s16le', silence_60s
    ], capture_output=True)

    timing_data = []
    concat_list_path = "temp/concat_list.txt"
    current_timeline_ms = 0

    with open(concat_list_path, "w", encoding="utf-8") as f:
        for idx, pos_ms, aligned_path, duration_ms in sorted(align_results, key=lambda x: x[0]):
            gap_ms = pos_ms - current_timeline_ms
            if gap_ms > 0:
                f.write(f"file 'silence_60s.wav'\n")
                f.write(f"outpoint {gap_ms / 1000.0:.3f}\n")
                current_timeline_ms += gap_ms
            
            if aligned_path and os.path.exists(aligned_path):
                f.write(f"file '{os.path.basename(aligned_path)}'\n")
                # BỔ SUNG: Khóa cứng thời gian từng câu TTS
                f.write(f"outpoint {duration_ms / 1000.0:.3f}\n")
                current_timeline_ms += duration_ms
            else:
                dur_sec = (subs[idx].end.ordinal - subs[idx].start.ordinal) / 1000.0
                f.write(f"file 'silence_60s.wav'\n")
                f.write(f"outpoint {dur_sec:.3f}\n")
                current_timeline_ms += int(dur_sec * 1000)

            timing_data.append({
                "index": idx,
                "sub_start_ms": subs[idx].start.ordinal,
                "sub_end_ms": subs[idx].end.ordinal,
                "sub_duration_ms": subs[idx].end.ordinal - subs[idx].start.ordinal,
                "tts_duration_ms": duration_ms
            })

        f.write(f"file 'silence_60s.wav'\n")
        f.write(f"outpoint 3.0\n")

    subprocess.run([
        ffmpeg_cmd, '-y', '-f', 'concat', '-safe', '0', 
        '-i', concat_list_path, '-c:a', 'pcm_s16le', args.tts_out
    ], capture_output=True)
    
    timing_path = os.path.join(os.path.dirname(args.tts_out), "tts_timing.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing_data, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t_start
    console.print(f"[bold green]HOAN TAT TRONG {elapsed:.1f}S![/bold green]")
    if skip_full_audio:
        console.print("[yellow]Video dai: Da bo qua tron am thanh de tiet kiem RAM.[/yellow]")

    if not args.keep_segments:
        import shutil
        shutil.rmtree("temp", ignore_errors=True)

if __name__ == "__main__":
    main()
