import os
import re
import json
import asyncio
import argparse
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pydub import AudioSegment
import pysrt
import requests
import edge_tts
from rich.console import Console
from tqdm import tqdm

console = Console()

# --- Cấu hình song song ---
MAX_TTS_WORKERS = 8       # Số luồng TTS chạy đồng thời
MAX_ALIGN_WORKERS = 6     # Số luồng align audio đồng thời

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
        console.print("[yellow]Thiếu TIKTOK_SESSION_ID trong .env. Vui lòng thiết lập trên giao diện![/yellow]")
        return False

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
        response = requests.post(url, params=params, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get("message") == "success" and data.get("data"):
                v_str = data["data"]["v_str"]
                import base64
                with open(output_path, "wb") as f:
                    f.write(base64.b64decode(v_str))
                return True
            else:
                console.print(f"[red]Lỗi API TikTok: {data.get('status_msg', 'Unknown Error')}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Lỗi kết nối TikTok TTS: {e}[/red]")
        return False

# --- Edge TTS Implementation ---
async def edge_tts_gen(text, voice, output_path):
    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return True
    except Exception as e:
        console.print(f"[red]Lỗi Edge TTS: {e}[/red]")
        return False

# --- Edge TTS Batch (tái sử dụng event loop) ---
async def edge_tts_batch(tasks_list):
    """Chạy nhiều Edge TTS đồng thời qua asyncio.gather."""
    async def _single(text, voice, output_path):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            return True
        except Exception as e:
            return False
    
    coros = [_single(t, v, o) for t, v, o in tasks_list]
    return await asyncio.gather(*coros)

# --- Audio Alignment (Sync) - Tối ưu ---
# Giới hạn tốc độ đọc tối đa (1.25 = chỉ nhanh hơn gốc 25%, chấp nhận dè 1 chút)
DEFAULT_MAX_SPEED_RATIO = 1.25

def align_audio(ffmpeg_cmd, ffprobe_cmd, input_audio, duration_target, output_wav, max_speed_ratio=DEFAULT_MAX_SPEED_RATIO):
    """Sử dụng atempo để khớp thời gian. Giới hạn tốc độ tối đa để không đọc quá nhanh.
    KHÔNG cắt audio - đọc đủ câu, chấp nhận dè/overlap nhẹ."""
    try:
        # Dùng pydub để lấy duration nhanh hơn subprocess ffprobe
        seg = AudioSegment.from_file(input_audio)
        current_dur = len(seg) / 1000.0
        if current_dur <= 0:
            current_dur = 1.0
    except Exception:
        try:
            probe = subprocess.run([
                ffprobe_cmd, '-v', 'error', '-show_entries', 'format=duration', 
                '-of', 'default=noprint_wrappers=1:nokey=1', input_audio
            ], capture_output=True, text=True, check=True).stdout.strip()
            current_dur = float(probe) if probe else 1.0
        except Exception:
            current_dur = 1.0

    ratio = current_dur / duration_target
    
    # Giới hạn: không cho đọc nhanh hơn max_speed_ratio lần
    if ratio < 0.5:
        ratio = 0.5
    if ratio > max_speed_ratio:
        ratio = max_speed_ratio  # Giới hạn tốc độ, audio sẽ dài hơn slot nhưng ĐỌC ĐỦ CÂU
    
    subprocess.run([
        ffmpeg_cmd, '-y', '-i', input_audio,
        '-filter:a', f'atempo={ratio}',
        '-loglevel', 'error',
        output_wav
    ], capture_output=True)


def _process_single_sub(i, sub, subs, mapping, speed_rate, ffmpeg_cmd, ffprobe_cmd, max_speed_ratio=DEFAULT_MAX_SPEED_RATIO):
    """Xử lý 1 dòng phụ đề: TTS + Align. Chạy trong thread riêng."""
    match = re.match(r"\[(SPEAKER_\d+)\] (.*)", sub.text)
    if match:
        spk_id = match.group(1)
        content = match.group(2)
    else:
        spk_id = "SPEAKER_00" 
        content = sub.text
        
    cfg = mapping.get(spk_id, {"engine": "tiktok", "voice": "vi_vn_002"})
    engine = cfg.get("engine", "tiktok")
    voice = cfg.get("voice", "vi_vn_002")
    
    temp_raw = f"temp/raw_{i}.mp3"
    temp_aligned = f"temp/aligned_{i}.wav"
    
    success = False
    if engine == "tiktok":
        success = tiktok_tts(content, voice, temp_raw)
        if not success:
            fallback_voice = "vi-VN-NamMinhNeural" if voice == "vi_vn_001" else "vi-VN-HoaiMyNeural"
            success = asyncio.run(edge_tts_gen(content, fallback_voice, temp_raw))
    else:
        success = asyncio.run(edge_tts_gen(content, voice, temp_raw))
        
    # Dùng thời gian sub gốc làm target - KHÔNG giới hạn max_allowed
    # Chấp nhận dè/overlap nhẹ, miễn ĐỌC ĐỦ CÂU không cắt chữ
    base_target_sec = (sub.end.ordinal - sub.start.ordinal) / 1000.0
    final_duration_sec = max(0.1, base_target_sec / speed_rate)

    if success and os.path.exists(temp_raw):
        align_audio(ffmpeg_cmd, ffprobe_cmd, temp_raw, final_duration_sec, temp_aligned, max_speed_ratio)
        if os.path.exists(temp_aligned):
            segment = AudioSegment.from_file(temp_aligned, format="wav")
        else:
            segment = AudioSegment.silent(duration=int(final_duration_sec * 1000))
    else:
        segment = AudioSegment.silent(duration=int(final_duration_sec * 1000))
    
    return i, sub.start.ordinal, segment


def _process_edge_batch(edge_tasks, all_subs_data, subs, mapping, speed_rate, ffmpeg_cmd, ffprobe_cmd, max_speed_ratio=DEFAULT_MAX_SPEED_RATIO):
    """Batch xử lý Edge TTS: gọi async gather rồi align song song."""
    if not edge_tasks:
        return []
    
    # Phase 1: Batch TTS qua asyncio
    tts_inputs = [(content, voice, raw_path) for (_, content, voice, raw_path) in edge_tasks]
    results = asyncio.run(edge_tts_batch(tts_inputs))
    
    # Phase 2: Align song song qua ThreadPool
    align_results = []
    
    def _align_one(task_info, tts_ok):
        idx, content, voice, raw_path = task_info
        sub = all_subs_data[idx]["sub"]
        
        # Dùng thời gian sub gốc - KHÔNG giới hạn, ĐỌC ĐỦ CÂU
        base_target_sec = (sub.end.ordinal - sub.start.ordinal) / 1000.0
        final_duration_sec = max(0.1, base_target_sec / speed_rate)
        
        temp_aligned = f"temp/aligned_{idx}.wav"
        
        if tts_ok and os.path.exists(raw_path):
            align_audio(ffmpeg_cmd, ffprobe_cmd, raw_path, final_duration_sec, temp_aligned, max_speed_ratio)
            if os.path.exists(temp_aligned):
                segment = AudioSegment.from_file(temp_aligned, format="wav")
            else:
                segment = AudioSegment.silent(duration=int(final_duration_sec * 1000))
        else:
            segment = AudioSegment.silent(duration=int(final_duration_sec * 1000))
        
        return idx, sub.start.ordinal, segment
    
    with ThreadPoolExecutor(max_workers=MAX_ALIGN_WORKERS) as pool:
        futures = []
        for task_info, tts_ok in zip(edge_tasks, results):
            futures.append(pool.submit(_align_one, task_info, tts_ok))
        
        for f in as_completed(futures):
            align_results.append(f.result())
    
    return align_results


def main():
    parser = argparse.ArgumentParser(description="Module 4: Lồng tiếng Đa giọng & Khớp nhịp (2026) - Turbo")
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--tts_out", required=True)
    parser.add_argument("--speaker_mapping", help="JSON mapping")
    parser.add_argument("--speed_rate", default="1.0", help="Tốc độ đọc cơ bản")
    parser.add_argument("--max_speed_ratio", default="1.25", help="Tốc độ đọc tối đa (1.25 = nhanh hơn gốc 25%%). Giảm xuống 1.1 nếu muốn đọc chậm hơn.")
    parser.add_argument("--ffmpeg_path", default="ffmpeg", help="Đường dẫn đến thư mục ffmpeg")
    parser.add_argument("--keep_segments", action="store_true", help="Giữ lại temp/aligned_*.wav cho video sync")
    
    args = parser.parse_args()
    
    speed_rate = float(args.speed_rate)
    max_speed_ratio = float(args.max_speed_ratio)
    ffmpeg_cmd = getattr(args, 'ffmpeg_path', 'ffmpeg')
    ffprobe_cmd = ffmpeg_cmd.replace("ffmpeg.exe", "ffprobe.exe") if getattr(sys, 'platform', '') == "win32" and "ffmpeg.exe" in ffmpeg_cmd else "ffprobe"

    mapping = {}
    if args.speaker_mapping:
        mapping = json.loads(args.speaker_mapping)
    
    subs = pysrt.open(args.srt_vi_in, encoding='utf-8')
    subs = sorted(subs, key=lambda s: s.start.ordinal)
    
    os.makedirs("temp", exist_ok=True)
    
    # THUẬT TOÁN ĐỒNG BỘ CAPCUT ABSOLUTE TIMELINE - TURBO
    last_sub_end = subs[-1].end.ordinal if subs else 0
    canvas_duration = last_sub_end + 5000
    full_audio = AudioSegment.silent(duration=canvas_duration)
    
    t_start = time.time()
    console.print(f"[bold cyan]⚡ Dự án lồng tiếng TURBO (Song song): {len(subs)} câu thoại, Tốc độ cơ sở: {speed_rate}x, Giới hạn nhanh: {max_speed_ratio}x[/bold cyan]")
    
    # Phân loại tasks theo engine
    all_subs_data = []
    edge_tasks = []
    tiktok_tasks = []
    
    for i, sub in enumerate(subs):
        match = re.match(r"\[(SPEAKER_\d+)\] (.*)", sub.text)
        if match:
            spk_id = match.group(1)
            content = match.group(2)
        else:
            spk_id = "SPEAKER_00" 
            content = sub.text
            
        cfg = mapping.get(spk_id, {"engine": "tiktok", "voice": "vi_vn_002"})
        engine = cfg.get("engine", "tiktok")
        voice = cfg.get("voice", "vi_vn_002")
        
        raw_path = f"temp/raw_{i}.mp3"
        all_subs_data.append({"sub": sub, "engine": engine, "voice": voice, "content": content, "raw_path": raw_path})
        
        if engine == "edge" or engine != "tiktok":
            edge_tasks.append((i, content, voice, raw_path))
        else:
            tiktok_tasks.append((i, content, voice, raw_path))
    
    results = []
    
    # ============================================================
    # STRATEGY 1: Edge TTS -> asyncio.gather (nhanh gấp nhiều lần)
    # ============================================================
    if edge_tasks:
        console.print(f"[cyan]⚡ Edge TTS batch: {len(edge_tasks)} câu đồng thời...[/cyan]")
        edge_results = _process_edge_batch(edge_tasks, all_subs_data, subs, mapping, speed_rate, ffmpeg_cmd, ffprobe_cmd, max_speed_ratio)
        results.extend(edge_results)
        console.print(f"[green]✅ Edge TTS hoàn tất: {len(edge_results)} câu[/green]")
    
    # ============================================================
    # STRATEGY 2: TikTok TTS -> ThreadPoolExecutor (HTTP song song)
    # ============================================================
    if tiktok_tasks:
        console.print(f"[cyan]⚡ TikTok TTS parallel: {len(tiktok_tasks)} câu, {MAX_TTS_WORKERS} luồng...[/cyan]")
        
        with ThreadPoolExecutor(max_workers=MAX_TTS_WORKERS) as pool:
            futures = {}
            for (idx, content, voice, raw_path) in tiktok_tasks:
                sub = all_subs_data[idx]["sub"]
                fut = pool.submit(_process_single_sub, idx, sub, subs, mapping, speed_rate, ffmpeg_cmd, ffprobe_cmd, max_speed_ratio)
                futures[fut] = idx
            
            done_count = 0
            for f in as_completed(futures):
                done_count += 1
                try:
                    result = f.result()
                    results.append(result)
                    if done_count % 10 == 0 or done_count == len(tiktok_tasks):
                        console.print(f"[dim]  TikTok: {done_count}/{len(tiktok_tasks)} xong[/dim]")
                except Exception as e:
                    idx = futures[f]
                    console.print(f"[yellow]⚠️ Lỗi câu {idx}: {e}[/yellow]")
                    sub = all_subs_data[idx]["sub"]
                    dur = (sub.end.ordinal - sub.start.ordinal) / 1000.0
                    results.append((idx, sub.start.ordinal, AudioSegment.silent(duration=int(dur * 1000))))
        
        console.print(f"[green]✅ TikTok TTS hoàn tất: {len(tiktok_tasks)} câu[/green]")
    
    # ============================================================
    # Overlay tất cả lên canvas
    # ============================================================
    console.print("[cyan]🎵 Đang ghép audio lên timeline...[/cyan]")
    for idx, position_ms, segment in results:
        full_audio = full_audio.overlay(segment, position=position_ms)

    # Cắt gọn đoạn đuôi thừa
    final_end_ms = last_sub_end + 1000
    if final_end_ms < len(full_audio):
        full_audio = full_audio[:final_end_ms]

    full_audio.export(args.tts_out, format="wav")
    
    # ============================================================
    # Export tts_timing.json cho Video Sync (mod7)
    # ============================================================
    timing_data = []
    for idx, position_ms, segment in sorted(results, key=lambda x: x[0]):
        sub = subs[idx]
        timing_data.append({
            "index": idx,
            "sub_start_ms": sub.start.ordinal,
            "sub_end_ms": sub.end.ordinal,
            "sub_duration_ms": sub.end.ordinal - sub.start.ordinal,
            "tts_duration_ms": len(segment)
        })
    
    timing_path = os.path.join(os.path.dirname(args.tts_out), "tts_timing.json")
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing_data, f, indent=2, ensure_ascii=False)
    console.print(f"[green]📊 Đã xuất timing: {timing_path}[/green]")
    
    elapsed = time.time() - t_start
    console.print(f"[bold green]⚡ LỒNG TIẾNG TURBO HOÀN TẤT![/bold green] -> {args.tts_out}")
    console.print(f"[bold green]⏱️ Thời gian: {elapsed:.1f}s ({len(subs)} câu, ~{elapsed/max(len(subs),1):.2f}s/câu)[/bold green]")

    import shutil
    if not args.keep_segments:
        shutil.rmtree("temp", ignore_errors=True)
    else:
        console.print("[dim]💾 Giữ lại temp/ cho video sync[/dim]")

if __name__ == "__main__":
    main()
