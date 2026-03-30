# -*- coding: utf-8 -*-
import os
import google.generativeai as genai
from dotenv import load_dotenv
from loguru import logger
import time

load_dotenv()

api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)

def gemini_response(messages, model_name='gemini-flash-latest'):
    if not api_key:
        logger.error("GEMINI_API_KEY not found in .env")
        return "Error: GEMINI_API_KEY not found"
    
    for retry in range(10):
        try:
            # Chuyển đổi định dạng messages OpenAI/LLM sang Gemini format
            gemini_messages = []
            system_instruction = ""
            
            for msg in messages:
                role = msg['role']
                content = msg['content']
                if role == 'system':
                    system_instruction += content + "\n"
                elif role == 'user':
                    gemini_messages.append({'role': 'user', 'parts': [content]})
                elif role == 'assistant':
                    gemini_messages.append({'role': 'model', 'parts': [content]})
            
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction if system_instruction else None
            )
            
            response = model.generate_content(gemini_messages)
            
            if not response or not response.text:
                 raise Exception("Empty response from Gemini")
                 
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                # Lỗi quá tải hạn ngạch (Free tier thường giới hạn 15/phút)
                logger.warning(f"Lỗi Gemini 429 (Quá tải hạn ngạch). Đang chờ 30 giây rồi thử lại ({retry+1}/10)...")
                time.sleep(30)
                continue
            
            if retry < 9:
                logger.warning(f"Lỗi Gemini API (Thử lại {retry+1}/10): {e}")
                time.sleep(5)
                continue
            
            logger.error(f"Gemini API Hoàn toàn thất bại: {e}")
            return f"Error: {e}"

if __name__ == '__main__':
    test_message = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Chào bạn, hãy giới thiệu bản thân bằng tiếng Việt."}
    ]
    response = gemini_response(test_message)
    print(response)
