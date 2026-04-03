import os
import json
import uuid
import argparse
import pysrt
import shutil
from rich.console import Console
from datetime import datetime

console = Console()

def get_capcut_draft_path():
    """Tìm thư mục Drafts của CapCut hoặc Jianying trên Windows."""
    local_appdata = os.getenv("LOCALAPPDATA")
    if not local_appdata:
        return None
    possible_paths = [
        os.path.join(local_appdata, "CapCut", "User Data", "Projects", "com.lveditor.draft"),
        os.path.join(local_appdata, "CapCut", "User Data", "Projects", "com.lved.capcut.win"),
        os.path.join(local_appdata, "JianyingPro", "User Data", "Projects", "com.lveditor.draft"),
        os.path.join(local_appdata, "JianyingPro", "User Data", "Projects", "com.lved.jianying.win")
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def get_duration_us(path):
    """Lấy thời lượng file bằng ffprobe (trả về microseconds)."""
    import subprocess
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return int(float(res.stdout.strip()) * 1000000) if res.stdout.strip() else 0
    except:
        return 0

def export_with_template(video_in, tts_in, bgm_in, srt_vi_in, project_dir, template_dir):
    """
    Clone MAU_CHUAN và CHỈ PATCH các trường cần thiết, giữ nguyên tất cả trường khác.
    """
    video_dur = get_duration_us(video_in)
    tts_dur = get_duration_us(tts_in)
    bgm_dur = get_duration_us(bgm_in) if os.path.exists(bgm_in) else 0

    # ========== BƯỚC 1: Clone toàn bộ MAU_CHUAN ==========
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
    shutil.copytree(template_dir, project_dir)
    console.print("[bold green]>>> Đã clone toàn bộ MAU_CHUAN.[/bold green]")

    # ========== BƯỚC 2: Đọc Meta gốc (đã copy), CHỈ PATCH vài trường ==========
    meta_path = os.path.join(project_dir, "draft_meta_info.json")
    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # Chỉ thay đổi những gì CẦN thay đổi
    new_draft_id = str(uuid.uuid4()).upper()
    now_us = int(datetime.now().timestamp() * 1000000)

    meta["draft_id"] = new_draft_id
    meta["draft_name"] = os.path.basename(project_dir)
    meta["draft_fold_path"] = project_dir.replace("\\", "/")
    meta["tm_draft_create"] = now_us
    meta["tm_draft_modified"] = now_us

    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)

    console.print("[bold green]>>> Đã patch Meta (giữ nguyên cấu trúc gốc).[/bold green]")

    # ========== BƯỚC 3: Tìm Timeline ID từ root content ==========
    root_content_path = os.path.join(project_dir, "draft_content.json")
    with open(root_content_path, 'r', encoding='utf-8') as f:
        root_data = json.load(f)
    timeline_id = root_data.get("id")

    # ========== BƯỚC 4: Patch inner Timeline content ==========
    inner_path = os.path.join(project_dir, "Timelines", timeline_id, "draft_content.json")
    if not os.path.exists(inner_path):
        console.print(f"[bold red]Không tìm thấy Timeline: {inner_path}[/bold red]")
        return

    with open(inner_path, 'r', encoding='utf-8') as f:
        inner_data = json.load(f)

    # Tạo material IDs
    v_mat_id = str(uuid.uuid4()).lower()
    t_mat_id = str(uuid.uuid4()).lower()
    b_mat_id = str(uuid.uuid4()).lower()

    # Cập nhật duration
    inner_data["duration"] = video_dur

    # Thay thế materials
    inner_data["materials"]["videos"] = [
        {"id": v_mat_id, "path": video_in.replace("\\", "/"), "duration": video_dur, "type": "video"}
    ]
    inner_data["materials"]["audios"] = [
        {"id": t_mat_id, "path": tts_in.replace("\\", "/"), "duration": tts_dur, "type": "audio"}
    ]
    if bgm_dur > 0:
        inner_data["materials"]["audios"].append(
            {"id": b_mat_id, "path": bgm_in.replace("\\", "/"), "duration": bgm_dur, "type": "audio"}
        )
    inner_data["materials"]["texts"] = []

    # Thay thế tracks
    inner_data["tracks"] = [
        {"id": str(uuid.uuid4()).upper(), "type": "audio", "segments": [
            {"id": str(uuid.uuid4()).upper(), "material_id": t_mat_id,
             "target_timerange": {"duration": tts_dur, "start": 0},
             "source_timerange": {"duration": tts_dur, "start": 0}, "volume": 2.0}
        ]},
        {"id": str(uuid.uuid4()).upper(), "type": "video", "segments": [
            {"id": str(uuid.uuid4()).upper(), "material_id": v_mat_id,
             "target_timerange": {"duration": video_dur, "start": 0},
             "source_timerange": {"duration": video_dur, "start": 0}}
        ]},
        {"id": str(uuid.uuid4()).upper(), "type": "audio", "segments": []},
        {"id": str(uuid.uuid4()).upper(), "type": "text", "segments": []}
    ]

    # BGM track
    if bgm_dur > 0:
        inner_data["tracks"][2]["segments"].append({
            "id": str(uuid.uuid4()).upper(), "material_id": b_mat_id,
            "target_timerange": {"duration": video_dur, "start": 0},
            "source_timerange": {"duration": video_dur, "start": 0}, "volume": 0.2
        })

    # Subtitles track
    subs = pysrt.open(srt_vi_in, encoding='utf-8')
    for sub in subs:
        txt_id = str(uuid.uuid4()).lower()
        start = sub.start.ordinal * 1000
        dur = (sub.end.ordinal - sub.start.ordinal) * 1000
        inner_data["materials"]["texts"].append({"id": txt_id, "content": sub.text, "type": "text"})
        inner_data["tracks"][3]["segments"].append({
            "id": str(uuid.uuid4()).upper(), "material_id": txt_id,
            "target_timerange": {"duration": dur, "start": start},
            "source_timerange": {"duration": dur, "start": 0}
        })

    with open(inner_path, 'w', encoding='utf-8') as f:
        json.dump(inner_data, f, ensure_ascii=False, indent=4)

    console.print("[bold green]>>> Đã patch Timeline content.[/bold green]")

    # ========== BƯỚC 5: Cập nhật root duration ==========
    root_data["duration"] = video_dur
    with open(root_content_path, 'w', encoding='utf-8') as f:
        json.dump(root_data, f, ensure_ascii=False, indent=4)

    console.print(f"[bold green]XUẤT DỰ ÁN CAPCUT THÀNH CÔNG: {os.path.basename(project_dir)}[/bold green]")

