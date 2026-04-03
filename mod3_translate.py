import os
import time
import json
import argparse
import pysrt
from google import genai
from google.genai import types
from dotenv import load_dotenv
from rich.console import Console
from tqdm import tqdm
import translators as ts
import random
import re

load_dotenv()
console = Console()

# Configuration
KEYS = os.getenv('GEMINI_API_KEY', '').split(',')
OPENAI_KEY = os.getenv('OPENAI_API_KEY', '')
DEFAULT_MODEL = 'gemini-2.0-flash'
OPENAI_MODEL = 'gpt-4o-mini' # Model OpenAI mặc định (ngon bổ rẻ)

def clean_json_response(text):
    """Sạch dữ liệu JSON trả về từ AI để parse được."""
    text = text.strip()
    # Loại bỏ code blocks nếu có
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    # Đôi khi AI trả về các ký tự lạ hoặc comment
    # Tìm đoạn JSON list đầu tiên và cuối cùng
    start_idx = text.find('[')
    end_idx = text.rfind(']')
    if start_idx != -1 and end_idx != -1:
        return text[start_idx : end_idx + 1]
    return text

def translate_google(texts, to_lang='vi', from_lang='zh'):
    """Dịch bằng Google/Bing Translate (miễn phí qua thư viện translators)."""
    # Map zh -> zh-CN for Google
    f_lang = 'zh-CN' if from_lang == 'zh' else from_lang
    
    # Thử dịch bằng Google trước
    engines = ['google', 'bing']
    for engine in engines:
        try:
            results = ts.translate_text(texts, from_language=f_lang, to_language=to_lang, translator=engine)
            if results:
                if isinstance(results, str):
                    return [results]
                return results
        except Exception as e:
            console.print(f"[yellow]Lỗi {engine} Translate:[/yellow] {e}. Đang thử engine khác...")
            time.sleep(2)
            
    return [None] * len(texts)

def translate_openai(texts, glossary=None, from_lang='zh', model_name=OPENAI_MODEL):
    """Dịch bằng OpenAI API (ChatGPT)."""
    if not OPENAI_KEY:
        console.print("[bold red]Lỗi:[/bold red] Không tìm thấy OPENAI_API_KEY trong file .env")
        return [None] * len(texts)

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)

    lang_from_text = "tự động nhận diện" if from_lang == 'auto' else from_lang
    system_prompt = (
        f"Bạn là một chuyên gia dịch thuật phim chuyên nghiệp. "
        f"Dịch danh sách các câu sau từ {lang_from_text} sang tiếng Việt tự nhiên, phù hợp văn cảnh video. "
        "TRẢ VỀ DUY NHẤT 1 MẢNG JSON CÁC CHUỖI (JSON ARRAY OF STRINGS)."
    )
    if glossary:
        system_prompt += f"\nTuân thủ Glossary: {json.dumps(glossary, ensure_ascii=False)}"

    user_prompt = f"Dịch list sau ({len(texts)} câu):\n{json.dumps(texts, ensure_ascii=False)}"

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"} if "gpt-4o" in model_name else None
        )
        
        txt = response.choices[0].message.content
        # OpenAI đôi khi trả về object {"translations": [...]} nếu dùng json_mode
        # Cố gắng tìm mảng trong text
        try:
            data = json.loads(txt)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # Tìm value là list đầu tiên
                for v in data.values():
                    if isinstance(v, list): return v
        except:
            pass
            
        cleaned = clean_json_response(txt)
        return json.loads(cleaned)
    except Exception as e:
        console.print(f"[red]Lỗi OpenAI:[/red] {e}")
        return [None] * len(texts)

def translate_gemini(texts, glossary=None, from_lang='zh', model_name=DEFAULT_MODEL):
    """Dịch một mảng các câu văn bằng Gemini API với xử lý lỗi chuyên sâu."""
    api_key_list = [k.strip() for k in KEYS if k.strip()]
    if not api_key_list:
        console.print("[bold red]Lỗi:[/bold red] Không tìm thấy GEMINI_API_KEY trong file .env")
        return [None] * len(texts)

    lang_from_text = "tự động nhận diện" if from_lang == 'auto' else from_lang
    system_prompt = (
        f"Bạn là một chuyên gia dịch thuật phim chuyên nghiệp từ {lang_from_text} sang tiếng Việt. "
        "Dịch danh sách các câu sau sang tiếng Việt tự nhiên, phù hợp văn cảnh video review/reup phim. "
        "QUY TẮC QUAN TRỌNG:\n"
        "1. Trả về đúng định dạng JSON List (mảng các chuỗi).\n"
        "2. Số lượng phần tử trả về PHẢI CHÍNH XÁC bằng số lượng đầu vào.\n"
        "3. Không giải thích, không thêm văn bản ngoài JSON."
    )
    
    if glossary:
        system_prompt += f"\nTuân thủ bảng tra thuật ngữ (Glossary): {json.dumps(glossary, ensure_ascii=False)}"

    user_prompt = f"Dịch list sau (số lượng: {len(texts)} câu):\n{json.dumps(texts, ensure_ascii=False)}"
    
    # Tạo bản sao danh sách key để xoay vòng
    available_keys = api_key_list.copy()
    
    for retry in range(10): # Tăng lên 10 lần thử
        if not available_keys:
            console.print(f"[yellow]Tất cả Key đều bị giới hạn hoặc lỗi.[/yellow] Nghỉ 60s rồi thử lại các key...")
            time.sleep(60)
            available_keys = api_key_list.copy()
            continue

        current_key = random.choice(available_keys)
        try:
            client = genai.Client(api_key=current_key)
            
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json"
                )
            )
            
            cleaned_text = clean_json_response(response.text)
            translated_list = json.loads(cleaned_text)
            
            if len(translated_list) == len(texts):
                return translated_list
            else:
                console.print(f"[yellow]Cảnh báo:[/yellow] Kích thước không khớp. Thử lại...")
        except Exception as e:
            if "429" in str(e):
                console.print(f"[yellow]Key {current_key[:10]}... bị Rate Limit (429). Đang đổi key khác...[/yellow]")
                if current_key in available_keys:
                    available_keys.remove(current_key)
                continue
            console.print(f"[red]Lỗi Gemini (Lượt {retry+1}):[/red] {e}")
            time.sleep(5)
            
    return [None] * len(texts)

