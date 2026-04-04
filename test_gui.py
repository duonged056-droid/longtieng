import sys
import os
import traceback

print("--- DIAGNOSTIC START ---")
print(f"Python: {sys.version}")
print(f"CWD: {os.getcwd()}")

try:
    print("1. Testing tkinter...")
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.destroy()
    print("   tkinter OK")

    print("2. Testing customtkinter import...")
    import types
    # Apply the same patch we have in app_desktop.py
    darkdetect_mock = types.ModuleType("darkdetect")
    darkdetect_mock.isDark = lambda: True
    darkdetect_mock.isLight = lambda: False
    darkdetect_mock.theme = lambda: "Dark"
    sys.modules["darkdetect"] = darkdetect_mock
    
    import customtkinter as ctk
    print("   customtkinter import OK")

    print("3. Testing customtkinter init...")
    ctk.set_appearance_mode("Dark")
    app = ctk.CTk()
    app.withdraw()
    app.destroy()
    print("   customtkinter init OK")

    print("4. Testing other imports...")
    import cv2
    print("   cv2 OK")
    import PIL.Image
    print("   PIL OK")
    import edge_tts
    print("   edge_tts OK")

    print("\n--- DIAGNOSTIC SUCCESS ---")
except Exception as e:
    print("\n--- DIAGNOSTIC FAILED ---")
    traceback.print_exc()
    input("\nNhấn Enter để thoát...")
