# -*- coding: utf-8 -*-
import json
import os
import re

from dotenv import load_dotenv
import time
from loguru import logger
from tools.step031_translation_openai import openai_response
from tools.step032_translation_llm import llm_response
from tools.step033_translation_translator import translator_response
from tools.step034_translation_ernie import ernie_response
from tools.step035_translation_qwen import qwen_response
from tools.step036_translation_ollama import ollama_response
from tools.step037_translation_gemini import gemini_response

load_dotenv()
import traceback

def get_necessary_info(info: dict):
    return {
        'title': info['title'],
        'uploader': info['uploader'],
        'description': info['description'],
        'upload_date': info['upload_date'],
        # 'categories': info['categories'],
        'tags': info['tags'],
    }

def ensure_transcript_length(transcript, max_length=4000):
    mid = len(transcript)//2
    before, after = transcript[:mid], transcript[mid:]
    length = max_length//2
    return before[:length] + after[-length:]

def split_text_into_sentences(para):
    para = re.sub('([。！？\?])([^，。！？\?”’》])', r"\1\n\2", para)  # Single character sentence delimiters
    para = re.sub('(\.{6})([^，。！？\?”’》])', r"\1\n\2", para)  # English ellipsis
    para = re.sub('(\…{2})([^，。！？\?”’》])', r"\1\n\2", para)  # Chinese ellipsis
    para = re.sub('([。！？\?][”’])([^，。！？\?”’》])', r'\1\n\2', para)
    # If there is a terminator before the double quotes, then the double quotes are the end of the sentence
    para = para.rstrip()  # Remove trailing \n
    # Semicolons are ignored here for simplicity
    return para.split("\n")

def translation_postprocess(result):
    result = re.sub(r'\（[^)]*\）', '', result)
    result = result.replace('...', '，')
    result = re.sub(r'(?<=\d),(?=\d)', '', result)
    result = result.replace('²', '的平方').replace(
        '————', '：').replace('——', '：').replace('°', '度')
    result = result.replace("AI", '人工智能')
    result = result.replace('变压器', "Transformer")
    return result

def valid_translation(text, translation, target_language='简体中文'):
    # Lọc block mã ```
    if (translation.startswith('```') and translation.endswith('```')):
        translation = translation[3:-3]
        if translation.startswith('json'): translation = translation[4:]
        return True, translation_postprocess(translation.strip())
    
    # Lọc dấu ngoặc kép
    if (translation.startswith('“') and translation.endswith('”')) or (translation.startswith('"') and translation.endswith('"')):
        translation = translation[1:-1]
        return True, translation_postprocess(translation.strip())
    
    # Tự động lọc prefix AI
    prefixes = ['翻译：', '译文：', 'Translation:', 'Dịch:', 'Bản dịch:', 'Tiếng Việt:', 'Dịch sang tiếng Việt:', 'Result:']
    for prefix in prefixes:
        if prefix in translation:
            parts = translation.split(prefix, 1)
            if len(parts) > 1:
                translation = parts[1].strip()
                break

    # Không kiểm tra độ dài cho video này để tránh nhầm lẫn
    # Chỉ kiểm tra từ cấm tối thiểu
    is_vietnamese = 'tiếng việt' in target_language.lower() or 'vietnamese' in target_language.lower()
    forbidden = ['这句', 'translate', 'Translate']
    if not is_vietnamese:
        forbidden += ['简体中文', '中文']
    
    translation = translation.strip().replace('\n', ' ')
    for word in forbidden:
        if word in translation:
            return False, f"Chứa từ cấm `{word}`."
    
    return True, translation_postprocess(translation)

def split_sentences(translation, use_char_based_end=True):
    output_data = []
    for item in translation:
        start = item['start']
        text = item['text']
        speaker = item['speaker']
        translation_text = item['translation']

        # Check if translation text is empty
        if not translation_text or len(translation_text.strip()) == 0:
            # If empty, use original range and skip splitting
            output_data.append({
                "start": round(start, 3),
                "end": round(item['end'], 3),
                "text": text,
                "speaker": speaker,
                "translation": translation_text or "Chưa dịch"  # Default if empty
            })
            continue

        sentences = split_text_into_sentences(translation_text)

        if use_char_based_end:
            # Avoid division by zero
            duration_per_char = (item['end'] - item['start']) / max(1, len(translation_text))
        else:
            duration_per_char = 0

        # logger.info(f'Char duration: {duration_per_char}')
        for sentence in sentences:
            if use_char_based_end:
                sentence_end = start + duration_per_char * len(sentence)
            else:
                sentence_end = item['end']

            # Append the new item
            output_data.append({
                "start": round(start, 3),
                "end": round(sentence_end, 3),
                "text": text,
                "speaker": speaker,
                "translation": sentence
            })

            # Update the start for the next sentence
            if use_char_based_end:
                start = sentence_end

    return output_data