def main():
    parser = argparse.ArgumentParser(description="Module 3: Dịch thuật SRT (Nâng cấp 2026)")
    parser.add_argument("--srt_in", required=True, help="File SRT đầu vào")
    parser.add_argument("--srt_out", required=True, help="File SRT đầu ra")
    parser.add_argument("--service", type=str, default="gemini", choices=["gemini", "google", "openai"], help="Dịch vụ dịch thuật")
    parser.add_argument("--to_lang", default="vi", help="Ngôn ngữ đích (vi, en, ...)")
    parser.add_argument("--from_lang", default="zh", help="Ngôn ngữ nguồn (zh, en, ja, ...)")
    parser.add_argument("--glossary", help="Đường dẫn file JSON từ điển")
    parser.add_argument("--batch_size", type=int, default=50, help="Số dòng dịch mỗi lượt (mặc định 50)")
    parser.add_argument("--multi_thread", action="store_true", help="Dịch đa luồng (chỉ dùng với gemini nếu có nhiều key)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.srt_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file {args.srt_in}")
        return

    # Tải glossary
    glossary_data = None
    if args.glossary and os.path.exists(args.glossary):
        try:
            with open(args.glossary, 'r', encoding='utf-8') as f:
                glossary_data = json.load(f)
        except:
            console.print("[yellow]Bỏ qua glossary do lỗi định dạng file.[/yellow]")

    subs = pysrt.open(args.srt_in, encoding='utf-8')
    all_texts = [sub.text.replace('\n', ' ') for sub in subs]
    translated_results = [None] * len(all_texts)
    
    console.print(f"[bold blue]Dịch thuật SRT:[/bold blue] {args.srt_in} -> {args.srt_out} (Dùng {args.service})")
    
    # Chia batch
    batches = []
    for i in range(0, len(all_texts), args.batch_size):
        batches.append((i, all_texts[i : i + args.batch_size]))
        
    def process_batch(b):
        start_idx, batch = b
        if args.service == "google":
            translated = translate_google(batch, to_lang=args.to_lang, from_lang=args.from_lang)
        elif args.service == "openai":
            translated = translate_openai(batch, glossary=glossary_data, from_lang=args.from_lang)
        else:
            translated = translate_gemini(batch, glossary=glossary_data, from_lang=args.from_lang)
            # Nếu Gemini lỗi (trả về toàn None), tự động fallback sang Google để không bị ngắt quãng
            if all(t is None for t in translated):
                console.print(f"[yellow]Gemini quá tải (429/Error). Tự động dùng Google Translate cho đoạn này...[/yellow]")
                translated = translate_google(batch, to_lang=args.to_lang, from_lang=args.from_lang)
            
        # Cuối cùng nếu vẫn lỗi thì mới giữ nguyên gốc
        final_batch = []
        for j, t in enumerate(translated):
            final_batch.append(t if t else batch[j])
        return start_idx, final_batch

    import concurrent.futures
    with tqdm(total=len(all_texts), desc="Đang dịch") as pbar:
        if args.multi_thread and args.service == "gemini" and len(KEYS) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(process_batch, b): b for b in batches}
                for future in concurrent.futures.as_completed(futures):
                    start_idx, translated_batch = future.result()
                    for j, res in enumerate(translated_batch):
                        translated_results[start_idx + j] = res
                    pbar.update(len(translated_batch))
        else:
            for b in batches:
                start_idx, translated_batch = process_batch(b)
                for j, res in enumerate(translated_batch):
                    translated_results[start_idx + j] = res
                pbar.update(len(translated_batch))
                if args.service == "gemini":
                    time.sleep(1) # Tránh rate limit nhẹ

    # Lưu kết quả
    for i, sub in enumerate(subs):
        sub.text = translated_results[i]
    
    os.makedirs(os.path.dirname(args.srt_out), exist_ok=True)
    subs.save(args.srt_out, encoding='utf-8')
    console.print(f"[bold green]XÁC NHẬN:[/bold green] Đã dịch xong và lưu tại {args.srt_out}")

if __name__ == "__main__":
    main()
