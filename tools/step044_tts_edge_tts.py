import os
from loguru import logger
import numpy as np
import torch
import time
from .utils import save_wav
import sys

import torchaudio
model = None



#  <|zh|><|en|><|jp|><|yue|><|ko|> for Chinese/English/Japanese/Cantonese/Korean
language_map = {
    '中文': 'zh-CN-XiaoxiaoNeural',
    'English': 'en-US-MichelleNeural',
    'Japanese': 'ja-JP-NanamiNeural',
    '粤语': 'zh-HK-HiuMaanNeural',
    'Korean': 'ko-KR-SunHiNeural'
}

def tts(text, output_path, target_language='Tiếng Việt', voice = 'vi-VN-HoaiMyNeural'):
    if os.path.exists(output_path):
        logger.info(f"TTS {text[:20]}... đã tồn tại")
        return
    
    import subprocess
    mp3_path = output_path.replace(".wav", ".mp3")
    
    for retry in range(3):
        try:
            # Sử dụng subprocess.run với list arguments để tránh lỗi shell injection và xử lý dấu ngoặc kép
            cmd = [
                'edge-tts',
                '--text', text,
                '--write-media', mp3_path,
                '--voice', voice
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 0:
                logger.info(f'TTS Success: {text[:20]}...')
                break
            else:
                logger.warning(f'TTS Command ran but file not found or empty: {mp3_path}')
        except subprocess.CalledProcessError as e:
            logger.warning(f'TTS Failed on try {retry+1}: {e.stderr}')
            time.sleep(1)
        except Exception as e:
            logger.warning(f'TTS Unexpected Error: {e}')
            time.sleep(1)
    
    if not os.path.exists(mp3_path):
        raise FileNotFoundError(f"Failed to create TTS file after retries: {mp3_path}")


if __name__ == '__main__':
    speaker_wav = r'videos/村长台钓加拿大/20240805 英文无字幕 阿里这小子在水城威尼斯发来问候/audio_vocals.wav'
    while True:
        text = input('请输入：')
        tts(text, f'playground/{text}.wav', target_language='中文')
        
