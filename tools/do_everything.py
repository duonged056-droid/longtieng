import json
import os
import time
import traceback

import torch
from loguru import logger
from .step000_video_downloader import get_info_list_from_url, download_single_video, get_target_folder
from .step010_demucs_vr import separate_all_audio_under_folder, init_demucs, release_model
from .step020_asr import transcribe_all_audio_under_folder
from .utils import srt_to_json, cleanup_folder
from .step021_asr_whisperx import init_whisperx, init_diarize, release_whisperx
from .step022_asr_funasr import init_funasr
from .step030_translation import translate_all_transcript_under_folder
from .step040_tts import generate_all_wavs_under_folder
from .step042_tts_xtts import init_TTS, release_xtts
from .step043_tts_cosyvoice import init_cosyvoice, release_cosyvoice
from .step050_synthesize_video import synthesize_all_video_under_folder
from concurrent.futures import ThreadPoolExecutor, as_completed

# Track model initialization status
models_initialized = {
    'demucs': False,
    'xtts': False,
    'cosyvoice': False,
    'whisperx': False,
    'diarize': False,
    'funasr': False
}


def get_available_gpu_memory():
    """Get the currently available GPU memory size (GB)"""
    try:
        if torch.cuda.is_available():
            # Get available memory for the current device
            free_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)
            return free_memory / (1024 ** 3)  # Convert to GB
        return 0  # If no GPU or CUDA is unavailable
    except Exception:
        return 0  # Return 0 on error


def initialize_models(tts_method, asr_method, diarization):
    """
    Initialize the required models.
    Models are only initialized on the first call to avoid redundant loading.
    """
    # Use global state to track initialized models
    global models_initialized

    with ThreadPoolExecutor() as executor:
        try:
            # LOẠI BỎ VIỆC NẠP SẴN TẤT CẢ MÔ HÌNH ĐỂ TIẾT KIỆM VRAM
            # Các mô hình sẽ được nạp theo kiểu "Lazy Load" trong process_video
            pass

        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"Khởi tạo mô hình thất bại: {str(e)}\n{stack_trace}")
            # Reset initialization state on error
            models_initialized = {key: False for key in models_initialized}
            release_model()  # Release loaded models
            raise


