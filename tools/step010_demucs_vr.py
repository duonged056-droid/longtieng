import shutil
from demucs.api import Separator
import os
from loguru import logger
import time
from .utils import save_wav, normalize_wav
import sys
import os

# Sửa lỗi nạp CUDA DLL cho Demucs trên Windows
if sys.platform == "win32":
    env_site_packages = os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Lib", "site-packages")
    nvidia_base = os.path.join(env_site_packages, "nvidia")
    if os.path.exists(nvidia_base):
        for sub_lib in ["cublas", "cudnn", "cuda_nvrtc"]:
            bin_path = os.path.join(nvidia_base, sub_lib, "bin")
            if os.path.exists(bin_path):
                try:
                    os.add_dll_directory(bin_path)
                except Exception:
                    pass

import torch
import gc

# Global variables
auto_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
separator = None
model_loaded = False  # Track whether the model has been loaded
current_model_config = {}  # Store the current loaded model configuration


def init_demucs():
    """
    Initialize the Demucs model.
    If already initialized, returns without reloading.
    """
    global separator, model_loaded
    if not model_loaded:
        separator = load_model()
        model_loaded = True
    else:
        logger.info("Mô hình Demucs đã được tải, bỏ qua khởi tạo")


def load_model(model_name: str = "htdemucs", device: str = 'auto', progress: bool = True,
               shifts: int = 1) -> Separator:
    """
    Load the Demucs model.
    If the same configuration is already loaded, reuse it.
    """
    global separator, model_loaded, current_model_config

    if separator is not None:
        # 检查是否需要重新加载模型（配置不同）
        requested_config = {
            'model_name': model_name,
            'device': 'auto' if device == 'auto' else device,
            'shifts': shifts
        }

        if current_model_config == requested_config:
            logger.info(f'Mô hình Demucs đã sẵn sàng với cấu hình tương tự, tái sử dụng.')
            return separator
        else:
            logger.info(f'Cấu hình Demucs thay đổi, đang tải lại...')
            # Release existing resources
            release_model()

    # LUÔN ƯU TIÊN MÔ HÌNH NHẸ ĐỂ ĐẢM BẢO TỐC ĐỘ (HTDEMUCS)
    if model_name == "htdemucs_ft":
        logger.warning(f"Mô hình {model_name} quá nặng cho card 4GB, tự động chuyển sang htdemucs để tăng tốc.")
        model_name = "htdemucs"

    logger.info(f'Đang tải mô hình Demucs: {model_name}')
    t_start = time.time()

    # Xóa bộ nhớ đệm GPU trước khi nạp mô hình mới
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # ÉP CỨNG SHIFTS = 0 ĐỂ ĐẠT TỐC ĐỘ TỐI ĐA TRÊN GPU
    if shifts > 0:
        logger.warning(f"Giá trị Shifts={shifts} tự động đưa về 0 để tối ưu tốc độ x5 lần.")
        shifts = 0

    device_to_use = auto_device if device == 'auto' else device
    logger.info(f"Demucs đang sử dụng thiết bị: {device_to_use} (Mô hình: {model_name})")
    separator = Separator(model_name, device=device_to_use, progress=progress, shifts=shifts)

    # 存储当前模型配置
    current_model_config = {
        'model_name': model_name,
        'device': 'auto' if device == 'auto' else device,
        'shifts': shifts
    }

    model_loaded = True
    t_end = time.time()
    logger.info(f'Khởi tạo Demucs thành công, thời gian: {t_end - t_start:.2f} s')

    return separator


def release_model():
    """
    Release model resources to avoid memory leaks.
    """
    global separator, model_loaded, current_model_config

    if separator is not None:
        logger.info('Đang giải phóng tài nguyên mô hình Demucs...')
        # Clear reference
        separator = None
        # Force garbage collection
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        model_loaded = False
        current_model_config = {}
        logger.info('Tài nguyên mô hình Demucs đã được giải phóng')


