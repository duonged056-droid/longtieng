import os
import sys

# PHIÊN BẢN ĐẶC TRỊ - ÉP DÙNG GPU NGAY TỪ DÒNG ĐẦU TIÊN
if sys.platform == "win32":
    import site
    # Tìm kiếm trong tất cả các thư mục site-packages khả thi
    possible_paths = site.getsitepackages() + [os.path.join(os.path.dirname(os.path.abspath(__file__)), "env", "Lib", "site-packages")]
    for sp in possible_paths:
        nvidia_base = os.path.join(sp, "nvidia")
        if os.path.exists(nvidia_base):
            for sub_lib in ["cublas", "cudnn", "cuda_nvrtc"]:
                bin_path = os.path.join(nvidia_base, sub_lib, "bin")
                if os.path.exists(bin_path):
                    try:
                        os.add_dll_directory(bin_path)
                        # Ghim thêm vào PATH để chắc chắn 100%
                        if bin_path not in os.environ["PATH"]:
                            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                    except Exception:
                        pass

import torch

# KIỂM TRA TRẠNG THÁI GPU
if torch.cuda.is_available():
    print(f"✅ ĐÃ NHẬN CARD ĐỒ HỌA: {torch.cuda.get_device_name(0)}")
    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
else:
    print("❌ CẢNH BÁO: CHƯA NHẬN CARD ĐỒ HỌA. HỆ THỐNG ĐANG CHẠY BẰNG CPU (RẤT CHẬM)")

import gradio as gr
import tkinter as tk
from tkinter import filedialog
import shutil
import subprocess
from PIL import Image, ImageDraw

# Thêm đường dẫn cho các submodule
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "CosyVoice"))
sys.path.append(os.path.join(ROOT_DIR, "CosyVoice", "third_party", "Matcha-TTS"))

from tools.step000_video_downloader import download_from_url
from tools.step010_demucs_vr import separate_all_audio_under_folder
from tools.step020_asr import transcribe_all_audio_under_folder
from tools.step030_translation import translate_all_transcript_under_folder
from tools.step040_tts import generate_all_wavs_under_folder
from tools.step050_synthesize_video import synthesize_all_video_under_folder
from tools.do_everything import do_everything
from tools.utils import SUPPORT_VOICE, srt_to_json

def get_blur_preview(video_input, blur_height, blur_y):
    if not video_input:
        return None
    
    # temp path
    frame_path = "temp/preview_frame.jpg"
    os.makedirs("temp", exist_ok=True)
    
    # Extract 1 frame with ffmpeg
    try:
        subprocess.run([
            'ffmpeg', '-ss', '00:00:01', '-i', video_input, 
            '-frames:v', '1', '-q:v', '2', frame_path, '-y'
        ], check=True, capture_output=True)
    except:
        # fallback to 0s if 1s fails
        try:
            subprocess.run([
                'ffmpeg', '-i', video_input, 
                '-frames:v', '1', '-q:v', '2', frame_path, '-y'
            ], check=True, capture_output=True)
        except:
            return None
        
    if not os.path.exists(frame_path):
        return None
        
    img = Image.open(frame_path)
    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    y1 = h * blur_y / 100
    y2 = y1 + (h * blur_height / 100)
    
    # Draw a semi-transparent green rectangle
    # Draw outline
    draw.rectangle([0, y1, w, y2], outline=(0, 255, 0, 255), width=5)
    # Draw fill
    overlay = Image.new('RGBA', img.size, (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, y1, w, y2], fill=(0, 255, 0, 60))
    
    img = Image.alpha_composite(img, overlay)
    
    return img.convert("RGB")

def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder_selected = filedialog.askdirectory()
    root.destroy()
    return folder_selected

def webui_save_local(local_path, target_dir, target_name=None):
    if local_path is None:
        return None
    os.makedirs(target_dir, exist_ok=True)
    filename = target_name if target_name else os.path.basename(local_path)
    target_path = os.path.join(target_dir, filename)
    shutil.copy(local_path, target_path)
    return target_path

