import os
import sys

def get_python():
    env_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "env", "Scripts", "python.exe")
    return env_py if os.path.exists(env_py) else get_python()

import threading
import subprocess
import json
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import asyncio
import edge_tts
import re
import pysrt

try:
    import cv2
    from PIL import Image, ImageTk
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# Initialize UI
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")  # Will override with custom colors

# --- BUMYT COLOR PALETTE (PREMIUM DARK) ---
B_BG = "#0f111a"      # Black navy background
B_SIDEBAR = "#161823"  # Deep sidebar
B_ACCENT = "#7d5fff"   # Purple accent
B_FRAME = "#1c1e2d"    # Section frame
B_TEXT = "#e0e0e0"
B_SUCCESS = "#00d285"  # Mint green
B_DANGER = "#ff4d4d"   # Soft red

class BumYTCloneExactApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Màn hình & Title
        self.title("LongTieng AI Pro - Convert Only 2026")
        self.geometry("1400x850")
        self.minsize(1000, 700)

        # Cấu hình Layout: 1 Grid lớn
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==================== SIDEBAR ====================
        self.sidebar_frame = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=B_SIDEBAR)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        # Logo BumYT Header
        self.logo_top_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.logo_top_frame.grid(row=0, column=0, padx=20, pady=(30, 20))
        
        self.logo_circle = ctk.CTkLabel(self.logo_top_frame, text="B", font=ctk.CTkFont(size=32, weight="bold"), width=60, height=60, corner_radius=30, fg_color=B_ACCENT, text_color="white")
        self.logo_circle.pack(pady=5)
        
        self.logo_label = ctk.CTkLabel(self.logo_top_frame, text="BumYT TTS", font=ctk.CTkFont(size=22, weight="bold"), text_color="white")
        self.logo_label.pack()

        # Sidebar buttons (Only Settings left as per user request to simplify)
        self.btn_settings = ctk.CTkButton(self.sidebar_frame, text="⚙️ Cài đặt API", height=45, corner_radius=8, font=ctk.CTkFont(size=14, weight="bold"), anchor="w", fg_color="transparent", border_width=1, border_color=B_FRAME, command=self.open_settings)
        self.btn_settings.grid(row=5, column=0, padx=20, pady=20, sticky="sew")

        # ==================== MAIN CONTENT AREA ====================
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(0, weight=1)

        # ==================== GLOBAL VARS ====================
        self.out_dir = "capcut"
        os.makedirs(self.out_dir, exist_ok=True)
        self.srt_vi_path = os.path.join(self.out_dir, "vi_output.srt")
        
        self.video_path = ""
        self.cap = None
        self.cv_image = None
        self.tk_image = None
        self.roi_coords = None
        self.roi_rect_id = None
        self.video_w = 0
        self.video_h = 0
        
        import dotenv
        dotenv.load_dotenv(".env")

        # Build the only Tab (Convert)
        self.frame_tab3 = self._build_tab3_convert()
        self.frame_tab3.grid(row=0, column=0, sticky="nsew")

    def pick_file(self, entry_widget, filetypes, title="Chọn File"):
        filename = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if filename:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, filename)

    def log(self, text, level="info"):
        if not hasattr(self, "log_view") or not self.log_view:
            print(text)
            return
            
        prefix = ""
        if level == "success": prefix = "✅ "
        elif level == "warning": prefix = "⚠️ "
        elif level == "error": prefix = "❌ "
        
        formatted_text = f"{prefix}{text}\n"
        self.log_view.insert("end", formatted_text)
        self.log_view.see("end")
        self.update_idletasks()
        print(text)

    # ==========================================================
    # TAB 3: CHUYỂN ĐỔI (TTS & RENDER CAPCUT)
    # ==========================================================

    # ==========================================================
    # SETTINGS WINDOW
    # ==========================================================
    def open_settings(self):
        win = ctk.CTkToplevel(self)
        win.title("Cài đặt API")
        win.geometry("600x400")
        win.transient(self)
        win.grab_set()
        
        frame = ctk.CTkFrame(win)
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(frame, text="Gemini API Key:").pack(anchor="w", pady=(0, 5))
        e_gemini = ctk.CTkEntry(frame, width=500, show="*")
        e_gemini.pack(pady=(0, 15))
        e_gemini.insert(0, os.environ.get("GEMINI_API_KEY", ""))
        
        ctk.CTkLabel(frame, text="OpenAI API Key:").pack(anchor="w", pady=(0, 5))
        e_openai = ctk.CTkEntry(frame, width=500, show="*")
        e_openai.pack(pady=(0, 15))
        e_openai.insert(0, os.environ.get("OPENAI_API_KEY", ""))
        
        ctk.CTkLabel(frame, text="System Prompt (Dịch thuật):").pack(anchor="w", pady=(0, 5))
        e_prompt = ctk.CTkTextbox(frame, width=500, height=80)
        e_prompt.pack(pady=(0, 10))
        e_prompt.insert("0.0", os.environ.get("SYSTEM_PROMPT", "Bạn là một dịch giả chuyên nghiệp..."))
        
        def save():
            env_content = {}
            if os.path.exists(".env"):
                with open(".env", "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line:
                            parts = line.strip().split("=", 1)
                            if len(parts) == 2:
                                env_content[parts[0]] = parts[1]
                            
            env_content["GEMINI_API_KEY"] = e_gemini.get()
            env_content["OPENAI_API_KEY"] = e_openai.get()
            env_content["SYSTEM_PROMPT"] = e_prompt.get("0.0", tk.END).strip().replace("\n", " ")
            
            with open(".env", "w", encoding="utf-8") as f:
                for k, v in env_content.items():
                    f.write(f"{k}={v}\n")
            
            # Update current env
            for k, v in env_content.items():
                os.environ[k] = v
            
            messagebox.showinfo("Thành công", "Đã lưu cài đặt!")
            win.destroy()
            
        ctk.CTkButton(frame, text="Lưu Cài Đặt", command=save, fg_color=B_SUCCESS, text_color="black", font=ctk.CTkFont(weight="bold")).pack(pady=10)


    # ==========================================================
    # CHUYỂN ĐỔI (TTS & RENDER CAPCUT)
    def _build_tab3_convert(self):
        frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)  
        frame.grid_rowconfigure(1, weight=0)  
        
        # --- TOP AREA (SCROLLABLE DASHBOARD) ---
        top_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        
        # --- TITLE HEADER ---
        header_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 20))
        ctk.CTkLabel(header_frame, text="⚡ LONG-TIENG AI PRO v2026", font=ctk.CTkFont(size=24, weight="bold"), text_color=B_ACCENT).pack(side="left", padx=5)
        
        # --- CARD 1: 🎙️ GIỌNG ĐỌC & TTS ---
        card_voice = ctk.CTkFrame(top_frame, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_voice.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(card_voice, text="🎙️ 1. Cấu hình Giọng Đọc & TTS", font=ctk.CTkFont(size=15, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=(10, 5))
        
        v_grid = ctk.CTkFrame(card_voice, fg_color="transparent")
        v_grid.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(v_grid, text="Provider:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.opt_tts_prov = ctk.CTkOptionMenu(v_grid, values=["Edge TTS", "TikTok TTS", "Google TTS"], width=180, fg_color=B_FRAME, command=self.update_voice_options)
        self.opt_tts_prov.set("Edge TTS")
        self.opt_tts_prov.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(v_grid, text="Giọng đọc:").grid(row=0, column=2, padx=(20, 5), pady=5, sticky="w")
        self.opt_voice_id = ctk.CTkOptionMenu(v_grid, values=["Edge Hoài My (Nữ YouTube)", "Edge Nam Minh (Nam YouTube)"], width=220, fg_color=B_FRAME)
        self.opt_voice_id.set("Edge Hoài My (Nữ YouTube)")
        self.opt_voice_id.grid(row=0, column=3, padx=5, pady=5)
        
        ctk.CTkLabel(v_grid, text="Test giọng:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.test_text = ctk.CTkEntry(v_grid, placeholder_text="Nhập chữ test...", width=300)
        self.test_text.grid(row=1, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(v_grid, text="🔊 Chạy Thử", width=100, fg_color=B_ACCENT, font=ctk.CTkFont(weight="bold"), command=self.test_voice).grid(row=1, column=3, padx=5, pady=5)

        # --- CARD 2: 📂 DỰ ÁN & FILE NGUỒN ---
        card_proj = ctk.CTkFrame(top_frame, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_proj.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(card_proj, text="📂 2. Dự Án & File Nguồn", font=ctk.CTkFont(size=15, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=(10, 5))
        
        p_grid = ctk.CTkFrame(card_proj, fg_color="transparent")
        p_grid.pack(fill="x", padx=15, pady=10)
        p_grid.columnconfigure(1, weight=1)
        
        # SRT
        ctk.CTkLabel(p_grid, text="File SRT nguồn:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_srt_in = ctk.CTkEntry(p_grid)
        self.entry_srt_in.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(p_grid, text="Mở File...", width=100, fg_color=B_FRAME, command=lambda: self.pick_file(self.entry_srt_in, [("SRT", "*.srt")])).grid(row=0, column=2, padx=5)
        
        # Video
        ctk.CTkLabel(p_grid, text="Video lồng tiếng:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_video_t3 = ctk.CTkEntry(p_grid)
        self.entry_video_t3.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(p_grid, text="Mở File...", width=100, fg_color=B_FRAME, command=lambda: self.pick_file(self.entry_video_t3, [("Video", "*.mp4 *.avi *.mkv")])).grid(row=1, column=2, padx=5)
        
        # Output Path (Hồ sơ)
        ctk.CTkLabel(p_grid, text="FFmpeg Path:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.ffmpeg_path = ctk.CTkEntry(p_grid)
        default_ffmpeg = os.path.abspath(os.path.join(os.path.dirname(__file__), "ffmpeg-2026-03-30-git-e54e117998-full_build", "bin", "ffmpeg.exe"))
        self.ffmpeg_path.insert(0, default_ffmpeg.replace("\\", "/"))
        self.ffmpeg_path.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(p_grid, text="Cấu hình...", width=100, fg_color=B_FRAME, command=lambda: self.pick_file(self.ffmpeg_path, [("Exe", "*.exe")])).grid(row=2, column=2, padx=5)

        # --- CARD 3: ⚙️ CHẾ ĐỘ XỬ LÝ (Processing Modes) ---
        card_mode = ctk.CTkFrame(top_frame, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_mode.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(card_mode, text="⚙️ 3. Chế độ Xử lý & Tùy chọn", font=ctk.CTkFont(size=15, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=(10, 5))
        
        m_grid = ctk.CTkFrame(card_mode, fg_color="transparent")
        m_grid.pack(fill="x", padx=15, pady=10)
        
        self.chk_auto_sep = ctk.CTkCheckBox(m_grid, text="🔊 Tách nhạc nền (AI Demucs)", text_color=B_ACCENT)
        self.chk_auto_sep.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.chk_separate_audio = ctk.CTkCheckBox(m_grid, text="🎚️ Xuất nhạc & lời riêng (CapCut)")
        self.chk_separate_audio.select()
        self.chk_separate_audio.grid(row=0, column=1, padx=10, pady=5, sticky="w")
        
        self.chk_all_clean = ctk.CTkCheckBox(m_grid, text="🗑️ Chế độ dọn dẹp (Xóa file rác)", text_color=B_DANGER)
        self.chk_all_clean.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.chk_capcut = ctk.CTkCheckBox(m_grid, text="🎬 Tạo dự án CapCut", text_color=B_ACCENT)
        self.chk_capcut.select()
        self.chk_capcut.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        
        self.chk_multi_voice = ctk.CTkCheckBox(m_grid, text="🎭 Đa giọng đọc (Characters)")
        self.chk_multi_voice.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.chk_audio_edit = ctk.CTkCheckBox(m_grid, text="🎧 Audio Edit Mode (Tách segment)")
        self.chk_audio_edit.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        # --- CARD 4: 🛠️ CÔNG CỤ HỖ TRỢ (Extra Tools) ---
        card_tools = ctk.CTkFrame(top_frame, fg_color=B_FRAME, corner_radius=15)
        card_tools.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(card_tools, text="🛠️ 4. Công Cụ Hỗ Trợ", font=ctk.CTkFont(size=15, weight="bold"), text_color="#aaa").pack(anchor="w", padx=15, pady=(10, 5))
        
        t_row = ctk.CTkFrame(card_tools, fg_color="transparent")
        t_row.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkButton(t_row, text="🛡️ Làm Mờ Sub", width=150, fg_color="#2b2b2b", command=self.run_blur_process).pack(side="left", padx=5)
        ctk.CTkButton(t_row, text="🎵 Tách Nhạc Lẻ", width=150, fg_color="#2b2b2b", command=self.run_separation).pack(side="left", padx=5)
        ctk.CTkButton(t_row, text="📏 Chọn Vùng Mờ", width=150, fg_color=B_FRAME, border_width=1, command=self.pick_blur_roi).pack(side="left", padx=5)

        # -- MAIN START BUTTON --
        ctk.CTkButton(top_frame, text="🚀 BẮT ĐẦU CHUYỂN ĐỔI", height=70, fg_color=B_ACCENT, corner_radius=35, font=ctk.CTkFont(size=20, weight="bold"), command=self.run_tab3).pack(fill="x", padx=50, pady=(20, 10))
        
        self.main_progress = ctk.CTkProgressBar(top_frame, height=12, progress_color=B_ACCENT)
        self.main_progress.pack(fill="x", padx=50, pady=(0, 20))
        self.main_progress.set(1.0)

        # --- BOTTOM AREA (SMALL LOGS) ---
        log_frame = ctk.CTkFrame(frame, fg_color=B_SIDEBAR, height=180) # Fixed small height
        log_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_frame.pack_propagate(False) # Prevent shrinking
        
        ctk.CTkLabel(log_frame, text="📜 Nhật ký quá trình (Bé bé thôi)", font=ctk.CTkFont(size=12, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=10, pady=2)
        self.log_view = ctk.CTkTextbox(log_frame, fg_color="#0a0a0a", text_color="#00ee00", font=ctk.CTkFont(family="Consolas", size=11))
        self.log_view.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        return frame

    # Session ID logic removed per user request

    # ==========================================================
    # LÀM MỜ VÙNG CHỌN (ROI SELECTOR)
    # ==========================================================

    def pick_blur_roi(self):
        if not HAS_CV2:
            messagebox.showerror("Lỗi", "Vui lòng cài đặt opencv-python và Pillow để dùng tính năng này!")
            return
            
        video_in = self.entry_video_blur.get().strip()
        if not video_in or not os.path.exists(video_in):
            messagebox.showerror("Lỗi", "Vui lòng chọn Video trước khi chọn vùng!")
            return
            
        self.roi_win = ctk.CTkToplevel(self)
        self.roi_win.title("Chọn vùng làm mờ (Kéo chuột để vẽ hình chữ nhật)")
        self.roi_win.geometry("1000x800")
        self.roi_win.attributes("-topmost", True)
        
        self.cap = cv2.VideoCapture(video_in)
        self.video_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        self.roi_canvas = tk.Canvas(self.roi_win, bg="black", cursor="cross")
        self.roi_canvas.pack(fill="both", expand=True, padx=20, pady=20)
        
        self.roi_slider = ctk.CTkSlider(self.roi_win, from_=0, to=self.total_frames-1, command=lambda v: self._update_roi_frame(int(float(v))))
        self.roi_slider.set(0)
        self.roi_slider.pack(fill="x", padx=40, pady=10)
        
        # Thêm nút Xóa vùng chọn
        ctk.CTkButton(self.roi_win, text="XÓA VÙNG CHỌN", width=150, fg_color=B_DANGER, command=self._clear_roi).pack(pady=10)
        
        self.roi_canvas.bind("<ButtonPress-1>", self._on_roi_press)
        self.roi_canvas.bind("<B1-Motion>", self._on_roi_drag)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_roi_release)
        
        self.start_x = None
        self.start_y = None
        self.roi_rect_id = None
        self.scale_f = 1.0
        
        self._update_roi_frame(0)

    def _update_roi_frame(self, frame_idx):
        if not self.cap: return
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        success, frame = self.cap.read()
        if not success: return
        
        # Resize to fit canvas
        cw = self.roi_canvas.winfo_width()
        ch = self.roi_canvas.winfo_height()
        if cw < 100: cw = 900 # Default
        if ch < 100: ch = 600

        self.scale_f = min(cw/self.video_w, ch/self.video_h)
        nw = int(self.video_w * self.scale_f)
        nh = int(self.video_h * self.scale_f)
        
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img_resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        
        self.tk_image = ImageTk.PhotoImage(img_resized)
        self.roi_canvas.delete("all") # Xóa hết cả ảnh cũ và hình cũ
        self.roi_canvas.create_image(cw//2, ch//2, image=self.tk_image, anchor="center")
        
        # Vẽ lại ROI duy nhất nếu có
        if self.roi_coords:
            self._draw_roi_rect()

    def _draw_roi_rect(self):
        if not self.roi_coords: return
        cw = self.roi_canvas.winfo_width()
        ch = self.roi_canvas.winfo_height()
        nw = int(self.video_w * self.scale_f)
        nh = int(self.video_h * self.scale_f)
        
        x, y, w, h = self.roi_coords
        off_x = (cw - nw) // 2
        off_y = (ch - nh) // 2
        
        x1 = (x * self.scale_f) + off_x
        y1 = (y * self.scale_f) + off_y
        x2 = x1 + (w * self.scale_f)
        y2 = y1 + (h * self.scale_f)
        self.roi_canvas.create_rectangle(x1, y1, x2, y2, outline="red", width=3, tags="roi_rect")

    def _clear_roi(self):
        self.roi_coords = None
        self.roi_canvas.delete("roi_rect")
        self.log("🗑️ Đã xóa vùng chọn Blur.")

    def _on_roi_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.roi_canvas.delete("roi_rect") # Xóa mọi hình chữ nhật cũ trước khi vẽ cái mới
        self.roi_rect_id = self.roi_canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=3, tags="roi_rect")

    def _on_roi_drag(self, event):
        self.roi_canvas.coords(self.roi_rect_id, self.start_x, self.start_y, event.x, event.y)

    def _on_roi_release(self, event):
        # Calculate real video coordinates
        cw = self.roi_canvas.winfo_width()
        ch = self.roi_canvas.winfo_height()
        nw = int(self.video_w * self.scale_f)
        nh = int(self.video_h * self.scale_f)
        
        off_x = (cw - nw) // 2
        off_y = (ch - nh) // 2
        
        # Real coords
        rx1 = (min(self.start_x, event.x) - off_x) / self.scale_f
        ry1 = (min(self.start_y, event.y) - off_y) / self.scale_f
        rx2 = (max(self.start_x, event.x) - off_x) / self.scale_f
        ry2 = (max(self.start_y, event.y) - off_y) / self.scale_f
        
        # Clamp to video bounds
        rx1 = max(0, min(self.video_w, rx1))
        ry1 = max(0, min(self.video_h, ry1))
        rx2 = max(0, min(self.video_w, rx2))
        ry2 = max(0, min(self.video_h, ry2))
        
        self.roi_coords = (int(rx1), int(ry1), int(rx2-rx1), int(ry2-ry1))
        self.log(f"📍 Đã chọn vùng Blur: x={self.roi_coords[0]}, y={self.roi_coords[1]}, w={self.roi_coords[2]}, h={self.roi_coords[3]}")

    def run_blur_process(self):
        video_in = self.entry_video_blur.get().strip()
        if not video_in or not os.path.exists(video_in):
            messagebox.showerror("Lỗi", "Vui lòng chọn Video nguồn!")
            return
        if not self.roi_coords:
            messagebox.showerror("Lỗi", "Vui lòng 'Chọn vùng mờ' trước!")
            return
            
        video_out = os.path.join(self.out_dir, "video_blurred.mp4")
        self.log(f"\n>>> BẮT ĐẦU LÀM MỜ VÙNG: {video_in}...")
        
        cmd = [
            get_python(), "mod8_blur_sub.py",
            "--video_in", video_in,
            "--video_out", video_out,
            "--x", str(self.roi_coords[0]),
            "--y", str(self.roi_coords[1]),
            "--w", str(self.roi_coords[2]),
            "--h", str(self.roi_coords[3]),
            "--blur", "51"
        ]
        
        threading.Thread(target=self._run_cmds, args=([cmd], "LÀM MỜ THÀNH CÔNG!")).start()

    def run_separation(self):
        v_in = self.entry_sep_in.get().strip()
        if not v_in or not os.path.exists(v_in):
            messagebox.showerror("Lỗi", "Vui lòng chọn Video/Audio để tách!")
            return
            
        self.log("\n>>> BẮT ĐẦU TÁCH ÂM THANH (Demucs AI)...")
        cmd = [
            get_python(), "mod1_demucs.py",
            "--video_in", v_in,
            "--output_dir", self.out_dir
        ]
        threading.Thread(target=self._run_cmds, args=([cmd], "TÁCH ÂM THÀNH CÔNG!")).start()

    def update_voice_options(self, choice):
        if "TikTok" in choice:
            self.opt_voice_id.configure(values=["TikTok Nữ (Hà Nhân/Bảo Bối)", "TikTok Nữ trầm", "TikTok Nam"])
            self.opt_voice_id.set("TikTok Nữ (Hà Nhân/Bảo Bối)")
        elif "Edge" in choice:
            self.opt_voice_id.configure(values=["Edge Hoài My (Nữ YouTube)", "Edge Nam Minh (Nam YouTube)"])
            self.opt_voice_id.set("Edge Hoài My (Nữ YouTube)")
        else:
            self.opt_voice_id.configure(values=["Google Nữ", "Google Nam"])
            self.opt_voice_id.set("Google Nữ")

    def run_tab3(self):
        custom_srt = self.entry_srt_in.get().strip()
        custom_video = self.entry_video_t3.get().strip()

        if not custom_srt:
            if os.path.exists(self.srt_vi_path):
                custom_srt = self.srt_vi_path
            else:
                messagebox.showerror("Lỗi", "Vui lòng chọn Video / SRT nguồn!")
                return
        
        # Hardcode box vì đã bỏ Tab 1 chọn ROI
        blur_box = "none"

        self.log("\n>>> BẮT ĐẦU QUY TRÌNH TỰ ĐỘNG (FULL PIPELINE)...")
        
        # Mapping voice config
        tts_prov = self.opt_tts_prov.get()
        voice_label = self.opt_voice_id.get()
        engine = "edge"
        if "TikTok" in tts_prov: engine = "tiktok"
        elif "Google" in tts_prov: engine = "google"
            
        voice_id = "vi-VN-HoaiMyNeural" 
        if engine == "tiktok":
            if "Nam" in voice_label: voice_id = "vi_vn_001"
            elif "trầm" in voice_label: voice_id = "vi_vn_003"
            else: voice_id = "vi_vn_002"
        else:
            if "Nam" in voice_label: voice_id = "vi-VN-NamMinhNeural"
            else: voice_id = "vi-VN-HoaiMyNeural"
            
        if self.chk_multi_voice.get():
            if engine == "tiktok":
                v00 = voice_id
                v01 = "vi_vn_001" if v00 in ["vi_vn_002", "vi_vn_003"] else "vi_vn_002"
                v02 = "vi_vn_003" if v00 == "vi_vn_002" else "vi_vn_002"
            else:
                v00 = voice_id
                v01 = "vi-VN-NamMinhNeural" if "HoaiMy" in v00 else "vi-VN-HoaiMyNeural"
                v02 = "vi-VN-HoaiMyNeural"
                
            mapping = json.dumps({
                "SPEAKER_00": {"engine": engine, "voice": v00},
                "SPEAKER_01": {"engine": engine, "voice": v01},
                "SPEAKER_02": {"engine": engine, "voice": v02}
            })
        else:
            mapping = json.dumps({
                "SPEAKER_00": {"engine": engine, "voice": voice_id},
                "SPEAKER_01": {"engine": engine, "voice": voice_id},
                "SPEAKER_02": {"engine": engine, "voice": voice_id}
            })
        
        output_mp3 = os.path.join(self.out_dir, "voices.wav")
        bgm_wav = os.path.join(self.out_dir, "bgm.wav")
        final_video = os.path.join(self.out_dir, "final_result.mp4")
        timing_json = os.path.join(self.out_dir, "tts_timing.json")
        
        # Video sync outputs
        video_synced = os.path.join(self.out_dir, "video_synced.mp4")
        audio_synced = os.path.join(self.out_dir, "voices_synced.wav")
        bgm_synced = os.path.join(self.out_dir, "bgm_synced.wav")
        srt_synced = os.path.join(self.out_dir, "vi_synced.srt")
        
        speed_val = 1.0
        ffmpeg_bin = self.ffmpeg_path.get().strip()

        tasks = []
        
        # 0. Tự động tách BGM (Demucs AI)
        bgm_clean = os.path.join(self.out_dir, "bgm_clean.wav")
        if self.chk_auto_sep.get() and custom_video:
            cmd_m1 = [
                get_python(), "mod1_demucs.py",
                "--video_in", custom_video,
                "--output_dir", self.out_dir
            ]
            tasks.append(cmd_m1)

        # 1. TTS Dubbing
        cmd_m4 = [
            get_python(), "mod4_tts_dubbing.py", 
            "--srt_vi_in", custom_srt, 
            "--tts_out", output_mp3, 
            "--speaker_mapping", mapping,
            "--speed_rate", str(speed_val),
            "--max_speed_ratio", "1.25",
            "--ffmpeg_path", ffmpeg_bin,
            "--keep_segments"
        ]
        tasks.append(cmd_m4)

        if custom_video:
            # 2. Video Sync & BGM Stretch
            cmd_m7 = [
                get_python(), "mod7_video_sync.py",
                "--video_in", custom_video,
                "--timing_json", timing_json,
                "--srt_vi_in", custom_srt,
                "--aligned_dir", "temp",
                "--video_out", video_synced,
                "--audio_out", audio_synced,
                "--srt_out", srt_synced,
                "--ffmpeg_path", ffmpeg_bin
            ]
            
            # Kiểm tra BGM khả dụng
            can_use_bgm = self.chk_auto_sep.get() or os.path.exists(bgm_clean)
            if can_use_bgm:
                cmd_m7 += ["--bgm_in", bgm_clean]
                if self.chk_separate_audio.get():
                    cmd_m7 += ["--bgm_out", bgm_synced]
                    # Tiếp theo dùng bản synced tách rời
                    bgm_wav = bgm_synced
                else:
                    bgm_wav = bgm_clean

            tasks.append(cmd_m7)
            
            # 3. Check & Muxing
            tasks.append(("__check_sync__", custom_video, video_synced, 
                          output_mp3, audio_synced, custom_srt, srt_synced))
            
            cmd_m5 = [
                get_python(), "mod5_mux_video.py", 
                "--video_in", "__VIDEO__", 
                "--tts_in", "__AUDIO__", 
                "--bgm_in", bgm_wav, 
                "--srt_vi_in", "__SRT__", 
                "--blur_box", blur_box, 
                "--video_out", final_video
            ]
            tasks.append(cmd_m5)
            
            # 4. CapCut Export (Track nhạc và lời riêng biệt)
            if self.chk_capcut.get():
                cmd_m6 = [
                    get_python(), "mod6_capcut_export.py",
                    "--video_in", "__VIDEO__",
                    "--tts_in", "__AUDIO__",
                    "--bgm_in", bgm_wav,
                    "--srt_vi_in", "__SRT__"
                ]
                tasks.append(cmd_m6)
        else:
            self.log("Bỏ qua muxing video và tạo CapCut vì không có video.", level="warning")
        
        threading.Thread(target=self._run_cmds, args=(tasks, "QUY TRÌNH HOÀN TẤT!")).start()

    def test_voice(self):
        text = self.test_text.get()
        if not text: text = "Chào mừng bạn đến với BumYT Pro 2026."
        self.log(f"Đang Test giọng đọc: {text}")
        
        async def do_test():
            communicate = edge_tts.Communicate(text, "vi-VN-HoaiMyNeural")
            await communicate.save("test_voice.mp3")
            os.startfile("test_voice.mp3")
            
        asyncio.run(do_test())

    def _run_cmds(self, cmds, success_msg):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        kwargs = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        
        # Biến lưu file thực tế (synced hoặc gốc)
        actual_video = ""
        actual_audio = ""
        actual_srt = ""
        
        for idx, cmd in enumerate(cmds):
            # Xử lý __check_sync__: kiểm tra mod7 tạo file thành công chưa
            if isinstance(cmd, tuple) and cmd[0] == "__check_sync__":
                _, orig_video, synced_video, orig_audio, synced_audio, orig_srt, synced_srt = cmd
                if os.path.exists(synced_video) and os.path.exists(synced_audio):
                    actual_video = synced_video
                    actual_audio = synced_audio
                    actual_srt = synced_srt if os.path.exists(synced_srt) else orig_srt
                    self.log("✅ Video Sync OK — dùng file đã đồng bộ", level="success")
                else:
                    actual_video = orig_video
                    actual_audio = orig_audio
                    actual_srt = orig_srt
                    self.log("⚠️ Video Sync bỏ qua — dùng file gốc", level="warning")
                continue
            
            # Thay placeholder bằng file thực tế
            if isinstance(cmd, list):
                cmd = [c.replace("__VIDEO__", actual_video).replace("__AUDIO__", actual_audio).replace("__SRT__", actual_srt) if isinstance(c, str) else c for c in cmd]
            
            self.log(f"> Đang xử lý: {os.path.basename(cmd[1])}...")
            try:
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=env, **kwargs)
                for line in iter(process.stdout.readline, ""):
                    self.log(line.strip())
                rc = process.wait()
                if rc == 0:
                    # --- AUTO CLEANUP LOGIC ---
                    if self.chk_all_clean.get():
                        if "mod8_blur_sub.py" in str(cmd):
                            # Xóa file video gốc sau khi mờ xong
                            try:
                                v_in_idx = cmd.index("--video_in") + 1
                                v_in = cmd[v_in_idx]
                                if os.path.exists(v_in):
                                    os.remove(v_in)
                                    self.log(f"🗑️ Đã xóa file video gốc: {os.path.basename(v_in)}")
                            except: pass
                        elif "mod7_video_sync.py" in str(cmd):
                            # Xóa file lồng tiếng chưa kéo dãn (voices.wav)
                            v_tmp = os.path.join(self.out_dir, "voices.wav")
                            if os.path.exists(v_tmp):
                                os.remove(v_tmp)
                                self.log("🗑️ Đã xóa file lồng tiếng chưa đồng bộ.")
                    # -------------------------
                else:
                    # mod7 lỗi → chỉ warn, không dừng
                    if "mod7_video_sync" in str(cmd):
                        self.log(f"⚠️ Video Sync lỗi — sẽ dùng file gốc", level="warning")
                        continue
                    self.log(f"❌ LỖI trong quá trình: {cmd[1]}", level="warning")
                    return
            except Exception as e:
                if "mod7_video_sync" in str(cmd):
                    self.log(f"⚠️ Video Sync lỗi — sẽ dùng file gốc", level="warning")
                    continue
                self.log(f"❌ LỖI HỆ THỐNG: {e}", level="warning")
                return
        
        self.log(success_msg, level="success")

def route_cli():
    if getattr(sys, 'frozen', False) and len(sys.argv) > 1 and sys.argv[1].endswith(".py"):
        script = sys.argv[1]
        sys.argv = [script] + sys.argv[2:]
        try:
            if script == "mod1_demucs.py":
                import mod1_demucs
                mod1_demucs.main()
            elif script == "mod2_asr.py":
                import mod2_asr
                mod2_asr.main()
            elif script == "mod3_translate.py":
                import mod3_translate
                mod3_translate.main()
            elif script == "mod4_tts_dubbing.py":
                import mod4_tts_dubbing
                mod4_tts_dubbing.main()
            elif script == "mod5_mux_video.py":
                import mod5_mux_video
                mod5_mux_video.main()
            elif script == "mod6_capcut_export.py":
                import mod6_capcut_export
                mod6_capcut_export.main()
            elif script == "mod7_video_sync.py":
                import mod7_video_sync
                mod7_video_sync.main()
            elif script == "tool_get_blur_box.py":
                import tool_get_blur_box
                from tool_get_blur_box import main
                main()
        except Exception as e:
            print(f"Subprocess system error: {e}")
        sys.exit(0)

if __name__ == "__main__":
    import multiprocessing
    import sys
    import io
    # Ensure UTF-8 output for console
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
        
    multiprocessing.freeze_support()
    route_cli()
    
    app = BumYTCloneExactApp()
    app.mainloop()