def separate_audio(folder: str, model_name: str = "htdemucs", device: str = 'auto', progress: bool = True,
                   shifts: int = 1) -> None:
    """
    Separate audio file into vocals and background (vocal separation).
    """
    global separator
    audio_path = os.path.join(folder, 'audio.wav')
    if not os.path.exists(audio_path):
        return None, None
    vocal_output_path = os.path.join(folder, 'audio_vocals.wav')
    instruments_output_path = os.path.join(folder, 'audio_instruments.wav')

    if os.path.exists(vocal_output_path) and os.path.exists(instruments_output_path):
        logger.info(f'Âm thanh đã được tách trước đó: {folder}')
        return vocal_output_path, instruments_output_path

    logger.info(f'Đang tiến hành tách âm thanh: {folder}')

    try:
        # 确保模型已加载并且配置正确
        if not model_loaded or current_model_config.get('model_name') != model_name or \
                (current_model_config.get('device') == 'auto') != (device == 'auto') or \
                current_model_config.get('shifts') != shifts:
            load_model(model_name, device, progress, shifts)

        t_start = time.time()

        try:
            origin, separated = separator.separate_audio_file(audio_path)
        except Exception as e:
            logger.error(f'Lỗi khi tách âm thanh: {e}')
            # Retry once on error
            release_model()
            load_model(model_name, device, progress, shifts)
            logger.info(f'Đã tải lại mô hình, đang thử lại...')
            origin, separated = separator.separate_audio_file(audio_path)

        t_end = time.time()
        logger.info(f'Hoàn tất tách âm thanh, thời gian: {t_end - t_start:.2f} s')

        vocals = separated['vocals'].numpy().T
        instruments = None
        for k, v in separated.items():
            if k == 'vocals':
                continue
            if instruments is None:
                instruments = v
            else:
                instruments += v
        instruments = instruments.numpy().T

        save_wav(vocals, vocal_output_path, sample_rate=44100)
        logger.info(f'Đã lưu file vocal: {vocal_output_path}')

        save_wav(instruments, instruments_output_path, sample_rate=44100)
        logger.info(f'Đã lưu file nhạc nền: {instruments_output_path}')

        return vocal_output_path, instruments_output_path

    except Exception as e:
        logger.error(f'分离音频失败: {str(e)}')
        # 出现错误，释放模型资源并重新抛出异常
        release_model()
        raise


def extract_audio_from_video(folder: str) -> bool:
    """
    Extract audio track from video file.
    """
    video_path = os.path.join(folder, 'download.mp4')
    if not os.path.exists(video_path):
        return False
    audio_path = os.path.join(folder, 'audio.wav')
    if os.path.exists(audio_path):
        logger.info(f'Âm thanh đã được trích xuất: {folder}')
        return True
    logger.info(f'Đang trích xuất âm thanh từ video: {folder}')

    os.system(
        f'ffmpeg -loglevel error -i "{video_path}" -vn -acodec pcm_s16le -ar 44100 -ac 2 "{audio_path}"')

    time.sleep(1)
    logger.info(f'Trích xuất âm thanh hoàn tất: {folder}')
    return True


def separate_all_audio_under_folder(root_folder: str, model_name: str = "htdemucs", device: str = 'auto',
                                    progress: bool = True, shifts: int = 5, progress_callback=None) -> None:
    """
    Separate all audio files in the specified folder.
    """
    global separator
    vocal_output_path, instruments_output_path = None, None

    try:
        if progress_callback:
            progress_callback(0, "Khởi động tiến trình tách âm thanh...")

        for subdir, dirs, files in os.walk(root_folder):
            if 'download.mp4' not in files:
                continue
            if 'audio.wav' not in files:
                extract_audio_from_video(subdir)
            if 'audio_vocals.wav' not in files:
                if progress_callback:
                    progress_callback(50, "Đang tiến hành tách giọng nói và nhạc nền...")
                vocal_output_path, instruments_output_path = separate_audio(subdir, model_name, device, progress,
                                                                            shifts)
            elif 'audio_vocals.wav' in files and 'audio_instruments.wav' in files:
                vocal_output_path = os.path.join(subdir, 'audio_vocals.wav')
                instruments_output_path = os.path.join(subdir, 'audio_instruments.wav')
                logger.info(f'Âm thanh đã có sẵn: {subdir}')

        logger.info(f'Hoàn tất tách âm thanh cho: {root_folder}')
        if progress_callback:
            progress_callback(100, "Tách giọng nói thành công!")
        return f'Tách âm thanh hoàn tất: {root_folder}', vocal_output_path, instruments_output_path

    except Exception as e:
        logger.error(f'Đã xảy ra lỗi khi tách âm: {str(e)}')
        release_model()
        raise


if __name__ == '__main__':
    folder = r"videos"
    separate_all_audio_under_folder(folder, shifts=0)