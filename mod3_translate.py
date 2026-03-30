import os
import time
import json
import argparse
import pysrt
import google.generativeai as genai
from dotenv import load_dotenv
from rich.console import Console
from tqdm import tqdm

load_dotenv()
console = Console()

# Cấu hình Gemini
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)

def translate_batch(texts, glossary=None, model_name='gemini-1.5-flash'):
    """Dịch một mảng các câu văn bằng Gemini API."""
    if not api_key:
        console.print("[bold red]Lỗi:[/bold red] Không tìm thấy GEMINI_API_KEY trong file .env")
        return [None] * len(texts)

    system_prompt = (
        "Bạn là một chuyên gia dịch thuật phim Trung Quốc sang Việt Nam. "
        "Hãy dịch các câu sau sang tiếng Việt một cách tự nhiên, gần gũi, phù hợp với văn cảnh video reup/review. "
        "Giữ nguyên định dạng JSON array trả về đúng số lượng câu. "
    )
    
    if glossary:
        system_prompt += f"\nTuân thủ các từ vựng sau: {json.dumps(glossary, ensure_ascii=False)}"

    # Tạo prompt chứa list các câu
    user_prompt = f"Dịch danh sách srt sau sang tiếng Việt (chỉ trả về JSON list string):\n{json.dumps(texts, ensure_ascii=False)}"
    
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt
    )

    for retry in range(5):
        try:
            response = model.generate_content(user_prompt)
            # Trích xuất JSON từ response text
            txt = response.text.replace('```json', '').replace('```', '').strip()
            translated_list = json.loads(txt)
            
            if len(translated_list) == len(texts):
                return translated_list
            else:
                console.print(f"[yellow]Cảnh báo:[/yellow] Số lượng câu dịch ({len(translated_list)}) không khớp đầu vào ({len(texts)})")
        except Exception as e:
            if "429" in str(e):
                console.print(f"[yellow]Gemini 429 (Rate Limit)...[/yellow] Đang chờ 30 giây (Thử lại {retry+1}/5)")
                time.sleep(30)
                continue
            console.print(f"[red]Lỗi Gemini:[/red] {e}")
            time.sleep(5)
            
    return [None] * len(texts)

def main():
    parser = argparse.ArgumentParser(description="Module 3: Dịch thuật SRT (Gemini 2026)")
    parser.add_argument("--srt_in", required=True, help="File SRT tiếng Trung đầu vào")
    parser.add_argument("--srt_vi_out", required=True, help="File SRT tiếng Việt đầu ra")
    parser.add_argument("--glossary", help="Đường dẫn file JSON từ điển (tên riêng, thuật ngữ)")
    parser.add_argument("--batch_size", type=int, default=20, help="Số dòng dịch mỗi lượt (mặc định 20)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.srt_in):
        console.print(f"[bold red]Lỗi:[/bold red] Không tìm thấy file {args.srt_in}")
        return

    # Tải glossary nếu có
    glossary_data = None
    if args.glossary and os.path.exists(args.glossary):
        with open(args.glossary, 'r', encoding='utf-8') as f:
            glossary_data = json.load(f)

    console.print(f"[bold blue]Đang đọc file SRT:[/bold blue] {args.srt_in}")
    subs = pysrt.open(args.srt_in, encoding='utf-8')
    all_texts = [sub.text.replace('\n', ' ') for sub in subs]
    
    translated_results = []
    
    console.print(f"[bold green]Bắt đầu dịch {len(all_texts)} câu...[/bold green]")
    
    with tqdm(total=len(all_texts), desc="Dịch thuật") as pbar:
        for i in range(0, len(all_texts), args.batch_size):
            batch = all_texts[i : i + args.batch_size]
            translated_batch = translate_batch(batch, glossary=glossary_data)
            
            # Nếu dịch thất bại (None), giữ nguyên bản gốc để không bị mất dòng
            for j, original in enumerate(batch):
                translated_results.append(translated_batch[j] if translated_batch[j] else original)
            
            pbar.update(len(batch))
            # Delay nhẹ để tránh Rate Limit tier free
            time.sleep(2)

    # Cập nhật nội dung SRT
    for i, sub in enumerate(subs):
        sub.text = translated_results[i]
    
    os.makedirs(os.path.dirname(args.srt_vi_out), exist_ok=True)
    subs.save(args.srt_vi_out, encoding='utf-8')
    console.print(f"[bold green]DỊCH THÀNH CÔNG![/bold green] -> {args.srt_vi_out}")

if __name__ == "__main__":
    main()
