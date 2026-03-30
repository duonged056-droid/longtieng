import os
from loguru import logger
import numpy as np
import torch
import time
from .utils import save_wav
import sys

# Thêm đường dẫn cho các submodule
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT_DIR, "CosyVoice"))
sys.path.append(os.path.join(ROOT_DIR, "CosyVoice", "third_party", "Matcha-TTS"))

try:
    from cosyvoice.cli.cosyvoice import CosyVoice
    from cosyvoice.utils.file_utils import load_wav
    import torchaudio
    from modelscope import snapshot_download
    COSYVOICE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Không thể import CosyVoice: {e}. Tính năng CosyVoice sẽ bị vô hiệu hóa.")
    COSYVOICE_AVAILABLE = False

model = None

def download_cosyvoice():
    snapshot_download('iic/CosyVoice-300M', local_dir='models/TTS/CosyVoice-300M')

def init_cosyvoice():
    load_model()
    
def load_model(model_path="models/TTS/CosyVoice-300M", device='auto'):
    global model
    if model is not None:
        return

    if device=='auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f'Loading CoxyVoice model from {model_path}')
    t_start = time.time()
    if not os.path.exists(model_path):
        download_cosyvoice()
    model = CosyVoice(model_path)
    t_end = time.time()
    logger.info(f'CoxyVoice model loaded in {t_end - t_start:.2f}s')
    
#  <|zh|><|en|><|jp|><|yue|><|ko|> for Chinese/English/Japanese/Cantonese/Korean
language_map = {
    '中文': 'zh',
    'English': 'en',
    'Japanese': 'jp',
    '粤语': 'yue',
    'Korean': 'ko'
}

def tts(text, output_path, speaker_wav, model_name="models/TTS/CosyVoice-300M", device='auto', target_language='中文'):
    global model
    
    if not COSYVOICE_AVAILABLE:
        logger.error("CosyVoice không khả dụng. Vui lòng kiểm tra thư viện và cấu hình.")
        return

    if os.path.exists(output_path):
        logger.info(f'TTS {text} 已存在')
        return
    
    if model is None:
        load_model(model_name, device)
    
    for retry in range(3):
        try:
            prompt_speech_16k = load_wav(speaker_wav, 16000)
            output = model.inference_cross_lingual(f'<|{language_map[target_language]}|>{text}', prompt_speech_16k)
            torchaudio.save(output_path, output['tts_speech'], 22050)

            logger.info(f'TTS {text}')
            break
        except Exception as e:
            logger.warning(f'TTS {text} 失败')
            logger.warning(e)


def release_cosyvoice():
    """Giải phóng tài nguyên CosyVoice để tiết kiệm VRAM."""
    global model
    if model is not None:
        logger.info("Đang giải phóng tài nguyên CosyVoice...")
        model = None
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        logger.info("Đã giải phóng tài nguyên CosyVoice thành công.")

if __name__ == '__main__':
    speaker_wav = r'videos/村长台钓加拿大/20240805 英文无字幕 阿里这小子在水城威尼斯发来问候/audio_vocals.wav'
    os.makedirs('playground', exist_ok=True)
    while True:
        text = input('请输入：')
        tts(text, f'playground/{text}.wav', speaker_wav = speaker_wav, target_langugae = "粤语")
        