def summarize(info, transcript, target_language='简体中文', method = 'LLM'):
    transcript_text = ' '.join(line['text'] for line in transcript)
    transcript_text = ensure_transcript_length(transcript_text, max_length=2000)
    info_message = f'Title: "{info["title"]}" Author: "{info["uploader"]}". ' 
    
    if method in ['Google Translate', 'Bing Translate']:
        full_description = f'{info_message}\n{transcript_text}\n{info_message}\n'
        translation = translator_response(full_description, target_language)
        return {
                'title': translator_response(info['title'], target_language),
                'author': info['uploader'],
                'summary': translation,
                'language': target_language
            }

    full_description = f'The following is the full content of the video:\n{info_message}\n{transcript_text}\n{info_message}\nAccording to the above content, detailedly Summarize the video in JSON format:\n```json\n{{"title": "", "summary": ""}}\n```'
    
    retry_message=''
    summary_result = None
    success = False

    for retry in range(9):
        try:
            messages = [
                {'role': 'system', 'content': f'You are a expert in the field of this video. Please summarize the video in JSON format.\n```json\n{{"title": "the title of the video", "summary": "the summary of the video"}}\n```'},
                {'role': 'user', 'content': full_description + retry_message},
            ]
            
            if method == 'LLM':
                response = llm_response(messages)
            elif method == 'OpenAI':
                response = openai_response(messages)
            elif method == 'Ernie':
                system_content = messages[0]['content']
                user_messages = messages[1:]
                response = ernie_response(user_messages, system=system_content)
            elif method == '阿里云-通义千问':
                response = qwen_response(messages)
            elif method == 'Ollama':
                response = ollama_response(messages)
            elif method == 'Gemini':
                response = gemini_response(messages)
            else:
                raise Exception('Phương pháp không hợp lệ')

            clean_response = response.replace('\n', ' ')
            if clean_response.startswith("Error:"):
                raise Exception(clean_response)
            
            # Trích xuất JSON
            json_match = re.findall(r'\{.*?\}', clean_response)
            if json_match:
                try:
                    summary_dict = json.loads(json_match[0])
                    summary_result = {
                        'title': summary_dict.get('title', info['title']).replace('title:', '').strip(),
                        'summary': summary_dict.get('summary', response).replace('summary:', '').strip()
                    }
                except Exception:
                    summary_result = {'title': info['title'], 'summary': response[:500]}
            else:
                summary_result = {'title': info['title'], 'summary': response[:500]}

            if summary_result['title'] or summary_result['summary']:
                success = True
                break
        except Exception as e:
            retry_message += '\nSummarize the video in JSON format:\n```json\n{"title": "", "summary": ""}\n```'
            logger.warning(f'Tóm lược lần {retry+1}/9 thất bại: {e}')
            time.sleep(1)
            
    if not success:
        logger.error("Tóm lược hoàn toàn thất bại. Sử dụng dự phòng.")
        summary_result = {
            'title': info['title'],
            'summary': info['title']
        }

    # Bước 2: Dịch tóm tắt sang ngôn ngữ đích (nếu cần)
    try:
        messages = [
            {'role': 'system',
                'content': f'You are a native speaker of {target_language}. Please translate the title and summary into {target_language} in JSON format. ```json\n{{"title": "the {target_language} title", "summary": "the {target_language} summary", "tags": []}}\n```.'},
            {'role': 'user',
                'content': f'Title: "{summary_result["title"]}". Summary: "{summary_result["summary"]}". Tags: {info["tags"]}.\nTranslate into {target_language} JSON.'},
        ]
        
        if method == 'LLM': translation = llm_response(messages)
        elif method == 'OpenAI': translation = openai_response(messages)
        elif method == 'Gemini': translation = gemini_response(messages)
        else: translation = summary_result['summary']
        
        json_match = re.findall(r'\{.*?\}', translation.replace('\n', ' '))
        if json_match:
            final_json = json.loads(json_match[0])
            return {
                'title': final_json.get('title', summary_result['title']),
                'author': info['uploader'],
                'summary': final_json.get('summary', summary_result['summary']),
                'tags': final_json.get('tags', info['tags']),
                'language': target_language
            }
    except Exception as e:
        logger.warning(f'Dịch tóm lược thất bại, dùng bản chưa dịch: {e}')
        
    return {
        'title': summary_result['title'],
        'author': info['uploader'],
        'summary': summary_result['summary'],
        'tags': info['tags'],
        'language': target_language
    }

