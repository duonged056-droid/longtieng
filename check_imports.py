import sys
import os

try:
    import tkinter
    print("tkinter OK")
    import customtkinter
    print("customtkinter OK")
    import cv2
    print("cv2 OK")
    import PIL
    print("PIL OK")
    import edge_tts
    print("edge_tts OK")
    import pysrt
    print("pysrt OK")
    import dotenv
    print("dotenv OK")
    import asyncio
    print("asyncio OK")
    import re
    print("re OK")
    import json
    print("json OK")
    import threading
    print("threading OK")
    import subprocess
    print("subprocess OK")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

print("All imports SUCCESS")
