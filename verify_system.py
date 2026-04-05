import os
import sys
import subprocess
import torch
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def check_file(path):
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    return exists, size

def check_import(package):
    try:
        # Use the current python to check imports first
        import importlib
        importlib.import_module(package)
        return True
    except ImportError:
        try:
            # Fallback check via subprocess
            cmd = [sys.executable, "-c", f"import {package}; print('OK')"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return "OK" in result.stdout
        except Exception:
            return False

def get_ffmpeg_version():
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        first_line = result.stdout.split('\n')[0]
        return first_line.split('version ')[1].split(' ')[0]
    except Exception:
        return "Not Found"

def verify_system():
    console.print(Panel.fit("[bold cyan]BumYT AI Dubbing Studio - System Verification[/bold cyan]", border_style="blue"))
    
    # 1. Check Hardware
    hw_table = Table(title="Phần cứng & Driver")
    hw_table.add_column("Thành phần", style="cyan")
    hw_table.add_column("Thông tin", style="magenta")
    hw_table.add_column("Trạng thái", justify="center")

    cuda_available = torch.cuda.is_available()
    hw_table.add_row("NVIDIA CUDA", "CUDA Core" if cuda_available else "N/A", "[green]OK[/green]" if cuda_available else "[red]MISSING[/red]")
    if cuda_available:
        hw_table.add_row("GPU Name", torch.cuda.get_device_name(0), "[green]DETECTED[/green]")
        vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        hw_table.add_row("VRAM", f"{vram:.1f} GB", "[green]OK[/green]" if vram > 4 else "[yellow]LOW[/yellow]")
    
    ffmpeg_ver = get_ffmpeg_version()
    hw_table.add_row("FFmpeg", ffmpeg_ver, "[green]OK[/green]" if ffmpeg_ver != "Not Found" else "[red]MISSING[/red]")
    
    console.print(hw_table)

    # 2. Check Files
    files_to_check = [
        "app_desktop.py", "mod1_demucs.py", "mod2_asr.py", 
        "mod4_tts_dubbing.py", "mod7_video_sync.py", "mod8_blur_sub.py",
        ".env", "requirements.txt"
    ]
    
    file_table = Table(title="Cấu trúc tệp tin")
    file_table.add_column("Tên tệp", style="cyan")
    file_table.add_column("Dung lượng", justify="right")
    file_table.add_column("Trạng thái", justify="center")

    all_files_ok = True
    for f in files_to_check:
        exists, size = check_file(f)
        if not exists: all_files_ok = False
        status = "[green]EXISTS[/green]" if exists else "[red]MISSING[/red]"
        file_table.add_row(f, f"{size/1024:.1f} KB" if exists else "-", status)
    
    console.print(file_table)

    # 3. Check Packages
    packages = ["torch", "edge_tts", "pysrt", "requests", "pydub", "cv2", "rich", "customtkinter"]
    pkg_table = Table(title="Thư viện Python")
    pkg_table.add_column("Package", style="cyan")
    pkg_table.add_column("Trạng thái", justify="center")

    all_pkgs_ok = True
    for p in packages:
        ok = check_import(p)
        if not ok: all_pkgs_ok = False
        pkg_table.add_row(p, "[green]OK[/green]" if ok else "[red]ERROR[/red]")
    
    console.print(pkg_table)

    if all_files_ok and all_pkgs_ok and cuda_available:
        console.print("\n[bold green]✅ HỆ THỐNG SẴN SÀNG![/bold green] Bạn có thể bắt đầu lồng tiếng chuyên nghiệp.")
    else:
        console.print("\n[bold red]⚠️ CẢNH BÁO:[/bold red] Có lỗi hoặc thiếu thành phần. Vui lòng kiểm tra lại logs ở trên.")

if __name__ == "__main__":
    verify_system()
