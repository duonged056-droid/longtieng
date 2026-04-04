import os

def get_dir_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total_size += os.path.getsize(fp)
            except OSError:
                pass
    return total_size

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0

root = "."
summary = []

for item in os.listdir(root):
    path = os.path.join(root, item)
    if os.path.isdir(path):
        size = get_dir_size(path)
        summary.append((item, size))
    else:
        size = os.path.getsize(path)
        summary.append((item, size))

summary.sort(key=lambda x: x[1], reverse=True)

print(f"{'Item':<30} | {'Size':<10}")
print("-" * 45)
for item, size in summary:
    print(f"{item:<30} | {format_size(size):<10}")
