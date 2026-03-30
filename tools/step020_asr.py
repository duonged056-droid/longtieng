
import os
import torch
import numpy as np
from dotenv import load_dotenv
from .step021_asr_whisperx import whisperx_transcribe_audio
from .step022_asr_funasr import funasr_transcribe_audio
from .utils import save_wav
import json
import librosa
from loguru import logger
load_dotenv()

def merge_segments(transcript, ending='!"\').:;?]}~！“”’）。：；？】'):
    merged_transcription = []
    buffer_segment = None

    for segment in transcript:
        if buffer_segment is None:
            buffer_segment = segment
        else:
            # Check if the last character of the 'text' field is a punctuation mark
            if buffer_segment['text'][-1] in ending:
                # If it is, add the buffered segment to the merged transcription
                merged_transcription.append(buffer_segment)
                buffer_segment = segment
            else:
                # If it's not, merge this segment with the buffered segment
                buffer_segment['text'] += ' ' + segment['text']
                buffer_segment['end'] = segment['end']

    # Don't forget to add the last buffered segment
    if buffer_segment is not None:
        merged_transcription.append(buffer_segment)

    return merged_transcription

def generate_speaker_audio(folder, transcript):
    wav_path = os.path.join(folder, 'audio_vocals.wav')
    audio_data, samplerate = librosa.load(wav_path, sr=24000)
    speaker_dict = dict()
    length = len(audio_data)
    delay = 0.05
    for segment in transcript:
        start = max(0, int((segment['start'] - delay) * samplerate))
        end = min(int((segment['end']+delay) * samplerate), length)
        speaker_segment_audio = audio_data[start:end]
        speaker_dict[segment['speaker']] = np.concatenate((speaker_dict.get(
            segment['speaker'], np.zeros((0, ))), speaker_segment_audio))

    speaker_folder = os.path.join(folder, 'SPEAKER')
    if not os.path.exists(speaker_folder):
        os.makedirs(speaker_folder)
    
    for speaker, audio in speaker_dict.items():
        speaker_file_path = os.path.join(
            speaker_folder, f"{speaker}.wav")
        save_wav(audio, speaker_file_path)


def transcribe_audio(method, folder, model_name: str = 'large', download_root='models/ASR/whisper', device='auto', batch_size=4, diarization=True,min_speakers=None, max_speakers=None):
    if os.path.exists(os.path.join(folder, 'transcript.json')):
        logger.info(f'Phụ đề đã tồn tại: {folder}')
        return True
    
    wav_path = os.path.join(folder, 'audio_vocals.wav')
    if not os.path.exists(wav_path):
        return False
    
    logger.info(f'Đang nhận dạng giọng nói: {wav_path}')
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    if method == 'WhisperX':
        transcript = whisperx_transcribe_audio(wav_path, model_name, download_root, device, batch_size, diarization, min_speakers, max_speakers)
    elif method == 'FunASR':
        transcript = funasr_transcribe_audio(wav_path, device, batch_size, diarization)
    else:
        logger.error('Invalid ASR method')
        raise ValueError('Invalid ASR method')

    transcript = merge_segments(transcript)
    with open(os.path.join(folder, 'transcript.json'), 'w', encoding='utf-8') as f:
        json.dump(transcript, f, indent=4, ensure_ascii=False)
    logger.info(f'Nhận dạng giọng nói {wav_path} thành công, đã lưu vào {os.path.join(folder, "transcript.json")}')
    generate_speaker_audio(folder, transcript)
    return transcript

def transcribe_all_audio_under_folder(folder, asr_method, whisper_model_name: str = 'large', device='auto', batch_size=4, diarization=False, min_speakers=None, max_speakers=None, progress_callback=None):
    transcribe_json = None
    
    # Count matching directories
    target_dirs = []
    for root, dirs, files in os.walk(folder):
        if 'audio_vocals.wav' in files and 'transcript.json' not in files:
            target_dirs.append(root)
    
    total_dirs = len(target_dirs)
    if total_dirs == 0:
        logger.info(f"Không tìm thấy file âm thanh cần nhận dạng.")
        # Re-scan for existing transcript.json if no new files
        for root, dirs, files in os.walk(folder):
            if 'transcript.json' in files:
                transcribe_json = json.load(open(os.path.join(root, 'transcript.json'), 'r', encoding='utf-8'))
                break
        return f'No audio files to transcribe', transcribe_json

    for i, root in enumerate(target_dirs):
        if progress_callback:
            percent = int((i / total_dirs) * 100)
            progress_callback(percent, f"Đang nhận dạng tiếng ({i+1}/{total_dirs}): {os.path.basename(root)}")
            
        transcribe_json = transcribe_audio(asr_method, root, whisper_model_name, 'models/ASR/whisper', device, batch_size, diarization, min_speakers, max_speakers)
    
    if progress_callback:
        progress_callback(100, "Nhận dạng giọng nói hoàn tất")
        
    return f'Transcribed all audio under {folder}', transcribe_json

if __name__ == '__main__':
    _, transcribe_json = transcribe_all_audio_under_folder('videos', 'WhisperX')
    print(transcribe_json)
    # _, transcribe_json = transcribe_all_audio_under_folder('videos', 'FunASR')    
    # print(transcribe_json)