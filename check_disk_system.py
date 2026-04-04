import os
import sys

def get_dir_size(path):
    if not os.path.exists(path):
        return 0
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    pass
    except Exception:
        pass
    return total_size

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

user_home = os.path.expanduser("~")
check_paths = [
    os.path.join(user_home, ".cache"),
    os.path.join(user_home, "AppData", "Local", "pip", "cache"),
    os.path.join(user_home, "AppData", "Local", "Temp"),
    os.path.join(user_home, "Downloads"),
    os.path.join(user_home, "Downloads", "longtieng"),
    os.path.join(user_home, ".cache", "huggingface"),
    os.path.join(user_home, ".cache", "torch"),
]

print(f"{'Path':<60} | {'Size':<10}")
print("-" * 75)
for p in check_paths:
    size = get_dir_size(p)
    # Relative path from user_home if possible for readability
    display_p = p.replace(user_home, "~")
    print(f"{display_p:<60} | {format_size(size):<10}")