def webui_separate_audio(sep_folder, sep_model, sep_device, sep_progress, sep_shifts, local_video, pr=gr.Progress()):
    if local_video:
        webui_save_local(local_video, sep_folder, "download.mp4")
    def progress_callback(percent, message):
        pr(percent / 100, desc=message)
    return separate_all_audio_under_folder(sep_folder, sep_model, sep_device, sep_progress, sep_shifts, progress_callback=progress_callback)

def webui_transcribe_audio(asr_folder, asr_method, asr_size, asr_device, asr_batch, asr_diar, asr_min, asr_max, local_video, pr=gr.Progress()):
    if local_video:
        webui_save_local(local_video, asr_folder, "download.mp4")
    def progress_callback(percent, message):
        pr(percent / 100, desc=message)
    return transcribe_all_audio_under_folder(asr_folder, asr_method, asr_size, asr_device, asr_batch, asr_diar, asr_min, asr_max, progress_callback=progress_callback)

def webui_translate_srt(trans_folder, trans_method, trans_lang, local_srt, pr=gr.Progress()):
    if local_srt:
        # Lưu file srt
        webui_save_local(local_srt, trans_folder)
        # Chuyển đổi srt sang json để module translation có thể đọc được
        srt_to_json(local_srt, os.path.join(trans_folder, 'transcript.json'))
    def progress_callback(percent, message):
        pr(percent / 100, desc=message)
    return translate_all_transcript_under_folder(trans_folder, trans_method, trans_lang, progress_callback=progress_callback)

def webui_generate_wavs(tts_folder, tts_method, tts_lang, tts_voice, local_srt, pr=gr.Progress()):
    if local_srt:
        # Lưu file srt
        webui_save_local(local_srt, tts_folder)
        # Chuyển đổi srt sang json để module tts có thể đọc được
        # Cần cả transcript.json và translation.json để đảm bảo tính tương thích
        srt_to_json(local_srt, os.path.join(tts_folder, 'transcript.json'))
        srt_to_json(local_srt, os.path.join(tts_folder, 'translation.json'))
    def progress_callback(percent, message):
        pr(percent / 100, desc=message)
    return generate_all_wavs_under_folder(tts_folder, tts_method, tts_lang, tts_voice, progress_callback=progress_callback)

def webui_synthesize_video_wrapper(syn_folder, syn_sub, syn_speed, syn_fps, syn_bgm, syn_bgm_vol, syn_vid_vol, syn_res, blur_subtitles, blur_height, blur_y, local_video, local_srt, pr=gr.Progress()):
    if local_video:
        webui_save_local(local_video, syn_folder, "download.mp4")
    if local_srt:
        webui_save_local(local_srt, syn_folder)
        # Chuyển đổi srt sang translation.json để module synthesize có thể đọc được
        srt_to_json(local_srt, os.path.join(syn_folder, 'translation.json'))
    def progress_callback(percent, message):
        pr(percent / 100, desc=message)
    return synthesize_all_video_under_folder(syn_folder, syn_sub, syn_speed, syn_fps, syn_bgm, syn_bgm_vol, syn_vid_vol, syn_res, progress_callback=progress_callback, blur_subtitles=blur_subtitles, blur_height=blur_height, blur_y=blur_y)