def main():
    parser = argparse.ArgumentParser(description="Module 6: Xuất project CapCut v8.x (Patch-Only Clone)")
    parser.add_argument("--video_in", required=True)
    parser.add_argument("--tts_in", required=True)
    parser.add_argument("--bgm_in", required=True)
    parser.add_argument("--srt_vi_in", required=True)
    parser.add_argument("--project_name", default="")

    args = parser.parse_args()
    p_name = args.project_name if args.project_name else datetime.now().strftime("%m%d_%H%M%S")

    capcut_base = get_capcut_draft_path()
    if not capcut_base:
        console.print("[bold red]LỖI: Không tìm thấy thư mục CapCut![/bold red]")
        return

    project_dir = os.path.join(capcut_base, p_name)
    template_dir = os.path.join(capcut_base, "MAU_CHUAN")

    if not os.path.exists(template_dir):
        console.print("[bold red]LỖI: Không tìm thấy dự án MAU_CHUAN![/bold red]")
        return

    console.print(f"[bold cyan]>>> Clone + Patch: {p_name}...[/bold cyan]")
    try:
        export_with_template(args.video_in, args.tts_in, args.bgm_in, args.srt_vi_in, project_dir, template_dir)
    except Exception as e:
        console.print(f"[bold red]Lỗi: {str(e)}[/bold red]")

if __name__ == "__main__":
    main()
