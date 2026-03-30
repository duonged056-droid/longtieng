import sys
import re
import os

file_path = r'c:\Users\duong\Downloads\longtieng\tools\step030_translation.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Định nghĩa hàm mới linh hoạt hơn cho Tiếng Việt
new_func = """def valid_translation(text, translation, target_language='简体中文'):
    # Hỗ trợ lọc các khối mã ```
    if (translation.startswith('```') and translation.endswith('```')):
        translation = translation[3:-3]
        if translation.startswith('json'): translation = translation[4:]
        return True, translation_postprocess(translation.strip())
    
    # Lọc các dấu ngoặc kép bọc ngoài
    if (translation.startswith('“') and translation.endswith('”')) or (translation.startswith('"') and translation.endswith('"')):
        translation = translation[1:-1]
        return True, translation_postprocess(translation.strip())
    
    # Tự động lọc các tiền tố phổ biến của AI
    prefixes = [
        '翻译：', '译文：', 'Translation:', 'Dịch sang tiếng Việt:', 
        'Bản dịch:', 'Dịch:', 'Kết quả dịch:', 'Tiếng Việt:', 'Dịch là:'
    ]
    for prefix in prefixes:
        if prefix in translation:
            parts = translation.split(prefix, 1)
            if len(parts) > 1:
                candidate = parts[1].strip()
                if candidate:
                    translation = candidate
                    break

    # Kiểm tra độ dài hợp lý
    is_vietnamese = 'tiếng việt' in target_language.lower() or 'vietnamese' in target_language.lower()
    max_len_factor = 4.0 if is_vietnamese else 2.0
    
    if len(text) <= 5:
        if len(translation) > 50:
            return False, 'Phản hồi quá dài.'
    
    # Từ cấm
    forbidden = ['这句', 'translate', 'Translate']
    if not is_vietnamese:
        forbidden += ['简体中文', '中文', 'translation', 'Translation']
    
    translation = translation.strip().replace('\\n', ' ')
    for word in forbidden:
        if word in translation:
            return False, f"Chứa từ cấm `{word}`."
    
    return True, translation_postprocess(translation)"""

# Thay thế toàn bộ khối hàm valid_translation cũ
# Tìm từ 'def valid_translation' cho đến 'return True, translation_postprocess(translation)'
pattern = r'def valid_translation\(.*?\):.*?return True, translation_postprocess\(translation\)'
content = re.sub(pattern, new_func, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patching successful!")
