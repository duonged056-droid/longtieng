import json
import os
import re
import librosa

from loguru import logger
import numpy as np

from .utils import save_wav, save_wav_norm
# from .step041_tts_bytedance import tts as bytedance_tts
from .step042_tts_xtts import tts as xtts_tts
from .step043_tts_cosyvoice import tts as cosyvoice_tts
from .step044_tts_edge_tts import tts as edge_tts
from .cn_tx import TextNorm
from audiostretchy.stretch import stretch_audio
normalizer = TextNorm()
def preprocess_text(text):
    # Basic text cleaning/preprocessing before TTS
    text = text.replace('AI', 'AI')
    text = re.sub(r'(?<!^)([A-Z])', r' \1', text)
    text = normalizer(text)
    # Insert space between letters and numbers using regex
    text = re.sub(r'(?<=[a-zA-Z])(?=\d)|(?<=\d)(?=[a-zA-Z])', ' ', text)
    return text
    
    
def adjust_audio_length(wav_path, desired_length, sample_rate = 24000, min_speed_factor = 0.6, max_speed_factor = 1.1):
    try:
        if not os.path.exists(wav_path):
            mp3_path = wav_path.replace('.wav', '.mp3')
            if os.path.exists(mp3_path):
                wav_path = mp3_path
            else:
                # If neither wav nor mp3 exists, generate silence
                logger.error(f"Không tìm thấy file âm thanh: {wav_path}. Thay thế bằng khoảng lặng.")
                return np.zeros((int(desired_length*sample_rate), )), desired_length

        wav, sr_load = librosa.load(wav_path, sr=sample_rate)
        current_length = len(wav)/sample_rate
        speed_factor = max(
            min(desired_length / current_length, max_speed_factor), min_speed_factor)
        logger.info(f"Speed Factor {speed_factor}")
        
        target_path = wav_path.replace('.wav', f'_adjusted.wav').replace('.mp3', f'_adjusted.wav')
        
        stretch_audio(wav_path, target_path, ratio=speed_factor, sample_rate=sample_rate)
        
        if os.path.exists(target_path):
            wav, sr_load = librosa.load(target_path, sr=sample_rate)
            return wav[:int(desired_length*sample_rate)], desired_length
        else:
            logger.error(f"Stretched audio not created: {target_path}. Using silence.")
            return np.zeros((int(desired_length*sample_rate), )), desired_length
            
    except Exception as e:
        logger.error(f"Lỗi khi điều chỉnh độ dài âm thanh cho {wav_path}: {e}")
        # Return silence on error to prevent pipeline crash
        return np.zeros((int(desired_length*sample_rate), )), desired_length

tts_support_languages = {
    # XTTS-v2 supports 17 languages: English (en), Spanish (es), French (fr), German (de), Italian (it), Portuguese (pt), Polish (pl), Turkish (tr), Russian (ru), Dutch (nl), Czech (cs), Arabic (ar), Chinese (zh-cn), Japanese (ja), Hungarian (hu), Korean (ko) Hindi (hi).
    'xtts': ['Tiếng Việt', '中文', 'English', 'Japanese', 'Korean', 'French', 'Polish', 'Spanish'],
    'bytedance': [],
    'GPTSoVits': [],
    'EdgeTTS': ['Tiếng Việt', '中文', 'English', 'Japanese', 'Korean', 'French', 'Polish', 'Spanish'],
    # zero_shot usage, <|zh|><|en|><|jp|><|yue|><|ko|> for Chinese/English/Japanese/Cantonese/Korean
    'cosyvoice': ['Tiếng Việt', '中文', '粤语', 'English', 'Japanese', 'Korean', 'French'], 
}