def process_video(info, root_folder, resolution,
                  demucs_model, device, shifts,
                  asr_method, whisper_model, batch_size, diarization, whisper_min_speakers, whisper_max_speakers,
                  translation_method, translation_target_language,
                  tts_method, tts_target_language, voice,
                  subtitles, speed_up, fps, background_music, bgm_volume, video_volume,
                  target_resolution, max_retries, progress_callback=None, srt_path=None, skip_asr=False, skip_translation=False, blur_subtitles=False, blur_height=15, blur_y=85):
    """
    Processing the full workflow for a single video with progress callback support.

    Args:
        progress_callback: Callback function for reporting progress and status, 
                          format: progress_callback(progress_percent, status_message)
    """
    local_time = time.localtime()

    # Define progress stages and weights
    stages = [
        ("Đang tải video...", 10),  # 10%
        ("Đang tách nhạc nền & giọng nói...", 15),  # 15%
        ("Đang nhận dạng giọng nói AI...", 20),  # 20%
        ("Đang dịch phụ đề...", 25),  # 25%
        ("Đang lồng tiếng Việt AI...", 20),  # 20%
        ("Đang hoàn thành video...", 10)  # 10%
    ]

    current_stage = 0
    progress_base = 0

    # 报告初始进度
    if progress_callback:
        progress_callback(0, "Chuẩn bị xử lý...")

    for retry in range(max_retries):
        try:
            # Report stage: Download
            stage_name, stage_weight = stages[current_stage]
            if progress_callback:
                progress_callback(progress_base, stage_name)

            if isinstance(info, str) and info.endswith('.mp4'):
                folder = os.path.dirname(info)
            else:
                folder = get_target_folder(info, root_folder)
                if folder is None:
                    error_msg = f'Không thể truy cập thư mục đích: {info["title"]}'
                    logger.warning(error_msg)
                    return False, None, error_msg

                folder = download_single_video(info, root_folder, resolution)
                if folder is None:
                    error_msg = f'下载视频失败: {info["title"]}'
                    logger.warning(error_msg)
                    return False, None, error_msg

            logger.info(f'处理视频: {folder}')

            # 完成下载阶段，进入人声分离阶段
            current_stage += 1
            progress_base += stage_weight
            stage_name, stage_weight = stages[current_stage]
            if progress_callback:
                progress_callback(progress_base, stage_name)

            try:
                # Bước 1: Nạp Demucs
                init_demucs()
                status, vocals_path, _ = separate_all_audio_under_folder(
                    folder, model_name=demucs_model, device=device, progress=True, shifts=shifts)
                logger.info(f'Tách nhạc nền hoàn tất: {vocals_path}')
                
                # Bước 2: Giải phóng Demucs ngay lập tức để dành VRAM cho WhisperX
                release_model()
            except Exception as e:
                stack_trace = traceback.format_exc()
                error_msg = f'Tách nhạc nền thất bại: {str(e)}\n{stack_trace}'
                logger.error(error_msg)
                release_model()
                return False, None, error_msg

            if srt_path and os.path.exists(srt_path):
                # If SRT provided, convert to JSON and save
                try:
                    transcript = srt_to_json(srt_path)
                    # Save both transcript and translation for TTS compatibility
                    with open(os.path.join(folder, 'transcript.json'), 'w', encoding='utf-8') as f:
                        json.dump(transcript, f, indent=4, ensure_ascii=False)
                    with open(os.path.join(folder, 'translation.json'), 'w', encoding='utf-8') as f:
                        json.dump(transcript, f, indent=4, ensure_ascii=False)
                    logger.info(f'Đã sử dụng file SRT ngoài: {srt_path}')
                    # Skip ASR stage
                    current_stage += 1
                    progress_base += stages[current_stage-1][1]
                except Exception as e:
                    logger.error(f'Lỗi khi xử lý file SRT ngoài: {str(e)}')
                    return False, None, f'Lỗi xử lý SRT ngoài: {str(e)}'
            elif not skip_asr:
                # Vocal separation done, entering ASR stage
                current_stage += 1
                progress_base += stage_weight
                stage_name, stage_weight = stages[current_stage]
                if progress_callback:
                    progress_callback(progress_base, stage_name)

                try:
                    # Bước 3: Nhận dạng giọng nói (WhisperX) - Nạp nối tiếp bên trong hàm để tiết kiệm VRAM
                    status, result_json = transcribe_all_audio_under_folder(
                        folder, asr_method=asr_method, whisper_model_name=whisper_model, device=device,
                        batch_size=batch_size, diarization=diarization,
                        min_speakers=whisper_min_speakers,
                        max_speakers=whisper_max_speakers)
                    logger.info(f'Nhận dạng giọng nói thành công: {status}')
                    
                    # Không cần release_whisperx() thủ công nữa vì nó đã tự giải phóng mô hình cuối (Diarize) bên trong
                    # Nhưng tốt nhất nên gọi để chắc chắn mọi thứ đã được dọn dẹp
                    release_whisperx()
                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_msg = f'Nhận dạng giọng nói thất bại: {str(e)}\n{stack_trace}'
                    logger.error(error_msg)
                    release_whisperx()
                    return False, None, error_msg
            else:
                # Skip ASR
                current_stage += 1
                progress_base += stage_weight

            # ASR done, entering Translation stage
            if not skip_translation:
                current_stage += 1
                progress_base += stage_weight
                stage_name, stage_weight = stages[current_stage]
                if progress_callback:
                    progress_callback(progress_base, stage_name)

                try:
                    status, summary, translation = translate_all_transcript_under_folder(
                        folder, method=translation_method, target_language=translation_target_language)
                    logger.info(f'Dịch thuật hoàn tất: {status}')
                except Exception as e:
                    stack_trace = traceback.format_exc()
                    error_msg = f'Dịch thuật thất bại: {str(e)}\n{stack_trace}'
                    logger.error(error_msg)
                    return False, None, error_msg
            else:
                # Skip Translation
                current_stage += 1
                progress_base += stage_weight

            # Translation done, entering TTS stage
            current_stage += 1
            progress_base += stage_weight
            stage_name, stage_weight = stages[current_stage]
            if progress_callback:
                progress_callback(progress_base, stage_name)

            try:
                # Bước 5: Nạp TTS tùy theo phương pháp
                if tts_method == 'xtts':
                    init_TTS()
                elif tts_method == 'cosyvoice':
                    init_cosyvoice()
                    
                status, synth_path, _ = generate_all_wavs_under_folder(
                    folder, method=tts_method, target_language=tts_target_language, voice=voice)
                logger.info(f'Lồng tiếng hoàn tất: {synth_path}')
                
                # Bước 6: Giải phóng TTS
                if tts_method == 'xtts':
                    release_xtts()
                elif tts_method == 'cosyvoice':
                    release_cosyvoice()
            except Exception as e:
                stack_trace = traceback.format_exc()
                error_msg = f'Lồng tiếng thất bại: {str(e)}\n{stack_trace}'
                logger.error(error_msg)
                if tts_method == 'xtts': release_xtts()
                elif tts_method == 'cosyvoice': release_cosyvoice()
                return False, None, error_msg

            # TTS done, entering Video Synthesis stage
            current_stage += 1
            progress_base += stage_weight
            stage_name, stage_weight = stages[current_stage]
            if progress_callback:
                progress_callback(progress_base, stage_name)

            try:
                status, output_video = synthesize_all_video_under_folder(
                    folder, subtitles=subtitles, speed_up=speed_up, fps=fps, resolution=target_resolution,
                    background_music=background_music, bgm_volume=bgm_volume, video_volume=video_volume,
                    blur_subtitles=blur_subtitles, blur_height=blur_height, blur_y=blur_y)
                logger.info(f'Tổng hợp video thành công: {output_video}')
            except Exception as e:
                stack_trace = traceback.format_exc()
                error_msg = f'Tổng hợp video thất bại: {str(e)}\n{stack_trace}'
                logger.error(error_msg)
                return False, None, error_msg

            # Hoàn tất mọi giai đoạn, tiến hành dọn dẹp tệp rác
            try:
                cleanup_folder(folder)
            except Exception as e:
                logger.error(f"Lỗi khi dọn dẹp tệp tạm: {e}")

            # Hoàn tất mọi giai đoạn, báo cáo tiến độ 100%
            if progress_callback:
                progress_callback(100, "Xử lý hoàn tất và đã dọn dẹp!")

            return True, output_video, "Xử lý thành công"
        except Exception as e:
            stack_trace = traceback.format_exc()
            error_msg = f'Lỗi khi xử lý video {info["title"] if isinstance(info, dict) else info}: {str(e)}\n{stack_trace}'
            logger.error(error_msg)
            if retry < max_retries - 1:
                logger.info(f'Đang thử lại {retry + 2}/{max_retries}...')
            else:
                return False, None, error_msg

    return False, None, f"Đã đạt giới hạn số lần thử lại: {max_retries}"


