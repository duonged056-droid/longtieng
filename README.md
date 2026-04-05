# 🎙️ BumYT AI Dubbing Studio (Premium)

**BumYT AI Dubbing Studio** là giải pháp lồng tiếng video chuyên nghiệp sử dụng trí tuệ nhân tạo (AI). Hệ thống cho phép tách lời, nhận dạng giọng nói, dịch thuật và lồng tiếng tự động với độ chính xác cao và hiệu năng tối ưu trên GPU.

---

## 🔥 Tính năng nổi bật

- **Tăng tốc phần cứng 100%**: Sử dụng `NVENC` và `DXVA2` để giải mã và mã hóa video, giải phóng hoàn toàn gánh nặng cho CPU.
- **Tách âm thanh thông minh (Demucs)**: Tách Vocals và BGM chất lượng cao, hỗ trợ video siêu dài (>2h) với chế độ Segment.
- **Nhận dạng giọng nói (ASR)**: Tích hợp WhisperX (large-v3) với khả năng khớp thời gian (Alignment) chính xác từng từ.
- **Lồng tiếng đa dạng (TTS)**: Hỗ trợ nhiều Engine (Edge TTS, TikTok TTS) với khả năng tinh chỉnh Tốc độ (Rate) và Cao độ (Pitch).
- **Chống giãn nở Video (Timeline Shifting)**: Thuật toán độc quyền giúp khớp thoại mà không làm thay đổi thời lượng video gốc hoặc làm méo hình ảnh.
- **Giao diện Premium**: Sử dụng `rich` để hiển thị tiến trình xử lý và logs chuyên nghiệp.

---

## 🛠️ Yêu cầu hệ thống

1. **Hệ điều hành**: Windows 10/11 (Đề xuất)
2. **Phần cứng**: 
   - GPU: NVIDIA RTX Series (Đề xuất >6GB VRAM để chạy WhisperX large-v3)
   - RAM: Tối thiểu 16GB
3. **Phần mềm**:
   - Python 3.10+
   - FFmpeg (Đã được cấu hình trong PATH)
   - CUDA Toolkit 11.8+ (Để chạy GPU)

---

## 🚀 Hướng dẫn cài đặt

1. **Cài đặt môi trường ảo**:
   ```bash
   python -m venv env
   .\env\Scripts\activate
   ```

2. **Cài đặt các thư viện cần thiết**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Cấu hình FFmpeg**:
   Đảm bảo `ffmpeg.exe` và `ffprobe.exe` có sẵn trong thư mục dự án hoặc trong hệ thống PATH.

---

## 📖 Cách sử dụng

Bạn có thể chạy ứng dụng qua giao diện Desktop:
```bash
python app_desktop.py
```
Hoặc chạy file batch:
`RUN_BUMYT_APP.bat`

---

## 🏗️ Cấu trúc dự án

- `mod1_demucs.py`: Tách Vocals và BGM.
- `mod2_asr.py`: Nhận dạng giọng nói (Trung Quốc/Việt).
- `mod4_tts_dubbing.py`: Lồng tiếng AI (TTS).
- `mod7_video_sync.py`: Hợp nhất video và đồng bộ thoại.
- `mod8_blur_sub.py`: Xử lý phụ đề và hiệu ứng làm mờ.

---

## 📝 Giấy phép
Bản quyền thuộc về **BumYT**. Vui lòng không sao chép khi chưa được phép.
