import os
import torch
import hashlib

home = torch.hub._get_torch_home()
fp = os.path.join(home, 'whisperx-vad-segmentation.bin')

print(f"Path: {fp}")
if os.path.exists(fp):
    size = os.path.getsize(fp)
    print(f"Size: {size} bytes")
    with open(fp, "rb") as f:
        content = f.read(500)
        print(f"Content start: {content}")
        f.seek(0)
        sha256 = hashlib.sha256(f.read()).hexdigest()
        print(f"SHA256: {sha256}")
else:
    print("File does not exist")