def do_everything(root_folder, url, num_videos=5, resolution='1080p',
                  demucs_model='htdemucs', device='auto', shifts=1,
                  asr_method='WhisperX', whisper_model='large', batch_size=4, diarization=False,
                  whisper_min_speakers=None, whisper_max_speakers=None,
                  translation_method='LLM', translation_target_language='Tiếng Việt',
                  tts_method='xtts', tts_target_language='Tiếng Việt', voice='vi-VN-HoaiMyNeural',
                  subtitles=True, speed_up=1.00, fps=30,
                  background_music=None, bgm_volume=0.5, video_volume=1.0, target_resolution='1080p',
                  max_workers=3, max_retries=5, progress_callback=None, srt_path=None, skip_asr=False, skip_translation=False, blur_subtitles=False, blur_height=15, blur_y=85):
    """
    Main entry point for handling the entire video processing workflow.

    Args:
        progress_callback: Callback function for reporting progress and status, 
                          format: progress_callback(progress_percent, status_message)
    """
    try:
        success_list = []
        fail_list = []
        error_details = []

        # Log start information and parameters
        logger.info("-" * 50)
        logger.info(f"Bắt đầu nhiệm vụ: {url}")
        logger.info(f"Tham số: Folder={root_folder}, Số lượng={num_videos}, Độ phân giải={resolution}")
        logger.info(f"Tách tiếng: Model={demucs_model}, Thiết bị={device}, Shifts={shifts}")
        logger.info(f"Nhận dạng: Phương pháp={asr_method}, Model={whisper_model}, Batch={batch_size}")
        logger.info(f"Dịch thuật: Phương pháp={translation_method}, Ngôn ngữ={translation_target_language}")
        logger.info(f"Lồng tiếng: Phương pháp={tts_method}, Ngôn ngữ={tts_target_language}, Giọng={voice}")
        logger.info(f"Tổng hợp: Phụ đề={subtitles}, Tốc độ={speed_up}, FPS={fps}, Độ phân giải={target_resolution}")
        logger.info("-" * 50)

        url = url.replace(' ', '').replace('，', '\n').replace(',', '\n')
        urls = [_ for _ in url.split('\n') if _]

        # Initialize models
        try:
            if progress_callback:
                progress_callback(5, "Đang khởi tạo các mô hình AI...")
            initialize_models(tts_method, asr_method, diarization)
        except Exception as e:
            stack_trace = traceback.format_exc()
            logger.error(f"Khởi tạo mô hình thất bại: {str(e)}\n{stack_trace}")
            return f"Khởi tạo mô hình thất bại: {str(e)}", None

        out_video = None
        if url.endswith('.mp4'):
            try:
                import shutil
                # Get original filename
                original_file_name = os.path.basename(url)

                # Remove extension to generate folder name
                new_folder_name = os.path.splitext(original_file_name)[0]

                # Build full path for new folder
                new_folder_path = os.path.join(root_folder, new_folder_name)

                # Create the folder under root_folder
                os.makedirs(new_folder_path, exist_ok=True)

                # Use original url as path since it's local
                original_file_path = url

                # Build full destination path
                new_file_path = os.path.join(new_folder_path, "download.mp4")

                # Copy video file to the new folder
                shutil.copy(original_file_path, new_file_path)
                
                success, output_video, error_msg = process_video(
                    new_file_path, root_folder, resolution,
                    demucs_model, device, shifts,
                    asr_method, whisper_model, batch_size, diarization, whisper_min_speakers, whisper_max_speakers,
                    translation_method, translation_target_language,
                    tts_method, tts_target_language, voice,
                    subtitles, speed_up, fps, background_music, bgm_volume, video_volume,
                    target_resolution, max_retries, progress_callback,
                    srt_path=srt_path, skip_asr=skip_asr, skip_translation=skip_translation,
                    blur_subtitles=blur_subtitles, blur_height=blur_height, blur_y=blur_y
                )

                if success:
                    logger.info(f"Xử lý video thành công: {new_file_path}")
                    return 'Xử lý thành công', output_video
                else:
                    logger.error(f"Xử lý video thất bại: {new_file_path}, Lỗi: {error_msg}")
                    return f'Xử lý thất bại: {error_msg}', None
            except Exception as e:
                stack_trace = traceback.format_exc()
                logger.error(f"Lỗi khi xử lý video cục bộ: {str(e)}\n{stack_trace}")
                return f"Lỗi video cục bộ: {str(e)}", None
        else:
            try:
                videos_info = []
                if progress_callback:
                    progress_callback(10, "Đang lấy thông tin video...")

                for video_info in get_info_list_from_url(urls, num_videos):
                    videos_info.append(video_info)

                if not videos_info:
                    return "Không thể lấy thông tin video, vui lòng kiểm tra URL", None

                for info in videos_info:
                    try:
                        success, output_video, error_msg = process_video(
                            info, root_folder, resolution,
                            demucs_model, device, shifts,
                            asr_method, whisper_model, batch_size, diarization, whisper_min_speakers,
                            whisper_max_speakers,
                            translation_method, translation_target_language,
                            tts_method, tts_target_language, voice,
                            subtitles, speed_up, fps, background_music, bgm_volume, video_volume,
                            target_resolution, max_retries, progress_callback,
                            srt_path=srt_path, skip_asr=skip_asr, skip_translation=skip_translation,
                            blur_subtitles=blur_subtitles, blur_height=blur_height, blur_y=blur_y
                        )

                        if success:
                            success_list.append(info)
                            out_video = output_video
                            logger.info(f"Đã xử lý xong: {info['title'] if isinstance(info, dict) else info}")
                        else:
                            fail_list.append(info)
                            error_details.append(f"{info['title'] if isinstance(info, dict) else info}: {error_msg}")
                            logger.error(
                                f"Lỗi khi xử lý: {info['title'] if isinstance(info, dict) else info}, Lỗi: {error_msg}")
                    except Exception as e:
                        stack_trace = traceback.format_exc()
                        fail_list.append(info)
                        error_details.append(f"{info['title'] if isinstance(info, dict) else info}: {str(e)}")
                        logger.error(
                            f"Lỗi hệ thống khi xử lý: {info['title'] if isinstance(info, dict) else info}, Lỗi: {str(e)}\n{stack_trace}")
            except Exception as e:
                stack_trace = traceback.format_exc()
                logger.error(f"Không thể lấy danh sách video: {str(e)}\n{stack_trace}")
                return f"Lỗi danh sách video: {str(e)}", None

        # Log completion summary
        logger.info("-" * 50)
        logger.info(f"Hoàn tất: Thành công={len(success_list)}, Thất bại={len(fail_list)}")
        if error_details:
            logger.info("Chi tiết lỗi:")
            for detail in error_details:
                logger.info(f"  - {detail}")

        return f'Thành công: {len(success_list)}\nThất bại: {len(fail_list)}', out_video

    except Exception as e:
        # Capture any overall processing errors
        stack_trace = traceback.format_exc()
        error_msg = f"Đã xảy ra lỗi trong quá trình xử lý: {str(e)}\n{stack_trace}"
        logger.error(error_msg)
        return error_msg, None


if __name__ == '__main__':
    do_everything(
        root_folder='videos',
        url='https://www.bilibili.com/video/BV1kr421M7vz/',
        translation_method='LLM',
        # translation_method = 'Google Translate', translation_target_language = '简体中文',
    )