import json
import time
import librosa
import numpy as np
import whisperx
from whisperx.asr import load_model as asr_load_model
import os
from loguru import logger
import inspect
import sys
from transformers import Wav2Vec2Processor

# Monkey Patch toàn cục cho Wav2Vec2Processor để fix lỗi 'sampling_rate' cho tiếng Trung
if not hasattr(Wav2Vec2Processor, 'sampling_rate'):
    Wav2Vec2Processor.sampling_rate = 16000

os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"

# Sửa lỗi "Library cublas64_12.dll is not found" trên Windows
if sys.platform == "win32":
    import site
    # Tìm kiếm trong tất cả các thư mục site-packages khả thi
    possible_paths = site.getsitepackages() + [os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Lib", "site-packages")]
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
from dotenv import load_dotenv
load_dotenv()

whisper_model = None
diarize_model = None

align_model = None
language_code = None
align_metadata = None

def init_whisperx():
    load_whisper_model()
    load_align_model()

def init_diarize():
    load_diarize_model()
    
def load_whisper_model(model_name: str = 'large', download_root = 'models/ASR/whisper', device='auto'):
    if model_name == 'large':
        pretrain_model = os.path.join(download_root,"faster-whisper-large-v3")
        model_name = 'large-v3' if not os.path.isdir(pretrain_model) else pretrain_model
        
    global whisper_model
    if whisper_model is not None:
        return
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f'Loading WhisperX model: {model_name}')
    t_start = time.time()
    if device=='cpu':
        whisper_model = asr_load_model(model_name, download_root=download_root, device=device, compute_type='int8')
    else:
        # Sử dụng int8_float16 để tiết kiệm VRAM cho card 4GB
        whisper_model = asr_load_model(model_name, download_root=download_root, device=device, compute_type='int8_float16')
    t_end = time.time()
    logger.info(f'Loaded WhisperX model: {model_name} in {t_end - t_start:.2f}s')

def load_align_model(language='en', device='auto', model_dir='models/ASR/whisper'):
    global align_model, language_code, align_metadata
    if align_model is not None and language_code == language:
        return
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    language_code = language
    t_start = time.time()
    align_model, align_metadata = whisperx.load_align_model(
        language_code=language_code, device=device, model_dir = model_dir)
    
    # Vá lỗi sampling_rate triệt để cho cả align_model và metadata
    for obj in [align_model, align_metadata.get("processor") if align_metadata else None]:
        if obj is not None:
            # Nếu là align_model, kiểm tra thuộc tính processor bên trong
            target = getattr(obj, "processor", obj)
            if target is not None and not hasattr(target, 'sampling_rate'):
                try:
                    target.sampling_rate = 16000
                    logger.info(f"Đã vá lỗi sampling_rate cho {type(target).__name__}")
                except Exception:
                    pass
    
    t_end = time.time()
    logger.info(f'Loaded alignment model: {language_code} in {t_end - t_start:.2f}s')
    
def load_diarize_model(device='auto'):
    global diarize_model
    if diarize_model is not None:
        return
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    t_start = time.time()
    try:
        diarize_model = whisperx.DiarizationPipeline(use_auth_token=os.getenv('HF_TOKEN'), device=device)
        t_end = time.time()
        logger.info(f'Loaded diarization model in {t_end - t_start:.2f}s')
    except Exception as e:
        t_end = time.time()
        logger.error(f"Failed to load diarization model in {t_end - t_start:.2f}s due to {str(e)}")
        logger.info("You have not set the HF_TOKEN, so the pyannote/speaker-diarization-3.1 model could not be downloaded.")
        logger.info("If you need to use the speaker diarization feature, please request access to the pyannote/speaker-diarization-3.1 model. Alternatively, you can choose not to enable this feature.")

def whisperx_transcribe_audio(wav_path, model_name: str = 'large', download_root='models/ASR/whisper', device='auto', batch_size=4, diarization=True,min_speakers=None, max_speakers=None):
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    # --- Bước 1: Nhận dạng giọng nói (Whisper) ---
    # Giải phóng mọi mô hình khác để dành chỗ cho Whisper
    release_align_model()
    release_diarize_model()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
    load_whisper_model(model_name, download_root, device)
    
    try:
        rec_result = whisper_model.transcribe(wav_path, batch_size=batch_size)
    except RuntimeError as e:
        if "out of memory" in str(e).lower() and batch_size > 1:
            logger.warning(f"Lỗi CUDA Out of Memory với batch_size={batch_size}. Đang thử lại với batch_size=1...")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            rec_result = whisper_model.transcribe(wav_path, batch_size=1)
        else:
            raise e
    
    if rec_result['language'] == 'nn' or not rec_result['segments']:
        logger.warning(f'Không tìm thấy tiếng trong file {wav_path}')
        return False
    
    # Giải phóng Whisper ngay để dành chỗ cho Align
    release_whisper_model()
    
    # --- Bước 2: Căn chỉnh khớp chữ (Align) ---
    load_align_model(rec_result['language'], device=device, model_dir=download_root)
    try:
        rec_result = whisperx.align(rec_result['segments'], align_model, align_metadata,
                                    wav_path, device, return_char_alignments=False)
    except Exception as e:
        logger.error(f"Lỗi trong quá trình Alignment: {str(e)}")
        # Có lỗi align vẫn trả về kết quả thô nếu cần, hoặc dừng lại
    
    # Giải phóng Align để dành chỗ cho Diarize
    release_align_model()
    
    # --- Bước 3: Phân tách người nói (Diarization) ---
    if diarization:
        load_diarize_model(device)
        if diarize_model:
            try:
                diarize_segments = diarize_model(wav_path,min_speakers=min_speakers, max_speakers=max_speakers)
                rec_result = whisperx.assign_word_speakers(diarize_segments, rec_result)
            except Exception as e:
                logger.error(f"Lỗi trong quá trình Diarization: {str(e)}")
        else:
            logger.warning("Diarization model is not loaded, skipping speaker diarization")
        
        # Giải phóng Diarize sau khi xong
        release_diarize_model()
        
    transcript = [{'start': segment['start'], 'end': segment['end'], 'text': segment['text'].strip(), 'speaker': segment.get('speaker', 'SPEAKER_00')} for segment in rec_result['segments']]
    
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
    return transcript

def release_whisper_model():
    global whisper_model
    if whisper_model is not None:
        logger.info("Giải phóng Whisper model...")
        whisper_model = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def release_align_model():
    global align_model, language_code, align_metadata
    if align_model is not None:
        logger.info("Giải phóng Alignment model...")
        align_model = None
        language_code = None
        align_metadata = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def release_diarize_model():
    global diarize_model
    if diarize_model is not None:
        logger.info("Giải phóng Diarization model...")
        diarize_model = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

def release_whisperx():
    """Giải phóng toàn bộ tài nguyên WhisperX."""
    logger.info("Đang giải phóng toàn bộ tài nguyên WhisperX...")
    release_whisper_model()
    release_align_model()
    release_diarize_model()
    logger.info("Đã giải phóng toàn bộ tài nguyên WhisperX thành công.")


if __name__ == '__main__':
    for root, dirs, files in os.walk("videos"):
        if 'audio_vocals.wav' in files:
            logger.info(f'Transcribing {os.path.join(root, "audio_vocals.wav")}')
            transcript = whisperx_transcribe_audio(os.path.join(root, "audio_vocals.wav"))
            print(transcript)
            break