def _translate(summary, transcript, target_language='简体中文', method='LLM', progress_callback=None):

    info = f'This is a video called "{summary["title"]}". {summary["summary"]}.'
    full_translation = []
    if target_language == '简体中文':
        fixed_message = [
            {'role': 'system', 'content': f'You are an expert in the field of this video.\n{info}\nTranslate the sentence into {target_language}. 下面我让你来充当翻译家，你的目标是把任何语言翻译成{target_language}，请翻译时不要带翻译腔，而是要翻译得自然、流畅和地道，使用优美和高雅的表达方式。请将人工智能的“agent”翻译为“智能体”，强化学习中是`Q-Learning`而不是`Queue Learning`。数学公式写成plain text，不要使用latex。确保翻译正确和简洁。注意信达雅。'},
            {'role': 'user', 'content': f'使用地道的{target_language}Translate:"Knowledge is power."'},
            {'role': 'assistant', 'content': '翻译：“知识就是力量。”'},
            {'role': 'user', 'content': f'使用地道的{target_language}Translate:"To be or not to be, that is the question."'},
            {'role': 'assistant', 'content': '翻译：“生存还是毁灭，这是一个值得考虑的问题。”'},
        ]
    elif target_language == 'Tiếng Việt':
        fixed_message = [
            {'role': 'system', 'content': f'Bạn là một dịch giả cao cấp, chuyên gia chuyển ngữ cho video.\nThông tin video: {info}\nNhiệm vụ: Dịch các câu thoại sau sang {target_language} sao cho SÁT NGHĨA nhất với ngữ cảnh, nhưng phải diễn đạt tự nhiên, thuần Việt và phù hợp để lồng tiếng. Tránh dịch word-by-word máy móc. Hãy chú ý đến đại từ nhân xưng, thuật ngữ chuyên môn và các câu thành ngữ sao cho đúng "chất" nội dung gốc. Bản dịch cần súc tích, nhịp điệu trôi chảy, đảm bảo tính "Tín - Đạt - Nhã".'},
            {'role': 'user', 'content': f'Dịch sang {target_language} một cách tự nhiên và sát nghĩa: "Knowledge is power."'},
            {'role': 'assistant', 'content': 'Dịch: "Tri thức chính là sức mạnh."'},
            {'role': 'user', 'content': f'Dịch sang {target_language} một cách tự nhiên và sát nghĩa: "To be or not to be, that is the question."'},
            {'role': 'assistant', 'content': 'Dịch: "Tồn tại hay không tồn tại, đó mới là vấn đề."'},
        ]
    else:
        # For other languages, we keep the template general
        fixed_message = [
            {'role': 'system', 'content': f'You are a language expert specializing in translating content from various fields. The current task involves translating the transcript of a video titled "{summary["title"]}". The summary of the video is: {summary["summary"]}. Your goal is to translate the following sentences into {target_language}. Please ensure that the translations are accurate, maintain the original meaning and tone, and are expressed in a clear and fluent manner.'},
            {'role': 'user', 'content': 'Please translate the following text: "Original Text"'},
            {'role': 'assistant', 'content': 'Translated text: "Translated Text"'},
            {'role': 'user', 'content': 'Translate the following text: "Another Original Text"'},
            {'role': 'assistant', 'content': 'Translated text: "Another Translated Text"'},
        ]

    history = []
    
    for i, line in enumerate(transcript):
        text = line['text']
        if progress_callback:
            percent = int((i / len(transcript)) * 100)
            progress_callback(percent, f"Đang dịch ({i+1}/{len(transcript)})")

        retry_message = 'Only translate the quoted sentence and give me the final translation.'
        if method == 'Google Translate':
            translation = translator_response(text, to_language = target_language, translator_server='google')
        elif method == 'Bing Translate':
            translation = translator_response(text, to_language = target_language, translator_server='bing')
        else:
            for retry in range(10):
                messages = fixed_message + \
                    history[-30:] + [{'role': 'user',
                                    'content': f'Translate:"{text}"'}]
                # print(messages)
                try:
                    if method == 'LLM':
                        response = llm_response(messages)
                    elif method == 'OpenAI':
                        response = openai_response(messages)
                    elif method == 'Ernie':
                        system_content = messages[0]['content']
                        user_messages = messages[1:]
                        response = ernie_response(user_messages, system=system_content)
                    elif method == '阿里云-通义千问':
                        response = qwen_response(messages)
                    elif method == 'Ollama':  # Add support for Ollama
                        response = ollama_response(messages)
                    elif method == 'Gemini':
                        response = gemini_response(messages)
                    else:
                        raise Exception('Phương pháp không hợp lệ')
                    translation = response.replace('\n', ' ').strip()
                    logger.info(f'Gốc：{text}')
                    logger.info(f'Dịch raw：{translation}')
                    
                    success, validated_msg = valid_translation(text, translation, target_language)
                    if not success:
                        if retry > 3:
                            logger.warning(f"Sau nhiều lần thử vẫn lỗi kiểm duyệt, sử dụng kết quả gốc. Lỗi: {validated_msg}")
                            # Nếu sau 4 lần vẫn lỗi, lấy thô nhưng hãy strip tí
                            translation = translation.split('Dịch:')[-1].split('Result:')[-1].strip()
                        else:
                            retry_message += f"\nLưu ý: {validated_msg}. Hãy chỉ trả về nội dung dịch thô."
                            raise Exception(f'Invalid translation: {validated_msg}')
                    else:
                        translation = validated_msg
                    break
                except Exception as e:
                    logger.error(e)
                    logger.warning('Dịch thất bại')
                    time.sleep(1)
        full_translation.append(translation)
        history.append({'role': 'user', 'content': f'Translate:"{text}"'})
        history.append({'role': 'assistant', 'content': f'Dịch: "{translation}"'})
        time.sleep(0.1)
        
    if progress_callback:
        progress_callback(100, "Dịch xong")
        
    return full_translation