def webui_do_everything(root_folder, url, num_videos, resolution,
                        demucs_model, device, shifts,
                        asr_method, whisper_model, batch_size, diarization, whisper_min_speakers, whisper_max_speakers,
                        translation_method, translation_target_language,
                        tts_method, tts_target_language, voice,
                        subtitles, speed_up, fps, background_music, bgm_volume, video_volume, target_resolution,
                        max_workers, max_retries, blur_subtitles, blur_height, blur_y, local_video, local_srt, skip_translation, pr=gr.Progress()):
    
    def progress_callback(percent, message):
        pr(percent / 100, desc=message)
    
    # Ưu tiên sử dụng video cục bộ nếu có
    if local_video is not None:
        url = local_video
        
    # Xử lý file SRT cục bộ
    srt_path = local_srt if local_srt is not None else None
    
    # Kết quả
    status, video = do_everything(
        root_folder=root_folder,
        url=url,
        num_videos=num_videos,
        resolution=resolution,
        demucs_model=demucs_model,
        device=device,
        shifts=shifts,
        asr_method=asr_method,
        whisper_model=whisper_model,
        batch_size=batch_size,
        diarization=diarization,
        whisper_min_speakers=whisper_min_speakers,
        whisper_max_speakers=whisper_max_speakers,
        translation_method=translation_method,
        translation_target_language=translation_target_language,
        tts_method=tts_method,
        tts_target_language=tts_target_language,
        voice=voice,
        subtitles=subtitles,
        speed_up=speed_up,
        fps=fps,
        background_music=background_music,
        bgm_volume=bgm_volume,
        video_volume=video_volume,
        target_resolution=target_resolution,
        max_workers=max_workers,
        max_retries=max_retries,
        progress_callback=progress_callback,
        srt_path=srt_path,
        skip_asr=(srt_path is not None),
        skip_translation=skip_translation,
        blur_subtitles=blur_subtitles,
        blur_height=blur_height,
        blur_y=blur_y
    )
    return status, video