def generate_wavs(method, folder, target_language='中文', voice = 'zh-CN-XiaoxiaoNeural', progress_callback=None):
    assert method in ['xtts', 'bytedance', 'cosyvoice', 'EdgeTTS']
    transcript_path = os.path.join(folder, 'translation.json')
    if not os.path.exists(transcript_path):
        transcript_path = os.path.join(folder, 'transcript.json')
        
    output_folder = os.path.join(folder, 'wavs')
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript = json.load(f)
    speakers = set()
    
    for line in transcript:
        speakers.add(line['speaker'])
    num_speakers = len(speakers)
    logger.info(f'Tìm thấy {num_speakers} người nói')

    if target_language not in tts_support_languages[method]:
        logger.error(f'{method} does not support {target_language}')
        return f'{method} does not support {target_language}'
        
    full_wav = np.zeros((0, ))
    for i, line in enumerate(transcript):
        if progress_callback:
            percent = int((i / len(transcript)) * 100)
            progress_callback(percent, f"Đang tạo giọng nói ({i+1}/{len(transcript)})")
            
        speaker = line['speaker']
        text = line.get('translation', line.get('text', ''))
        text = preprocess_text(text)
        output_path = os.path.join(output_folder, f'{str(i).zfill(4)}.wav')
        speaker_wav = os.path.join(folder, 'SPEAKER', f'{speaker}.wav')
        # if num_speakers == 1:
            # bytedance_tts(text, output_path, speaker_wav, voice_type='BV701_streaming')
        
        if method == 'bytedance':
            bytedance_tts(text, output_path, speaker_wav, target_language = target_language)
        elif method == 'xtts':
            xtts_tts(text, output_path, speaker_wav, target_language = target_language)
        elif method == 'cosyvoice':
            cosyvoice_tts(text, output_path, speaker_wav, target_language = target_language)
        elif method == 'EdgeTTS':
            edge_tts(text, output_path, target_language = target_language, voice = voice)
        start = line['start']
        end = line['end']
        length = end-start
        last_end = len(full_wav)/24000
        if start > last_end:
            full_wav = np.concatenate((full_wav, np.zeros((int((start - last_end) * 24000), ))))
        start = len(full_wav)/24000
        line['start'] = start
        if i < len(transcript) - 1:
            next_line = transcript[i+1]
            next_end = next_line['end']
            end = min(start + length, next_end)
        wav, length = adjust_audio_length(output_path, end-start)

        full_wav = np.concatenate((full_wav, wav))
        line['end'] = start + length
        
    if progress_callback: progress_callback(95, "Đang trộn âm và hậu xử lý...")
    vocal_wav, sr = librosa.load(os.path.join(folder, 'audio_vocals.wav'), sr=24000)
    full_wav = full_wav / np.max(np.abs(full_wav)) * np.max(np.abs(vocal_wav))
    audio_tts_wav = os.path.join(folder, 'audio_tts.wav')
    save_wav(full_wav, audio_tts_wav)
    with open(transcript_path, 'w', encoding='utf-8') as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    
    instruments_wav, sr = librosa.load(os.path.join(folder, 'audio_instruments.wav'), sr=24000)
    len_full_wav = len(full_wav)
    len_instruments_wav = len(instruments_wav)
    
    if len_full_wav > len_instruments_wav:
        # If full_wav is longer, pad instruments_wav to match length
        instruments_wav = np.pad(
            instruments_wav, (0, len_full_wav - len_instruments_wav), mode='constant')
    elif len_instruments_wav > len_full_wav:
        # If instruments_wav is longer, pad full_wav to match length
        full_wav = np.pad(
            full_wav, (0, len_instruments_wav - len_full_wav), mode='constant')
    combined_wav = full_wav + instruments_wav
    # Combined with normalization
    audio_combined_wav = os.path.join(folder, 'audio_combined.wav')
    save_wav_norm(combined_wav, audio_combined_wav)
    
    # Export MP3 as requested
    import subprocess
    audio_tts_mp3 = os.path.join(folder, 'audio_tts.mp3')
    audio_combined_mp3 = os.path.join(folder, 'audio_combined.mp3')
    
    try:
        logger.info("Converting synthesized audio to MP3...")
        subprocess.run(['ffmpeg', '-y', '-i', audio_tts_wav, '-acodec', 'libmp3lame', '-ab', '192k', audio_tts_mp3], check=True, capture_output=True)
        subprocess.run(['ffmpeg', '-y', '-i', audio_combined_wav, '-acodec', 'libmp3lame', '-ab', '192k', audio_combined_mp3], check=True, capture_output=True)
        logger.info(f"Full MP3 exported: {audio_tts_mp3} and {audio_combined_mp3}")
    except Exception as e:
        logger.warning(f"Failed to export MP3 using ffmpeg: {e}")

    logger.info(f'Đã tạo tệp âm thanh: {audio_combined_wav}')
    if progress_callback: progress_callback(100, "Lồng tiếng hoàn tất")
    return audio_combined_wav, os.path.join(folder, 'audio.wav')

def generate_all_wavs_under_folder(root_folder, method, target_language='中文', voice = 'zh-CN-XiaoxiaoNeural', progress_callback=None):
    wav_combined, wav_ori = None, None
    
    # Count directories matching criteria
    target_dirs = []
    for root, dirs, files in os.walk(root_folder):
        target_file = None
        if 'translation.json' in files:
            target_file = 'translation.json'
        elif 'transcript.json' in files:
            target_file = 'transcript.json'
            
        if target_file and 'audio_combined.wav' not in files:
            target_dirs.append((root, target_file))
            
    total_dirs = len(target_dirs)
    if total_dirs == 0:
        logger.info(f"Không tìm thấy file cần lồng tiếng.")
        # Re-check existing files
        for root, dirs, files in os.walk(root_folder):
            if 'audio_combined.wav' in files:
                wav_combined, wav_ori = os.path.join(root, 'audio_combined.wav'), os.path.join(root, 'audio.wav')
                break
        return f'No files to generate wavs', wav_combined, wav_ori

    for i, (root, target_file) in enumerate(target_dirs):
        def sub_callback(p, msg):
            if progress_callback:
                overall_p = int((i / total_dirs) * 100 + (p / total_dirs))
                progress_callback(overall_p, f"[{i+1}/{total_dirs}] {msg}")
                
        wav_combined, wav_ori = generate_wavs(method, root, target_language, voice, progress_callback=sub_callback)
        
    if progress_callback:
        progress_callback(100, "Hoàn tất tất cả nhiệm vụ lồng tiếng")
        
    return f'Generated all wavs under {root_folder}', wav_combined, wav_ori

if __name__ == '__main__':
    folder = r'videos/村长台钓加拿大/20240805 英文无字幕 阿里这小子在水城威尼斯发来问候'
    generate_wavs('xtts', folder)
