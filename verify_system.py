import os
import sys
import subprocess

def check_file(path):
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    return exists, size

def check_import(package):
    try:
        # Use the env's python to check imports
        env_py = os.path.join("env", "Scripts", "python.exe")
        if not os.path.exists(env_py):
            env_py = sys.executable
            
        cmd = [env_py, "-c", f"import {package}; print('OK')"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return "OK" in result.stdout
    except Exception:
        return False

files_to_check = [
    "app_desktop.py",
    "mod4_tts_dubbing.py",
    "mod7_video_sync.py",
    "mod1_demucs.py",
    "ffmpeg-2026-03-30-git-e54e117998-full_build/bin/ffmpeg.exe",
    ".env"
]

packages_to_check = [
    "torch",
    "edge_tts",
    "pysrt",
    "requests",
    "pydub",
    "cv2",
    "PIL",
    "customtkinter"
]

print(f"{'File':<60} | {'Status':<10} | {'Size':<10}")
print("-" * 85)
all_ok = True
for f in files_to_check:
    exists, size = check_file(f)
    status = "EXISTS" if exists else "MISSING"
    if not exists: all_ok = False
    print(f"{f:<60} | {status:<10} | {size/1024:.2f} KB")

print("\n" + f"{'Package':<30} | {'Status':<10}")
print("-" * 45)
for p in packages_to_check:
    status = "OK" if check_import(p) else "ERROR/MISSING"
    if status != "OK": all_ok = False
    print(f"{p:<30} | {status:<10}")

if all_ok:
    print("\n[SUCCESS] Chúc mừng! Mọi thứ vẫn nguyên vẹn và hoạt động bình thường.")
else:
    print("\n[WARNING] Có một số thành phần bị thiếu hoặc lỗi. Hãy kiểm tra lại.")
