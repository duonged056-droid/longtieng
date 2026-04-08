import os
import sys
import traceback

# Ghi log lỗi ra file để debug
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    with open("crash.log", "w", encoding="utf-8") as f:
        f.write("=== CRASH LOG ===\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    print(f"Ứng dụng gặp lỗi. Chi tiết tại crash.log: {exc_value}")
    # Hiện thông báo nếu có tkinter
    try:
        import tkinter.messagebox as mb
        mb.showerror("Lỗi khởi động", f"Ứng dụng gặp lỗi:\n{exc_value}\n\nChi tiết xem tại file crash.log")
    except:
        pass

sys.excepthook = handle_exception

# Fix hang on Windows: Bypass theme detection (darkdetect)
import types
darkdetect_mock = types.ModuleType("darkdetect")
darkdetect_mock.isDark = lambda: True
darkdetect_mock.isLight = lambda: False
darkdetect_mock.theme = lambda: "Dark"
sys.modules["darkdetect"] = darkdetect_mock

def get_python():
    env_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "env", "Scripts", "python.exe")
    if os.path.exists(env_py):
        return env_py
    return sys.executable

import threading
import time
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
    from PIL import Image, ImageTk, ImageDraw, ImageFont
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
        self.title("YTDUONGVIETSUB - Professional AI Dubbing Studio")
        self.geometry("1450x980")
        self.minsize(1100, 800)
        self.configure(fg_color=B_BG)

        # Cấu hình Layout chính: Cột trái (Video) và Cột phải (Controls)
        self.grid_columnconfigure(0, weight=3) # Video panel takes more space
        self.grid_columnconfigure(1, weight=2) # Control panel
        self.grid_rowconfigure(0, weight=1)

        # ==================== GLOBAL VARS ====================
        self.out_dir = "output"
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
        self.scale_f = 1.0
        
        # New: Subtitle Position & Dragging state
        self.sub_x_percent = 50.0  # Mặc định ở giữa
        self.sub_y_percent = 30.0  # Mặc định theo slider (tương ứng MarginV)
        self.dragging_sub = False
        self.sub_bbox = None  # (x1, y1, x2, y2) trên canvas
        
        import dotenv
        dotenv.load_dotenv(".env")

        # ==================== LEFT PANEL: VIDEO & ROI ====================
        self.left_panel = self._build_left_panel()
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)

        # ==================== CONTROLS & LOGS ====================
        self.right_panel = self._build_right_panel()
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 20), pady=20)

        # ==================== PROCESS MANAGEMENT ====================
        self.active_processes = []
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

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

        # Ép tác vụ UI về luồng chính để chống Crash App
        def _update_ui():
            self.log_view.insert("end", formatted_text)
            self.log_view.see("end")
            self.update_idletasks()

        self.after(0, _update_ui)
        print(text)

    def _build_left_panel(self):
        frame = ctk.CTkFrame(self, fg_color=B_SIDEBAR, corner_radius=20, border_width=1, border_color="#2b2b2b")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Top Header for Video Panel
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(header, text="📺 VIDEO PREVIEW & ROI SELECTOR", font=ctk.CTkFont(size=16, weight="bold"), text_color=B_SUCCESS).pack(side="left")
        
        # Canvas for Video & ROI
        self.roi_canvas = tk.Canvas(frame, bg="#0a0a0a", highlightthickness=0, cursor="cross")
        self.roi_canvas.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        # Video controls
        ctrl_bar = ctk.CTkFrame(frame, fg_color="transparent")
        ctrl_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 20))
        
        self.roi_slider = ctk.CTkSlider(ctrl_bar, from_=0, to=100, height=15, progress_color=B_ACCENT, command=self._on_slider_move)
        self.roi_slider.set(0)
        self.roi_slider.pack(fill="x", side="top", pady=(0, 15))
        
        btn_box = ctk.CTkFrame(ctrl_bar, fg_color="transparent")
        btn_box.pack(fill="x")
        
        ctk.CTkButton(btn_box, text="📂 NẠP VIDEO NGUỒN", height=40, fg_color=B_ACCENT, font=ctk.CTkFont(weight="bold"), command=self.load_unified_video).pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="🗑️ XÓA VÙNG MỜ", height=40, fg_color="#333", text_color="#ff4d4d", command=self._clear_roi).pack(side="left", padx=5)
        
        # Feature Row: Blur & Action
        feat_box = ctk.CTkFrame(ctrl_bar, fg_color="transparent")
        feat_box.pack(fill="x", pady=(10, 0))
        
        ctk.CTkButton(feat_box, text="🚀 CHẠY LÀM MỜ SUB", height=42, fg_color=B_SUCCESS, text_color="black", font=ctk.CTkFont(weight="bold"), command=self.run_blur_only).pack(side="left", fill="x", expand=True, padx=5)

        # Bind events for drawing
        self.roi_canvas.bind("<ButtonPress-1>", self._on_roi_press)
        self.roi_canvas.bind("<B1-Motion>", self._on_roi_drag)
        self.roi_canvas.bind("<ButtonRelease-1>", self._on_roi_release)
        self.roi_canvas.bind("<Configure>", lambda e: self._redraw_current_frame()) # Handle resize

        return frame

    def _pick_video_t3(self):
        """Chọn video trực tiếp từ panel phải — đồng bộ với panel trái."""
        path = filedialog.askopenfilename(title="Chọn Video", filetypes=[("Video", "*.mp4 *.avi *.mkv *.mov")])
        if path:
            self._set_video_path(path)

    def _set_video_path(self, path):
        """Cập nhật video path cho CẢ 2 panel (trái + phải)."""
        self.video_path = path
        # Cập nhật ô Video ở panel phải
        if hasattr(self, "entry_video_t3"):
            self.entry_video_t3.delete(0, tk.END)
            self.entry_video_t3.insert(0, path)

    def load_unified_video(self):
        path = filedialog.askopenfilename(title="Chọn Video", filetypes=[("Video", "*.mp4 *.avi *.mkv *.mov")])
        if path:
            # Cập nhật video cho cả 2 panel
            self._set_video_path(path)
            
            self.cap = cv2.VideoCapture(path)
            if not self.cap.isOpened():
                self.log(f"Lỗi: Không thể mở video {path}", level="error")
                return
            
            self.video_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))

            self.video_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            self.roi_slider.configure(from_=0, to=self.total_frames - 1)
            self.roi_slider.set(0)
            
            self.log(f"🎬 Đã nạp video: {os.path.basename(path)} ({self.video_w}x{self.video_h})")
            
            # Check for matching SRT
            srt_guess = path.rsplit(".", 1)[0] + ".srt"
            if os.path.exists(srt_guess):
                self.entry_srt_in.delete(0, tk.END)
                self.entry_srt_in.insert(0, srt_guess)
                self.log(f"📝 Tự động nhận diện file phụ đề: {os.path.basename(srt_guess)}")

            self._update_roi_frame(0)

    def _on_slider_move(self, value):
        if self.cap:
            self._update_roi_frame(int(float(value)))

    def _redraw_current_frame(self):
        if self.cap:
            curr = int(self.roi_slider.get())
            self._update_roi_frame(curr)


    def _build_right_panel(self):
        # This replaces the original main content frame logic but inside the right column
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=0) # Header fixed
        frame.grid_rowconfigure(1, weight=5) # Scrollable area takes most space
        frame.grid_rowconfigure(2, weight=0) # Log fixed

        # Fixed Top Header
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(5, 10))
        
        ctk.CTkLabel(header, text="⚡ CONTROL CENTER", font=ctk.CTkFont(size=22, weight="bold"), text_color=B_ACCENT).pack(side="left")
        
        # Right Panel SCROLLABLE Content
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        frame.grid_rowconfigure(1, weight=1)

        # Card 1: GIỌNG ĐỌC
        card_voice = ctk.CTkFrame(scroll, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_voice.pack(fill="x", pady=10)
        ctk.CTkLabel(card_voice, text="🎙️ 1. Cấu hình Giọng Đọc (TTS)", font=ctk.CTkFont(size=14, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=10)
        
        v_grid = ctk.CTkFrame(card_voice, fg_color="transparent")
        v_grid.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(v_grid, text="Provider:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.opt_tts_prov = ctk.CTkOptionMenu(v_grid, values=["Edge TTS", "TikTok TTS", "Google TTS"], width=150, fg_color=B_FRAME, command=self.update_voice_options)
        self.opt_tts_prov.set("Edge TTS")
        self.opt_tts_prov.grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(v_grid, text="Giọng đọc:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.opt_voice_id = ctk.CTkOptionMenu(v_grid, values=["Edge Hoài My (Nữ YouTube)", "Edge Nam Minh (Nam YouTube)"], width=200, fg_color=B_FRAME)
        self.opt_voice_id.set("Edge Hoài My (Nữ YouTube)")
        self.opt_voice_id.grid(row=1, column=1, padx=5, pady=5)
        
        # --- BẮT ĐẦU ĐOẠN THÊM MỚI: Ô NHẬP TIKTOK SESSION ID ---
        ctk.CTkLabel(v_grid, text="TikTok Session:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_tiktok_session = ctk.CTkEntry(v_grid, width=350, placeholder_text="Nhập sessionid của TikTok (Bắt buộc nếu xài giọng TikTok)")
        self.entry_tiktok_session.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        
        # Tự động đọc ID cũ từ file .env lên giao diện (nếu có)
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("TIKTOK_SESSION_ID="):
                        self.entry_tiktok_session.insert(0, line.split("=", 1)[1].strip())
        except Exception:
            # Nếu chưa có file .env, điền tạm cái ID cũ
            self.entry_tiktok_session.insert(0, "9bd1a9b86b51abca383eded216b33134")
        # --- KẾT THÚC ĐOẠN THÊM MỚI ---
        
        # Card 2: FILE & DỰ ÁN
        card_proj = ctk.CTkFrame(scroll, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_proj.pack(fill="x", pady=10)
        ctk.CTkLabel(card_proj, text="📂 2. Dự Án & File Phụ Đề", font=ctk.CTkFont(size=14, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=10)
        
        p_grid = ctk.CTkFrame(card_proj, fg_color="transparent")
        p_grid.pack(fill="x", padx=15, pady=(0, 15))
        p_grid.columnconfigure(1, weight=1)
        
        # Video nguồn — liên kết với nút NẠP VIDEO NGUỒN bên panel trái
        ctk.CTkLabel(p_grid, text="Video:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.entry_video_t3 = ctk.CTkEntry(p_grid, height=35, placeholder_text="← Nhấn 'NẠP VIDEO NGUỒN' hoặc chọn tại đây")
        self.entry_video_t3.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(p_grid, text="Mở...", width=100, fg_color=B_FRAME, command=self._pick_video_t3).grid(row=0, column=2, padx=5)

        ctk.CTkLabel(p_grid, text="File SRT:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_srt_in = ctk.CTkEntry(p_grid, height=35)
        self.entry_srt_in.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(p_grid, text="Mở...", width=100, fg_color=B_FRAME, command=lambda: self.pick_file(self.entry_srt_in, [("SRT", "*.srt")])).grid(row=1, column=2, padx=5)

        ctk.CTkLabel(p_grid, text="FFmpeg:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.entry_ffmpeg = ctk.CTkEntry(p_grid, height=35)
        # TỰ ĐỘNG QUÉT TÌM FFmpeg TRÁNH HARDCODE
        default_ffmpeg = "ffmpeg"
        base_dir = os.path.dirname(__file__)
        for root, dirs, files in os.walk(base_dir):
            if "ffmpeg.exe" in files:
                default_ffmpeg = os.path.abspath(os.path.join(root, "ffmpeg.exe"))
                break
        self.entry_ffmpeg.insert(0, default_ffmpeg.replace("\\", "/"))
        self.entry_ffmpeg.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ctk.CTkButton(p_grid, text="Cấu hình...", width=100, fg_color=B_FRAME, command=lambda: self.pick_file(self.entry_ffmpeg, [("Exe", "*.exe")])).grid(row=2, column=2, padx=5)

        # Utility for ffmpeg path
        self.ffmpeg_path = ""

        
        # Card 3: CHẾ ĐỘ XỬ LÝ (MODULAR)
        card_mode = ctk.CTkFrame(scroll, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_mode.pack(fill="x", pady=10)
        ctk.CTkLabel(card_mode, text="⚙️ 3. Tùy chọn Xử lý chính", font=ctk.CTkFont(size=14, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=10)
        
        m_grid = ctk.CTkFrame(card_mode, fg_color="transparent")
        m_grid.pack(fill="x", padx=15, pady=(0, 15))
        
        self.chk_run_tts = ctk.CTkCheckBox(m_grid, text="🎙️ Chạy Lồng Tiếng (TTS)", text_color=B_ACCENT)
        self.chk_run_tts.select()
        self.chk_run_tts.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.chk_auto_sep = ctk.CTkCheckBox(m_grid, text="🔊 Tách nhạc nền (AI)")
        self.chk_auto_sep.grid(row=0, column=1, padx=10, pady=5, sticky="w")

        self.chk_all_clean = ctk.CTkCheckBox(m_grid, text="🗑️ Chế độ dọn dẹp dự án (Cleanup)")
        self.chk_all_clean.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")

        # --- BẮT ĐẦU ĐOẠN THÊM MỚI: CARD 4 - HARDSUB ---
        card_sub = ctk.CTkFrame(scroll, fg_color=B_SIDEBAR, corner_radius=15, border_width=1, border_color="#2b2b2b")
        card_sub.pack(fill="x", pady=10)
        ctk.CTkLabel(card_sub, text="🔤 4. Cấu hình Phụ đề (Hardsub)", font=ctk.CTkFont(size=14, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=10)
        
        s_grid = ctk.CTkFrame(card_sub, fg_color="transparent")
        s_grid.pack(fill="x", padx=15, pady=(0, 15))
        
        self.chk_hardsub = ctk.CTkCheckBox(s_grid, text="Bật chèn cứng Phụ đề (Hardsub)", text_color=B_ACCENT, command=self._redraw_current_frame)
        self.chk_hardsub.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        ctk.CTkLabel(s_grid, text="Style chữ:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.opt_sub_style = ctk.CTkOptionMenu(s_grid, values=["Trắng viền đen (Cơ bản)", "Vàng viền đen (Đậm)", "Trắng bóng đổ Neon", "Trắng nền hộp mờ"], command=lambda x: self._redraw_current_frame())
        self.opt_sub_style.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(s_grid, text="Căn lề Dưới (Y):").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.slider_sub_y = ctk.CTkSlider(s_grid, from_=5, to=100, command=lambda x: self._redraw_current_frame())
        self.slider_sub_y.set(30)
        self.slider_sub_y.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(s_grid, text="Cỡ chữ (Size):").grid(row=3, column=0, padx=10, pady=5, sticky="w")
        self.slider_font_size = ctk.CTkSlider(s_grid, from_=10, to=80, command=lambda x: self._redraw_current_frame())
        self.slider_font_size.set(22)
        self.slider_font_size.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(s_grid, text="Độ dày viền (Outline):").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.slider_outline = ctk.CTkSlider(s_grid, from_=0, to=15, command=lambda x: self._redraw_current_frame())
        self.slider_outline.set(2)
        self.slider_outline.grid(row=4, column=1, padx=5, pady=5, sticky="ew")
        
        ctk.CTkLabel(s_grid, text="Đổ bóng chữ (Shadow):").grid(row=5, column=0, padx=10, pady=5, sticky="w")
        self.slider_shadow = ctk.CTkSlider(s_grid, from_=0, to=15, command=lambda x: self._redraw_current_frame())
        self.slider_shadow.set(0)
        self.slider_shadow.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
        # --- KẾT THÚC ĐOẠN THÊM MỚI ---

        # Start Button
        ctk.CTkButton(scroll, text="🚀 BẮT ĐẦU XỬ LÝ", height=60, fg_color=B_ACCENT, corner_radius=30, font=ctk.CTkFont(size=18, weight="bold"), command=self.run_tab3).pack(fill="x", padx=20, pady=20)
        
        self.main_progress = ctk.CTkProgressBar(scroll, height=10, progress_color=B_ACCENT)
        self.main_progress.pack(fill="x", padx=20, pady=(0, 20))
        self.main_progress.set(1.0)

        # Log View (Chat-like console)
        log_card = ctk.CTkFrame(frame, fg_color=B_BG, height=180, corner_radius=15, border_width=1, border_color="#2b2b2b")
        log_card.grid(row=2, column=0, sticky="ew", padx=0, pady=(10, 0))
        log_card.pack_propagate(False)
        
        ctk.CTkLabel(log_card, text="💬 QUÁ TRÌNH XỬ LÝ", font=ctk.CTkFont(size=12, weight="bold"), text_color=B_SUCCESS).pack(anchor="w", padx=15, pady=5)
        self.log_view = ctk.CTkTextbox(log_card, fg_color="#0a0a0a", text_color="#00ee00", font=ctk.CTkFont(family="Consolas", size=11))
        self.log_view.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        return frame

    # ==========================================================
    # TAB 3: CHUYỂN ĐỔI (TTS & RENDER CAPCUT)
    # ==========================================================



    # Session ID logic removed per user request


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
        
        # --- BẮT ĐẦU: VẼ LIVE PREVIEW PHỤ ĐỀ LÊN KHUNG HÌNH ---
        if hasattr(self, 'chk_hardsub') and self.chk_hardsub.get():
            try:
                draw = ImageDraw.Draw(img_resized)
                # CHUẨN HÓA: f_size trên preview phải nhân với scale_f để khớp với màn hình 1080p
                # Multiplier 1.8 giúp cỡ 22-25 trông tự nhiên trên Full HD
                f_size = int(self.slider_font_size.get() * self.scale_f * 1.8)
                out_th = int(self.slider_outline.get() * self.scale_f * 1.2)
                shad_th = int(self.slider_shadow.get() * self.scale_f * 1.2)
                
                try:
                    font = ImageFont.truetype("arialbd.ttf", f_size)
                except:
                    try:
                        # Thử tìm font khác trên Windows
                        font = ImageFont.truetype("arial.ttf", f_size)
                    except:
                        font = ImageFont.load_default()


                sample_text = "YTDUONG - Test Sub CapCut"
                style = self.opt_sub_style.get()
                
                # Sync slider Y với sub_y_percent (nếu cần hiển thị)
                self.slider_sub_y.set(self.sub_y_percent)
                
                # MarginV tương ứng: sub_y_percent * 2.0 để dễ căn chỉnh trên preview
                margin_v = int(self.sub_y_percent * self.scale_f * 2.0)
                
                # Tính toán tọa độ dựa trên % (X) và MarginV (Y)
                bbox = draw.textbbox((0, 0), sample_text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                
                tx = (nw * (self.sub_x_percent / 100.0)) - (tw / 2.0)
                ty = nh - th - margin_v

                # Lưu Bounding Box để bắt sự kiện chuột (coords trên canvas thực tế)
                cw_actual = self.roi_canvas.winfo_width()
                ch_actual = self.roi_canvas.winfo_height()
                if cw_actual < 100: cw_actual = 900
                if ch_actual < 100: ch_actual = 600
                off_x = (cw_actual - nw) // 2
                off_y = (ch_actual - nh) // 2
                
                self.last_tw, self.last_th = tw, th
                self.sub_bbox = (tx + off_x, ty + off_y, tx + off_x + tw, ty + off_y + th)

                # Đổ bóng
                if shad_th > 0:
                    draw.text((tx+shad_th, ty+shad_th), sample_text, font=font, fill="black")

                # Áp dụng màu và viền
                if "Vàng" in style:
                    draw.text((tx, ty), sample_text, font=font, fill="#FFFF00", stroke_width=out_th, stroke_fill="black")
                elif "hộp mờ" in style:
                    pad = int(8 * self.scale_f)
                    draw.rectangle([tx-pad, ty-pad, tx+tw+pad, ty+th+pad], fill=(0,0,0,140))
                    draw.text((tx, ty), sample_text, font=font, fill="white")
                elif "Neon" in style:
                    draw.text((tx+int(2*self.scale_f), ty+int(2*self.scale_f)), sample_text, font=font, fill="#ff00ff")
                    draw.text((tx, ty), sample_text, font=font, fill="white", stroke_width=out_th, stroke_fill="black")
                else:
                    draw.text((tx, ty), sample_text, font=font, fill="white", stroke_width=out_th, stroke_fill="black")
            except Exception as e:
                pass
        # --- KẾT THÚC: LIVE PREVIEW ---
        
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
        
        # Kiểm tra xem có bấm vào phụ đề không
        if hasattr(self, 'sub_bbox') and self.sub_bbox and getattr(self, 'chk_hardsub', None) and self.chk_hardsub.get():
            x1, y1, x2, y2 = self.sub_bbox
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.dragging_sub = True
                return

        self.dragging_sub = False
        self.roi_canvas.delete("roi_rect") # Xóa mọi hình chữ nhật cũ trước khi vẽ cái mới
        self.roi_rect_id = self.roi_canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=3, tags="roi_rect")

    def _on_roi_drag(self, event):
        if hasattr(self, 'dragging_sub') and self.dragging_sub:
            # Tính toán vị trí mới dựa trên chuột
            cw = self.roi_canvas.winfo_width()
            ch = self.roi_canvas.winfo_height()
            nw = int(self.video_w * self.scale_f)
            nh = int(self.video_h * self.scale_f)
            if nw == 0 or nh == 0: return

            off_x = (cw - nw) // 2
            off_y = (ch - nh) // 2
            
            # Tọa độ chuột so với khung video
            vx = event.x - off_x
            vy = event.y - off_y
            
            # Cập nhật X %
            self.sub_x_percent = max(0, min(100, (vx / nw) * 100.0))
            
            # Cập nhật Y (MarginV)
            # ty = nh - th - margin_v => margin_v = nh - th - ty
            # Lấy tâm chữ làm điểm mốc cho mượt
            th = getattr(self, 'last_th', 20)
            ty_target = vy - (th / 2.0)
            margin_v = nh - th - ty_target
            self.sub_y_percent = max(0, min(500, margin_v / (self.scale_f * 2.0)))
            
            self._redraw_current_frame()
        else:
            if hasattr(self, 'roi_rect_id'):
                self.roi_canvas.coords(self.roi_rect_id, self.start_x, self.start_y, event.x, event.y)

    def _on_roi_release(self, event):
        if hasattr(self, 'dragging_sub') and self.dragging_sub:
            self.dragging_sub = False
            self.log(f"📍 Đã đặt vị trí Sub: X={self.sub_x_percent:.1f}%, Y={self.sub_y_percent:.1f}")
            return
            
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
        video_in = self.entry_video_t3.get().strip()

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
            "--blur", "25",
            "--ffmpeg_path", self.entry_ffmpeg.get().strip()
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
            # MỚI: Thêm các lựa chọn giọng đã được "độ" lại thông số
            self.opt_voice_id.configure(values=[
                "Edge Hoài My (Nữ Cơ Bản)", 
                "Edge Nam Minh (Nam Cơ Bản)",
                "Edge Hoài My (Review Phim - Nhanh, Cuốn)",
                "Edge Nam Minh (Kể Chuyện - Trầm Ấm)"
            ])
            self.opt_voice_id.set("Edge Hoài My (Review Phim - Nhanh, Cuốn)")
        else:
            self.opt_voice_id.configure(values=["Google Nữ", "Google Nam"])
            self.opt_voice_id.set("Google Nữ")

    def run_tab3(self):
        custom_srt = self.entry_srt_in.get().strip()
        # Đồng bộ: ưu tiên self.video_path, fallback sang ô nhập bên phải
        custom_video = self.video_path if self.video_path else self.entry_video_t3.get().strip()
        # Nếu user nhập trực tiếp vào ô entry
        if not custom_video:
            entry_val = self.entry_video_t3.get().strip()
            if entry_val and os.path.exists(entry_val):
                custom_video = entry_val
                self.video_path = entry_val

        if not custom_video or not os.path.exists(custom_video):
            messagebox.showerror("Lỗi", "Vui lòng NẠP VIDEO NGUỒN trước khi xử lý!")
            return

        if not custom_srt and self.chk_run_tts.get():
            if os.path.exists(self.srt_vi_path):
                custom_srt = self.srt_vi_path
            else:
                messagebox.showerror("Lỗi", "Vui lòng chọn File SRT để lồng tiếng!")
                return
        
        self.log(f"\n>>> BẮT ĐẦU XỬ LÝ (Dubbing & Sync) - {time.strftime('%H:%M:%S')}")
        
        # AN TOÀN: Cập nhật key TikTok Session ID mà không xóa sạch file .env
        t_session = self.entry_tiktok_session.get().strip()
        if t_session:
            import dotenv
            dotenv.set_key(".env", "TIKTOK_SESSION_ID", t_session)

        
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
            # BỔ SUNG: Ép thông số Pitch (Độ trầm) và Rate (Tốc độ) vào luồng xử lý
            if "Review Phim" in voice_label:
                voice_id = "vi-VN-HoaiMyNeural|+15%|+5Hz"
            elif "Kể Chuyện" in voice_label:
                voice_id = "vi-VN-NamMinhNeural|-10%|-5Hz"
            elif "Nam" in voice_label: 
                voice_id = "vi-VN-NamMinhNeural|+0%|+0Hz"
            else: 
                voice_id = "vi-VN-HoaiMyNeural|+0%|+0Hz"
            
        mapping = json.dumps({
            "SPEAKER_00": {"engine": engine, "voice": voice_id},
            "SPEAKER_01": {"engine": engine, "voice": voice_id},
            "SPEAKER_02": {"engine": engine, "voice": voice_id}
        })
        
        output_mp3 = os.path.join(self.out_dir, "voices.wav")
        bgm_clean = os.path.join(self.out_dir, "bgm_clean.wav")
        video_synced = os.path.join(self.out_dir, "video_synced.mp4")
        bgm_synced = os.path.join(self.out_dir, "bgm_synced.wav")
        vocal_synced = os.path.join(self.out_dir, "vocal_synced.wav")
        audio_full = os.path.join(self.out_dir, "voices_full.wav")
        srt_synced = os.path.join(self.out_dir, "vi_synced.srt")
        timing_json = os.path.join(self.out_dir, "tts_timing.json")
        ffmpeg_bin = self.entry_ffmpeg.get().strip()
        if not ffmpeg_bin: ffmpeg_bin = "ffmpeg"


        tasks = []
        
        # 1. Tự động tách BGM (Demucs AI)
        if self.chk_auto_sep.get() and custom_video:
            tasks.append([get_python(), "mod1_demucs.py", "--video_in", custom_video, "--output_dir", self.out_dir])

        # 2. TTS Dubbing
        if self.chk_run_tts.get():
            tasks.append([
                get_python(), "mod4_tts_dubbing.py", 
                "--srt_vi_in", custom_srt, 
                "--tts_out", output_mp3, 
                "--speaker_mapping", mapping,
                "--speed_rate", "1.0",
                "--max_speed_ratio", "1.25",
                "--ffmpeg_path", ffmpeg_bin,
                "--keep_segments"
            ])

            if custom_video:
                # 3. Video Sync
                cmd_m7 = [
                    get_python(), "mod7_video_sync.py",
                    "--video_in", custom_video,
                    "--timing_json", timing_json,
                    "--srt_vi_in", custom_srt,
                    "--aligned_dir", "temp",
                    "--video_out", video_synced,
                    "--bgm_out", bgm_synced,
                    "--srt_out", srt_synced,
                    "--vocal_vol", "1.2",
                    "--bgm_vol", "0.2",
                    "--ffmpeg_path", ffmpeg_bin
                ]
                if self.chk_auto_sep.get() or os.path.exists(bgm_clean):
                    cmd_m7 += ["--bgm_in", bgm_clean]
                tasks.append(cmd_m7)

        if not tasks:
            self.log("⚠️ Không có nhiệm vụ nào được chọn!", level="warning")
            return
            
        # --- BẮT ĐẦU: GẮN PHỤ ĐỀ VÀO VIDEO BẰNG FFMPEG ---
        if getattr(self, 'chk_hardsub', None) and self.chk_hardsub.get() and custom_video:
            video_final_hardsub = os.path.join(self.out_dir, "video_FINAL_HARDSUB.mp4")
            style_name = self.opt_sub_style.get()
            
            # Lấy thông số từ UI (ưu tiên giá trị từ việc kéo thả)
            ui_y = self.sub_y_percent
            ui_x = self.sub_x_percent
            ui_size = self.slider_font_size.get()
            ui_outline = self.slider_outline.get()
            ui_shadow = self.slider_shadow.get()

            # --- LOGIC CĂN CHỈNH TỶ LỆ CHUẨN 1080P ---
            # Sử dụng PlayResY=1080 để cố định tọa độ, giúp cỡ chữ khớp 100% video
            f_size = int(ui_size * 1.8)
            margin_v = int(ui_y * 2.0)
            out_th = int(ui_outline * 1.2)
            shad_th = int(ui_shadow * 1.2)
            
            # Tính toán MarginL/MarginR để dịch chuyển tâm chữ theo X (PlayResX=1920)
            diff = int((ui_x / 100.0) * 3840 - 1920)
            m_left = diff if diff > 0 else 0
            m_right = -diff if diff < 0 else 0

            # QUAN TRỌNG: Thêm PlayResY=1080 để FFmpeg hiểu tỷ lệ màn hình là Full HD
            base_style = f"Fontname=Arial,Fontsize={f_size},Alignment=2,MarginL={m_left},MarginR={m_right},MarginV={margin_v},Outline={out_th},Shadow={shad_th},PlayResY=1080"
            
            # Định dạng màu BGR chuẩn cho FFmpeg (Màu vàng: &H00FFFF&)
            if "Vàng" in style_name: 
                ass_style = f"{base_style},PrimaryColour=&H00FFFF&,OutlineColour=&H000000&"
            elif "hộp mờ" in style_name: 
                ass_style = f"{base_style},PrimaryColour=&HFFFFFF&,BackColour=&H80000000,BorderStyle=3,Outline=0,Shadow=0"
            elif "Neon" in style_name: 
                ass_style = f"{base_style},PrimaryColour=&HFFFFFF&,OutlineColour=&HFF00FF&"
            else:
                ass_style = f"{base_style},PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&"
            
            # --- VÁ LỖI TƯƠNG THÍCH VÀ ĐƯỜNG DẪN ---
            # Sử dụng đường dẫn tương đối để chống FFmpeg báo lỗi dấu hai chấm trên Windows
            try:
                srt_rel = os.path.relpath(srt_synced).replace('\\', '/')
                srt_escaped = srt_rel.replace(':', '\\:')
            except:
                srt_escaped = srt_synced.replace('\\', '/').replace(':', '\\\\:')
            
            # Tự động kiểm tra Card đồ họa để chọn Encoder phù hợp (Chống Crash)
            try:
                test_v = subprocess.run([ffmpeg_bin, '-encoders'], capture_output=True, text=True)
                has_nvenc = 'h264_nvenc' in test_v.stdout
            except:
                has_nvenc = False
            
            v_encoder = 'h264_nvenc' if has_nvenc else 'libx264'
            v_preset = 'p4' if has_nvenc else 'fast'
            # --------------------------------------

            cmd_hardsub = [
                ffmpeg_bin, '-y', 
                '-hwaccel', 'auto', '-i', video_synced,
                '-vf', f"subtitles='{srt_escaped}':force_style='{ass_style}'",
                '-c:v', v_encoder, '-preset', v_preset, '-cq', '26', '-c:a', 'copy', video_final_hardsub
            ]
            tasks.append(cmd_hardsub)
            
            success_msg = f"DỰ ÁN ĐÃ HOÀN TẤT!\n\nVideo Full Phụ Đề của bạn tại:\n👉 {os.path.basename(video_final_hardsub)}"
        else:
            success_msg = f"DỰ ÁN ĐÃ HOÀN TẤT!\n\nBạn có thể đưa bộ file này vào CapCut:\n1. Video: {os.path.basename(video_synced)}\n2. Nhạc nền: {os.path.basename(bgm_synced)}\n3. Phụ đề: {os.path.basename(srt_synced)}"
        # --- KẾT THÚC: GẮN PHỤ ĐỀ ---

        threading.Thread(target=self._run_cmds, args=(tasks, success_msg, None, None)).start()

    def run_blur_only(self):
        if not self.video_path:
            messagebox.showerror("Lỗi", "Vui lòng Nạp Video trước!")
            return
        if not self.roi_coords:
            messagebox.showerror("Lỗi", "Vui lòng Vẽ Vùng Mờ trên video trước!")
            return
            
        ffmpeg_bin = self.entry_ffmpeg.get().strip()
        if not ffmpeg_bin: ffmpeg_bin = "ffmpeg"

             
        video_out = os.path.join(self.out_dir, "video_blurred.mp4")
        
        self.log("\n>>> BẮT ĐẦU LÀM MỜ SUB (Bước 1)...")
        cmd = [
            get_python(), "mod8_blur_sub.py",
            "--video_in", self.video_path,
            "--video_out", video_out,
            "--x", str(self.roi_coords[0]),
            "--y", str(self.roi_coords[1]),
            "--w", str(self.roi_coords[2]),
            "--h", str(self.roi_coords[3]),
            "--blur", "25",
            "--ffmpeg_path", ffmpeg_bin
        ]
        
        def on_blur_done():
            # Cũng gom Messagebox vào luồng chính để tránh crash macOS/Windows
            def _gui_action():
                if messagebox.askyesno("Thành công", f"Đã làm mờ xong.\nBạn có muốn dùng video này làm lồng tiếng không?"):
                    self.video_path = video_out
                    self.entry_video_t3.delete(0, tk.END)
                    self.entry_video_t3.insert(0, video_out)
                    self.cap = cv2.VideoCapture(video_out)
                    self._update_roi_frame(0)
            self.after(0, _gui_action)

        threading.Thread(target=self._run_cmds, args=([cmd], "LÀM MỜ HOÀN TẤT!", None, None, on_blur_done)).start()


    def _run_cmds(self, cmds, success_msg, final_temp=None, final_target=None, callback=None):
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
                self.active_processes.append(process) # Theo dõi để tắt khi đóng app
                for line in iter(process.stdout.readline, ""):
                    self.log(line.strip())
                rc = process.wait()
                if process in self.active_processes:
                    self.active_processes.remove(process)
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
                            # TỐI ƯU THEO YÊU CẦU: Xóa tất cả các file rác, chỉ giữ lại 3 file cuối cùng
                            keep_files = ["video_synced.mp4", "bgm_synced.wav", "vi_synced.srt"]
                            cleaned_count = 0
                            
                            # Xóa các file trong output/
                            for f in os.listdir(self.out_dir):
                                if f not in keep_files:
                                    if f.startswith("_") or f in ["tts_timing.json", "voices.wav", "bgm_clean.wav"]:
                                        f_path = os.path.join(self.out_dir, f)
                                        try:
                                            if os.path.isfile(f_path):
                                                os.remove(f_path)
                                                cleaned_count += 1
                                            elif os.path.isdir(f_path):
                                                import shutil
                                                shutil.rmtree(f_path)
                                                cleaned_count += 1
                                        except: pass

                            
                            # XEM THÊM: Xóa sạch file trong folder temp/ nhưng giữ lại folder theo yêu cầu
                            if os.path.exists("temp"):
                                try:
                                    for f in os.listdir("temp"):
                                        f_path = os.path.join("temp", f)
                                        if os.path.isfile(f_path):
                                            os.remove(f_path)
                                    cleaned_count += 1
                                    self.log("🗑️ Đã làm sạch các file trong thư mục temp/")
                                except: pass

                                
                            if cleaned_count > 0:
                                self.log(f"🗑️ Đã dọn dẹp dự án (xóa {cleaned_count} mục tạm), chỉ giữ lại Video, BGM và Sub.")

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
        
        # Rename result if needed
        if final_temp and final_target and os.path.exists(final_temp):
            import shutil
            try:
                if os.path.exists(final_target): os.remove(final_target)
                shutil.move(final_temp, final_target)
                self.log(f"✅ Đã lưu kết quả tại: {final_target}", level="success")
            except Exception as e:
                self.log(f"⚠️ Lỗi khi đổi tên file kết quả: {e}", level="warning")

        self.log(success_msg, level="success")
        if callback:
            callback()

    def on_closing(self):
        """Xử lý khi đóng cửa sổ: Tắt toàn bộ tiến trình chạy ngầm."""
        print("\n[!] Đang đóng ứng dụng, vui lòng chờ giây lát để dọn dẹp...")
        
        # 1. Tắt các process do app khởi tạo (Demucs, Whisper, Video Sync...)
        if hasattr(self, 'active_processes'):
            for p in self.active_processes:
                try:
                    if p.poll() is None: # Nếu vẫn đang chạy
                        if sys.platform == "win32":
                            # Dùng taskkill /T để diệt cả cây process
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                        else:
                            p.terminate()
                except:
                    pass
        
        # 2. Quét sạch FFmpeg một lần nữa cho chắc
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], capture_output=True)
        except:
            pass

        # 3. Giải phóng OpenCV
        if hasattr(self, 'cap') and self.cap:
            try:
                self.cap.release()
            except:
                pass

        self.destroy()
        sys.exit(0)


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
                try:
                    import mod3_translate
                    mod3_translate.main()
                except ImportError:
                    print("Module mod3_translate.py không tồn tại.")
            elif script == "mod4_tts_dubbing.py":
                import mod4_tts_dubbing
                mod4_tts_dubbing.main()

            elif script == "mod5_mux_video.py":
                try:
                    import mod5_mux_video
                    mod5_mux_video.main()
                except ImportError:
                    print("Module mod5_mux_video.py không tồn tại.")
            elif script == "mod6_capcut_export.py":
                try:
                    import mod6_capcut_export
                    mod6_capcut_export.main()
                except ImportError:
                    print("Module mod6_capcut_export.py không tồn tại.")
            elif script == "mod7_video_sync.py":
                import mod7_video_sync
                mod7_video_sync.main()
            elif script == "tool_get_blur_box.py":
                try:
                    import tool_get_blur_box
                    from tool_get_blur_box import main
                    main()
                except ImportError:
                    print("Module tool_get_blur_box.py không tồn tại.")
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