with gr.Blocks(theme=gr.themes.Soft(), title='Linly-Dubbing Tiếng Việt') as app:
    hf_token = os.getenv('HF_TOKEN')
    if not hf_token:
        gr.HTML("""
            <div style="background-color: #ffe6e6; border-left: 6px solid #f44336; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
                <p style="color: #d32f2f; font-weight: bold; margin: 0; font-size: 1.1em;">⚠️ Cảnh báo: Thiếu mã HF_TOKEN (Hugging Face Token)</p>
                <p style="margin: 8px 0 0 0; color: #333;">Dự án yêu cầu <b>HF_TOKEN</b> để tải mô hình VAD và Diarization từ Hugging Face. 
                Vui lòng làm theo hướng dẫn trong file <code>implementation_plan.md</code> để cài đặt.</p>
            </div>
        """)
    gr.Markdown("# 🎬 Công cụ AI Lồng tiếng/Dịch thuật video đa ngôn ngữ - Linly-Dubbing")
    
    with gr.Tab("Tự động hóa Một lần nhấp"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    root_folder = gr.Textbox(label='Thư mục đầu ra video', value='videos', scale=4)
                    btn_select_folder = gr.Button("📂 Chọn Thư mục", scale=1)
                
                url = gr.Textbox(label='URL Video (Youtube/Bilibili)', placeholder='Nhập link video tại đây...', value='')
                
                with gr.Row():
                    local_video = gr.File(label='Hoặc tải lên Video cục bộ', file_count='single', file_types=['.mp4', '.avi', '.mkv'])
                    local_srt = gr.File(label='Tải lên file SRT (Phụ đề gốc)', file_count='single', file_types=['.srt'])
                
                skip_translation = gr.Checkbox(label='Lồng tiếng trực tiếp từ SRT (Không dịch lại)', value=False)
                
                with gr.Accordion("⚙️ Cấu hình nâng cao", open=False):
                    num_videos = gr.Slider(minimum=1, maximum=100, step=1, label='Số lượng video tối đa (nếu tải playlist)', value=5)
                    resolution = gr.Radio(['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'], label='Độ phân giải tải xuống ưu tiên', value='1080p')
                    
                    gr.Markdown("### 🔊 Tách giọng & Nhận dạng (ASR)")
                    demucs_model = gr.Radio(['htdemucs', 'htdemucs_ft', 'htdemucs_6s', 'hdemucs_mmi', 'mdx', 'mdx_extra', 'mdx_q', 'mdx_extra_q', 'SIG'], label='Mô hình tách nhạc nền (Demucs)', value='htdemucs_ft')
                    device = gr.Radio(['auto', 'cuda', 'cpu'], label='Thiết bị xử lý (CPU/GPU)', value='auto')
                    shifts = gr.Slider(minimum=0, maximum=10, step=1, label='Số lần dịch chuyển (Shifts - tăng chất lượng)', value=5)
                    
                    asr_method = gr.Dropdown(['WhisperX', 'FunASR'], label='Phương pháp nhận dạng giọng nói', value='WhisperX')
                    whisper_model = gr.Radio(['large', 'medium', 'small', 'base', 'tiny'], label='Kích thước mô hình Whisper', value='large')
                    batch_size = gr.Slider(minimum=1, maximum=128, step=1, label='Kích thước lô (Batch Size)', value=4)
                    diarization = gr.Checkbox(label='Tách biệt các người nói (Diarization)', value=True)
                    whisper_min_speakers = gr.Radio([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], label='Số người nói tối thiểu', value=None)
                    whisper_max_speakers = gr.Radio([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], label='Số người nói tối đa', value=None)

                gr.Markdown("### 🌐 Dịch thuật & Lồng tiếng (TTS)")
                with gr.Row():
                    translation_method = gr.Dropdown(['OpenAI', 'Gemini', 'LLM', 'Google Translate', 'Bing Translate', 'Ernie'], label='Công cụ dịch thuật', value='Gemini')
                    translation_target_language = gr.Dropdown(['Tiếng Việt', 'Tiếng Trung (Giản thể)', 'Tiếng Trung (Phồn thể)', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn'], label='Ngôn ngữ đích', value='Tiếng Việt')
                
                with gr.Row():
                    tts_method = gr.Dropdown(['xtts', 'cosyvoice', 'EdgeTTS'], label='Công nghệ lồng tiếng (TTS)', value='EdgeTTS')
                    tts_target_language = gr.Dropdown(['Tiếng Việt', 'Tiếng Trung', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn', 'Tiếng Tây Ban Nha', 'Tiếng Pháp'], label='Ngôn ngữ lồng tiếng', value='Tiếng Việt')
                
                voice = gr.Dropdown(SUPPORT_VOICE, value='vi-VN-HoaiMyNeural', label='Chọn giọng nói (EdgeTTS)')

                with gr.Accordion("🎬 Cấu hình Video đầu ra", open=False):
                    subtitles = gr.Checkbox(label='Chèn phụ đề vào video', value=True)
                    speed_up = gr.Slider(minimum=0.5, maximum=2, step=0.05, label='Tốc độ video tổng thể', value=1.00)
                    fps = gr.Slider(minimum=1, maximum=60, step=1, label='FPS đầu ra', value=30)
                    background_music = gr.Audio(label='Nhạc nền thay thế (BGM)', sources=['upload'], type='filepath')
                    bgm_volume = gr.Slider(minimum=0, maximum=1, step=0.05, label='Âm lượng nhạc nền', value=0.5)
                    video_volume = gr.Slider(minimum=0, maximum=1, step=0.05, label='Âm lượng giọng video gốc', value=1.0)
                    target_resolution = gr.Radio(['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'], label='Độ phân giải video cuối', value='1080p')
                    max_workers = gr.Slider(minimum=1, maximum=100, step=1, label='Số lượng luồng xử lý (Workers)', value=1)
                    max_retries = gr.Slider(minimum=1, maximum=10, step=1, label='Số lần thử lại khi lỗi', value=3)
                    
                    gr.Markdown("### 🌫️ Thiết lập làm mờ phụ đề cũ")
                    blur_subtitles = gr.Checkbox(label='Làm mờ phụ đề cũ', value=False)
                    with gr.Row(visible=False) as blur_settings:
                        with gr.Column():
                            blur_height = gr.Slider(minimum=0, maximum=100, step=1, label='Chiều cao vùng mờ (%)', value=15)
                            blur_y = gr.Slider(minimum=0, maximum=100, step=1, label='Vị trí dọc (%)', value=85)
                            btn_preview_blur = gr.Button("👁️ Xem trước vùng mờ")
                        blur_preview_img = gr.Image(label='Minh họa vùng mờ', interactive=False)

                btn_run = gr.Button("🚀 BẮT ĐẦU XỬ LÝ", variant="primary")

            with gr.Column():
                output_status = gr.Textbox(label='Trạng thái tiến trình')
                output_video = gr.Video(label='Video kết quả hoàn thiện')

        btn_select_folder.click(select_folder, outputs=root_folder)
        btn_run.click(
            webui_do_everything,
            inputs=[
                root_folder, url, num_videos, resolution,
                demucs_model, device, shifts,
                asr_method, whisper_model, batch_size, diarization, whisper_min_speakers, whisper_max_speakers,
                translation_method, translation_target_language,
                tts_method, tts_target_language, voice,
                subtitles, speed_up, fps, background_music, bgm_volume, video_volume, target_resolution,
                max_workers, max_retries, blur_subtitles, blur_height, blur_y, local_video, local_srt, skip_translation
            ],
            outputs=[output_status, output_video]
        )
        
        # Blur settings logic
        def toggle_blur(choice):
            return gr.update(visible=choice)
        blur_subtitles.change(toggle_blur, inputs=blur_subtitles, outputs=blur_settings)
        
        # Link preview button
        def handle_preview(local_v, url_v, bh, by):
            video_path = local_v if local_v else url_v
            return get_blur_preview(video_path, bh, by)
            
        btn_preview_blur.click(handle_preview, inputs=[local_video, url, blur_height, blur_y], outputs=blur_preview_img)

    with gr.Tab("Tải xuống Video"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    dl_folder = gr.Textbox(label='Thư mục lưu video', value='videos', scale=4)
                    btn_dl_folder = gr.Button("📂 Chọn", scale=1)
                dl_url = gr.Textbox(label='Link Video', placeholder='Youtube/Bilibili...', value='')
                dl_resolution = gr.Radio(['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'], label='Độ phân giải', value='1080p')
                dl_num = gr.Slider(minimum=1, maximum=100, step=1, label='Số lượng video tối đa', value=1)
                btn_dl = gr.Button("📥 Bắt đầu tải", variant="primary")
            with gr.Column():
                dl_status = gr.Textbox(label='Trạng thái tải')
                dl_video = gr.Video(label='Xem trước video')
                dl_info = gr.Json(label='Thông tin Video (Metadata)')
        
        btn_dl_folder.click(select_folder, outputs=dl_folder)
        btn_dl.click(download_from_url, inputs=[dl_url, dl_folder, dl_resolution, dl_num], outputs=[dl_status, dl_video, dl_info])
    
    with gr.Tab("Tách nhạc (Separation)"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    sep_folder = gr.Textbox(label='Thư mục chứa video', value='videos', scale=4)
                    btn_sep_folder = gr.Button("📂 Chọn", scale=1)
                
                sep_video = gr.File(label='Hoặc tải lên Video cục bộ', file_count='single', file_types=['.mp4', '.avi', '.mkv'])
                
                sep_model = gr.Radio(['htdemucs', 'htdemucs_ft', 'htdemucs_6s', 'hdemucs_mmi', 'mdx', 'mdx_extra', 'mdx_q', 'mdx_extra_q', 'SIG'], label='Mô hình Demucs', value='htdemucs_ft')
                sep_device = gr.Radio(['auto', 'cuda', 'cpu'], label='Thiết bị xử lý', value='auto')
                sep_progress = gr.Checkbox(label='Hiển thị thanh tiến trình', value=True)
                sep_shifts = gr.Slider(minimum=0, maximum=10, step=1, label='Số lần dịch chuyển (Shifts)', value=5)
                btn_sep = gr.Button("🎸 Tách Vocal & Background", variant="primary")
            with gr.Column():
                sep_status = gr.Text(label='Trạng thái')
                sep_vocal = gr.Audio(label='Giọng nói (Vocal)')
                sep_bgm = gr.Audio(label='Nhạc nền (Background Music)')
        
        btn_sep_folder.click(select_folder, outputs=sep_folder)
        btn_sep.click(webui_separate_audio, inputs=[sep_folder, sep_model, sep_device, sep_progress, sep_shifts, sep_video], outputs=[sep_status, sep_vocal, sep_bgm])

    with gr.Tab("Nhận dạng Giọng nói (ASR)"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    asr_folder = gr.Textbox(label='Thư mục chứa video/audio', value='videos', scale=4)
                    btn_asr_folder = gr.Button("📂 Chọn", scale=1)
                
                asr_video = gr.File(label='Tải lên tệp Video/Audio', file_count='single', file_types=['.mp4', '.avi', '.mkv', '.wav', '.mp3'])
                
                asr_method_tab = gr.Dropdown(['WhisperX', 'FunASR'], label='Mô hình nhận dạng', value='WhisperX')
                asr_size = gr.Radio(['large', 'medium', 'small', 'base', 'tiny'], label='Kích thước mô hình', value='large')
                asr_device = gr.Radio(['auto', 'cuda', 'cpu'], label='Thiết bị', value='auto')
                asr_batch = gr.Slider(minimum=1, maximum=128, step=1, label='Kích thước lô', value=4)
                asr_diar = gr.Checkbox(label='Phân biệt người nói', value=True)
                asr_min = gr.Radio([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], label='Số người nói tối thiểu', value=None)
                asr_max = gr.Radio([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], label='Số người nói tối đa', value=None)
                btn_asr = gr.Button("✍️ Bắt đầu nhận dạng", variant="primary")
            with gr.Column():
                asr_status = gr.Text(label='Trạng thái')
                asr_detail = gr.Json(label='Kết quả nhận dạng (JSON)')
        
        btn_asr_folder.click(select_folder, outputs=asr_folder)
        btn_asr.click(webui_transcribe_audio, inputs=[asr_folder, asr_method_tab, asr_size, asr_device, asr_batch, asr_diar, asr_min, asr_max, asr_video], outputs=[asr_status, asr_detail])

    with gr.Tab("Dịch thuật Phụ đề"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    trans_folder = gr.Textbox(label='Thư mục lưu trữ', value='videos', scale=4)
                    btn_trans_folder = gr.Button("📂 Chọn", scale=1)
                
                trans_srt = gr.File(label='Tải lên file SRT (Phụ đề)', file_count='single', file_types=['.srt'])
                
                trans_method_tab = gr.Dropdown(['OpenAI', 'Gemini', 'LLM', 'Google Translate', 'Bing Translate', 'Ernie'], label='Công cụ dịch thuật', value='Gemini')
                trans_lang_tab = gr.Dropdown(['Tiếng Việt', 'Tiếng Trung (Giản thể)', 'Tiếng Trung (Phồn thể)', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn'], label='Ngôn ngữ đích', value='Tiếng Việt')
                btn_trans = gr.Button("🎨 Bắt đầu dịch thuật", variant="primary")
            with gr.Column():
                trans_status = gr.Text(label='Trạng thái')
                trans_summary = gr.Json(label='Tóm tắt nội dung')
                trans_detail = gr.Json(label='Chi tiết dịch (Từng dòng)')
        
        btn_trans_folder.click(select_folder, outputs=trans_folder)
        btn_trans.click(webui_translate_srt, inputs=[trans_folder, trans_method_tab, trans_lang_tab, trans_srt], outputs=[trans_status, trans_summary, trans_detail])

    with gr.Tab("Tổng hợp Tiếng (TTS)"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    tts_folder = gr.Textbox(label='Thư mục làm việc', value='videos', scale=4)
                    btn_tts_folder = gr.Button("📂 Chọn", scale=1)
                
                tts_srt = gr.File(label='Tải lên file SRT (Phụ đề đã dịch)', file_count='single', file_types=['.srt'])
                
                tts_method_tab = gr.Dropdown(['xtts', 'cosyvoice', 'EdgeTTS'], label='Phương pháp tổng hợp', value='EdgeTTS')
                tts_lang_tab = gr.Dropdown(['Tiếng Việt', 'Tiếng Trung', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn', 'Tiếng Tây Ban Nha', 'Tiếng Pháp'], label='Ngôn ngữ', value='Tiếng Việt')
                tts_voice_tab = gr.Dropdown(SUPPORT_VOICE, value='vi-VN-HoaiMyNeural', label='Chọn giọng nói')
                btn_tts = gr.Button("🎙️ Bắt đầu lồng tiếng", variant="primary")
            with gr.Column():
                tts_status = gr.Text(label='Trạng thái')
                tts_wav = gr.Audio(label='Giọng nói lồng tiếng')
                tts_orig = gr.Audio(label='Giọng nói gốc (nếu có)')
        
        btn_tts_folder.click(select_folder, outputs=tts_folder)
        btn_tts.click(webui_generate_wavs, inputs=[tts_folder, tts_method_tab, tts_lang_tab, tts_voice_tab, tts_srt], outputs=[tts_status, tts_wav, tts_orig])

    with gr.Tab("Ghép nối Video cuối"):
        with gr.Row():
            with gr.Column():
                with gr.Row():
                    syn_folder = gr.Textbox(label='Thư mục chứa tệp xử lý', value='videos', scale=4)
                    btn_syn_folder = gr.Button("📂 Chọn", scale=1)
                
                with gr.Row():
                    syn_video_local = gr.File(label='Tải lên Video nền', file_count='single', file_types=['.mp4', '.avi', '.mkv'])
                    syn_srt_local = gr.File(label='Tải lên Phụ đề hoàn chỉnh', file_count='single', file_types=['.srt'])
                
                syn_sub = gr.Checkbox(label='Hiển thị phụ đề cứng', value=True)
                syn_speed = gr.Slider(minimum=0.5, maximum=2, step=0.05, label='Điều chỉnh tốc độ', value=1.00)
                syn_fps = gr.Slider(minimum=1, maximum=60, step=1, label='FPS đầu ra', value=30)
                syn_bgm = gr.Audio(label='Nhạc nền bổ sung', sources=['upload'], type='filepath')
                syn_bgm_vol = gr.Slider(minimum=0, maximum=1, step=0.05, label='Âm lượng nhạc nền', value=0.5)
                syn_vid_vol = gr.Slider(minimum=0, maximum=1, step=0.05, label='Âm lượng video gốc', value=1.0)
                syn_res = gr.Radio(['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'], label='Độ phân giải', value='1080p')
                
                gr.Markdown("### 🌫️ Thiết lập làm mờ phụ đề cũ")
                syn_blur_subtitles = gr.Checkbox(label='Làm mờ phụ đề cũ', value=False)
                with gr.Row(visible=False) as syn_blur_settings:
                    with gr.Column():
                        syn_blur_height = gr.Slider(minimum=0, maximum=100, step=1, label='Chiều cao vùng mờ (%)', value=15)
                        syn_blur_y = gr.Slider(minimum=0, maximum=100, step=1, label='Vị trí dọc (%)', value=85)
                        syn_btn_preview_blur = gr.Button("👁️ Xem trước vùng mờ")
                    syn_blur_preview_img = gr.Image(label='Minh họa vùng mờ', interactive=False)
                
                btn_syn = gr.Button("🎬 Bắt đầu xuất Video", variant="primary")
            with gr.Column():
                syn_status = gr.Text(label='Trạng thái xuất video')
                syn_video = gr.Video(label='Video thành phẩm cuối cùng')
        
        btn_syn_folder.click(select_folder, outputs=syn_folder)
        btn_syn.click(webui_synthesize_video_wrapper, 
                     inputs=[syn_folder, syn_sub, syn_speed, syn_fps, syn_bgm, syn_bgm_vol, syn_vid_vol, syn_res, syn_blur_subtitles, syn_blur_height, syn_blur_y, syn_video_local, syn_srt_local], 
                     outputs=[syn_status, syn_video])
        
        # Sync visibility
        syn_blur_subtitles.change(toggle_blur, inputs=syn_blur_subtitles, outputs=syn_blur_settings)
        # Link preview
        syn_btn_preview_blur.click(handle_preview, inputs=[syn_video_local, syn_folder, syn_blur_height, syn_blur_y], outputs=syn_blur_preview_img)

if __name__ == '__main__':
    app.launch(
        server_name="127.0.0.1", 
        share=True,
        inbrowser=True
    )