import os
import json
import uuid
import argparse
import pysrt
from datetime import datetime
from pydub import AudioSegment
from rich.console import Console

console = Console()

def get_duration_ms(file_path):
    """Lấy thời lượng file audio/video bằng pydub."""
    try:
        audio = AudioSegment.from_file(file_path)
        return len(audio)
    except:
        return 0

def create_capcut_json(project_name, video_path, bgm_path, tts_path, srt_path):
    """
    Sinh file draft_content.json chuẩn cấu trúc CapCut PC.
    Thời gian trong CapCut tính bằng Microseconds (1s = 1,000,000).
    """
    video_dur_ms = get_duration_ms(video_path)
    bgm_dur_ms = get_duration_ms(bgm_path)
    tts_dur_ms = get_duration_ms(tts_path)
    subs = pysrt.open(srt_path)

    # Khởi tạo Metadata
    video_id = str(uuid.uuid4())
    bgm_id = str(uuid.uuid4())
    tts_id = str(uuid.uuid4())

    content = {
        "canvas_config": {"height": 1080, "width": 1920},
        "duration": video_dur_ms * 1000,
        "tracks": [],
        "materials": {
            "videos": [
                {"id": video_id, "path": os.path.abspath(video_path), "duration": video_dur_ms * 1000, "type": "video"}
            ],
            "audios": [
                {"id": bgm_id, "path": os.path.abspath(bgm_path), "duration": bgm_dur_ms * 1000, "type": "audio"},
                {"id": tts_id, "path": os.path.abspath(tts_path), "duration": tts_dur_ms * 1000, "type": "audio"}
            ],
            "texts": []
        }
    }

    # 1. Track Video
    content["tracks"].append({
        "id": str(uuid.uuid4()), "type": "video",
        "segments": [{
            "id": str(uuid.uuid4()), "material_id": video_id,
            "target_timerange": {"duration": video_dur_ms * 1000, "start": 0},
            "source_timerange": {"duration": video_dur_ms * 1000, "start": 0}
        }]
    })

    # 2. Track BGM (Volume 0.3)
    content["tracks"].append({
        "id": str(uuid.uuid4()), "type": "audio",
        "segments": [{
            "id": str(uuid.uuid4()), "material_id": bgm_id,
            "target_timerange": {"duration": bgm_dur_ms * 1000, "start": 0},
            "source_timerange": {"duration": bgm_dur_ms * 1000, "start": 0},
            "common_config": {"volume": 0.3}
        }]
    })

    # 3. Track TTS
    content["tracks"].append({
        "id": str(uuid.uuid4()), "type": "audio",
        "segments": [{
            "id": str(uuid.uuid4()), "material_id": tts_id,
            "target_timerange": {"duration": tts_dur_ms * 1000, "start": 0},
            "source_timerange": {"duration": tts_dur_ms * 1000, "start": 0}
        }]
    })

    # 4. Track Subtitles (Text)
    text_track_segments = []
    for sub in subs:
        text_id = str(uuid.uuid4())
        start_us = sub.start.ordinal * 1000
        end_us = sub.end.ordinal * 1000
        dur_us = end_us - start_us
        
        content["materials"]["texts"].append({
            "id": text_id,
            "content": json.dumps({
                "text": sub.text,
                "styles": [{"font_size": 20, "color": "#FFFFFF"}]
            })
        })
        
        text_track_segments.append({
            "id": str(uuid.uuid4()), "material_id": text_id,
            "target_timerange": {"duration": dur_us, "start": start_us}
        })
        
    content["tracks"].append({"id": str(uuid.uuid4()), "type": "text", "segments": text_track_segments})

    return content

def main():
    parser = argparse.ArgumentParser(description="Module 6: Xuất Project CapCut PC (LongTieng 2026 Edition)")
    parser.add_argument("--video_in", required=True)
    parser.add_argument("--bgm_in", required=True)
    parser.add_argument("--tts_in", required=True)
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--project_name", default="Reup_Video_Dubbing")
    
    args = parser.parse_args()
    
    output_dir = os.path.join(os.getcwd(), f"CapCut_Draft_{args.project_name}")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Gen Draft Content
    draft_content = create_capcut_json(args.project_name, args.video_in, args.bgm_in, args.tts_in, args.srt_vi_in)
    with open(os.path.join(output_dir, "draft_content.json"), "w", encoding="utf-8") as f:
        json.dump(draft_content, f, indent=4, ensure_ascii=False)
        
    # 2. Gen Meta Info
    meta_info = {
        "draft_id": str(uuid.uuid4()),
        "draft_name": args.project_name,
        "draft_updated_time": int(datetime.now().timestamp() * 1000)
    }
    with open(os.path.join(output_dir, "draft_meta_info.json"), "w", encoding="utf-8") as f:
        json.dump(meta_info, f, indent=4, ensure_ascii=False)
        
    console.print(f"[bold green]XUẤT DỰ ÁN CAPCUT THÀNH CÔNG![/bold green]")
    console.print(f"Thư mục Draft: [bold magenta]{output_dir}[/bold magenta]")
    console.print("Gợi ý: Copy toàn bộ thư mục này vào folder Drafts của CapCut Desktop để mở.")

if __name__ == "__main__":
    main()