def translate(method, folder, target_language='简体中文', progress_callback=None):
    if os.path.exists(os.path.join(folder, 'translation.json')):
        logger.info(f'Bản dịch đã tồn tại: {folder}')
        if progress_callback: progress_callback(100, "Bản dịch đã tồn tại")
        return True
    
    info_path = os.path.join(folder, 'download.info.json')
    # Not necessarily download.info.json
    if os.path.exists(info_path):
        with open(info_path, 'r', encoding='utf-8') as f:
            info = json.load(f)
        info = get_necessary_info(info)
    else:
        info = {
            'title': os.path.basename(folder),
            'uploader': 'Unknown',
            'description': 'Unknown',
            'upload_date': 'Unknown',
            'tags': []
        }
    transcript_path = os.path.join(folder, 'transcript.json')
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript = json.load(f)
    
    summary_path = os.path.join(folder, 'summary.json')
    if os.path.exists(summary_path):
        summary = json.load(open(summary_path, 'r', encoding='utf-8'))
    else:
        if progress_callback: progress_callback(5, "Đang tóm tắt nội dung...")
        summary = summarize(info, transcript, target_language, method)
        if summary is None:
            logger.error(f'Không thể tóm tắt {folder}')
            return False
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    translation_path = os.path.join(folder, 'translation.json')
    translation = _translate(summary, transcript, target_language, method, progress_callback=progress_callback)
    for i, line in enumerate(transcript):
        line['translation'] = translation[i]
    transcript = split_sentences(transcript)
    with open(translation_path, 'w', encoding='utf-8') as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    return summary, transcript

def translate_all_transcript_under_folder(folder, method, target_language):
    summary_json , translate_json = None, None
    for root, dirs, files in os.walk(folder):
        if 'transcript.json' in files and 'translation.json' not in files:
            summary_json , translate_json = translate(method, root, target_language)
        elif 'translation.json' in files:
            summary_json = json.load(open(os.path.join(root, 'summary.json'), 'r', encoding='utf-8'))
            translate_json = json.load(open(os.path.join(root, 'translation.json'), 'r', encoding='utf-8'))
    # print(summary_json, translate_json)
    return f'Translated all videos under {folder}',summary_json , translate_json

if __name__ == '__main__':
    # translate_all_transcript_under_folder(r'videos', 'LLM' , '简体中文')
    # translate_all_transcript_under_folder(r'videos', 'OpenAI' , '简体中文')
    translate_all_transcript_under_folder(r'videos', 'ernie' , '简体中文')