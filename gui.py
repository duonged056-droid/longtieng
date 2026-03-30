import sys
import os

# PHIÊN BẢN ĐẶC TRỊ - ÉP DÙNG GPU NGAY TỪ DÒNG ĐẦU TIÊN
if sys.platform == "win32":
    import site
    # Tìm kiếm trong tất cả các thư mục site-packages khả thi
    possible_paths = site.getsitepackages() + [os.path.join(os.path.dirname(os.path.abspath(__file__)), "env", "Lib", "site-packages")]
    for sp in possible_paths:
        nvidia_base = os.path.join(sp, "nvidia")
        if os.path.exists(nvidia_base):
            for sub_lib in ["cublas", "cudnn", "cuda_nvrtc"]:
                bin_path = os.path.join(nvidia_base, sub_lib, "bin")
                if os.path.exists(bin_path):
                    try:
                        os.add_dll_directory(bin_path)
                        # Ghim thêm vào PATH để chắc chắn 100%
                        if bin_path not in os.environ["PATH"]:
                            os.environ["PATH"] = bin_path + os.pathsep + os.environ["PATH"]
                    except Exception:
                        pass

import torch

# KIỂM TRA TRẠNG THÁI GPU
if torch.cuda.is_available():
    print(f"✅ ĐÃ NHẬN CARD ĐỒ HỌA: {torch.cuda.get_device_name(0)}")
    os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"
else:
    print("❌ CẢNH BÁO: CHƯA NHẬN CARD ĐỒ HỌA. HỆ THỐNG ĐANG CHẠY BẰNG CPU (RẤT CHẬM)")

from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PySide6.QtCore import Qt

# 请确保导入正确模块
try:
    # 导入自定义控件文件
    from ui_components import (CustomSlider, FloatSlider, RadioButtonGroup,
                               AudioSelector, VideoPlayer)

    # 导入各个功能标签页
    from tabs.full_auto_tab import FullAutoTab
    from tabs.settings_tab import SettingsTab
    from tabs.download_tab import DownloadTab
    from tabs.demucs_tab import DemucsTab
    from tabs.asr_tab import ASRTab
    from tabs.translation_tab import TranslationTab
    from tabs.tts_tab import TTSTab
    from tabs.video_tab import SynthesizeVideoTab
    from tabs.linly_talker_tab import LinlyTalkerTab

    # 尝试导入实际的功能模块
    try:
        from tools.step000_video_downloader import download_from_url
        from tools.step010_demucs_vr import separate_all_audio_under_folder
        from tools.step020_asr import transcribe_all_audio_under_folder
        from tools.step030_translation import translate_all_transcript_under_folder
        from tools.step040_tts import generate_all_wavs_under_folder
        from tools.step050_synthesize_video import synthesize_all_video_under_folder
        from tools.do_everything import do_everything
        from tools.utils import SUPPORT_VOICE
    except ImportError as e:
        print(f"Cảnh báo: Không thể nhập một số mô-đun công cụ: {e}")
        # Định nghĩa danh sách giọng nói hỗ trợ tạm thời
        SUPPORT_VOICE = ['vi-VN-HoaiMyNeural', 'vi-VN-NamMinhNeural', 'zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural',
                         'en-US-JennyNeural', 'ja-JP-NanamiNeural']

except ImportError as e:
    print(f"Lỗi: Khởi tạo ứng dụng thất bại: {e}")
    sys.exit(1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Công cụ AI Lồng tiếng/Dịch thuật video đa ngôn ngữ - Linly-Dubbing")
        self.resize(1024, 768)

        # 创建选项卡
        self.tab_widget = QTabWidget()

        # 创建标签页实例
        self.full_auto_tab = FullAutoTab()
        self.settings_tab = SettingsTab()

        # 连接配置页面的配置变更信号到一键自动化页面
        self.settings_tab.config_changed.connect(self.full_auto_tab.update_config)

        # Thêm các tab
        self.tab_widget.addTab(self.full_auto_tab, "Tự động hóa Một lần nhấp")
        self.tab_widget.addTab(self.settings_tab, "Cài đặt")
        self.tab_widget.addTab(DownloadTab(), "Tải video tự động")
        self.tab_widget.addTab(DemucsTab(), "Tách giọng nói")
        self.tab_widget.addTab(ASRTab(), "Nhận dạng AI")
        self.tab_widget.addTab(TranslationTab(), "Dịch phụ đề")
        self.tab_widget.addTab(TTSTab(), "Tổng hợp giọng nói")
        self.tab_widget.addTab(SynthesizeVideoTab(), "Tổng hợp video")
        self.tab_widget.addTab(LinlyTalkerTab(), "Linly-Talker (Đang phát triển)")

        # 设置中央窗口部件
        self.setCentralWidget(self.tab_widget)


def main():
    # 设置高DPI缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # 设置应用样式
    app.setStyle("Fusion")

    # 创建主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()