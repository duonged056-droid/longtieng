import os
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
                               QPushButton, QMessageBox, QSplitter, QLineEdit, QFileDialog)
from PySide6.QtCore import Qt, Signal

from ui_components import (CustomSlider, FloatSlider, RadioButtonGroup,
                           AudioSelector, VideoPlayer)


class SettingsTab(QWidget):
    """
    Trang cấu hình, cho phép người dùng thiết lập tất cả các tham số xử lý và lưu vào config.json
    """
    # 定义配置变更信号
    config_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_config()

    def init_ui(self):
        """初始化配置页面UI"""
        self.layout = QVBoxLayout(self)

        # 创建一个滚动区域用于容纳配置项
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)

        # 添加所有配置控件
        self.add_config_widgets()

        # Tạo nút lưu cấu hình
        self.button_layout = QHBoxLayout()
        self.save_config_button = QPushButton("Lưu cấu hình人员") # Modified for consistency
        self.save_config_button = QPushButton("Lưu cấu hình")
        self.save_config_button.clicked.connect(self.save_config)
        self.save_config_button.setMinimumHeight(40)
        self.save_config_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.reset_config_button = QPushButton("Đặt lại cấu hình")
        self.reset_config_button.clicked.connect(self.reset_config)
        self.reset_config_button.setMinimumHeight(40)
        self.button_layout.addWidget(self.reset_config_button)
        self.button_layout.addWidget(self.save_config_button)

        # 设置滚动区域
        self.scroll_area.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll_area)
        self.layout.addLayout(self.button_layout)
        self.setLayout(self.layout)

    def add_config_widgets(self):
        """添加所有配置控件"""
        # Cấu hình video
        self.scroll_layout.addWidget(QLabel("=== Cấu hình tải video ==="))
        self.scroll_layout.addWidget(QLabel("Thư mục đầu ra video"))
        
        folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_output_folder)
        folder_layout.addWidget(self.video_folder)
        folder_layout.addWidget(self.btn_select_folder)
        self.scroll_layout.addLayout(folder_layout)

        # Độ phân giải
        self.resolution = RadioButtonGroup(
            ['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'],
            "Độ phân giải",
            '1080p'
        )
        self.scroll_layout.addWidget(self.resolution)

        # Số lượng video tải xuống
        self.video_count = CustomSlider(1, 100, 1, "Số lượng video tải xuống", 5)
        self.scroll_layout.addWidget(self.video_count)

        # Cấu hình xử lý âm thanh
        self.scroll_layout.addWidget(QLabel("=== Cấu hình xử lý âm thanh ==="))
        # Mô hình
        self.model = RadioButtonGroup(
            ['htdemucs', 'htdemucs_ft', 'htdemucs_6s', 'hdemucs_mmi', 'mdx', 'mdx_extra', 'mdx_q', 'mdx_extra_q',
             'SIG'],
            "Mô hình tách giọng nói",
            'htdemucs'
        )
        self.scroll_layout.addWidget(self.model)

        # Thiết bị tính toán
        self.device = RadioButtonGroup(['auto', 'cuda', 'cpu'], "Thiết bị tính toán", 'auto')
        self.scroll_layout.addWidget(self.device)

        # Số lần dịch chuyển
        self.shifts = CustomSlider(0, 10, 1, "Số lần dịch chuyển (Shifts)", 1)
        self.scroll_layout.addWidget(self.shifts)

        # Cấu hình ASR
        self.scroll_layout.addWidget(QLabel("=== Cấu hình nhận dạng giọng nói ==="))
        # Chọn mô hình ASR
        self.asr_model_label = QLabel("Chọn mô hình ASR")
        self.scroll_layout.addWidget(self.asr_model_label)
        self.asr_model = RadioButtonGroup(['WhisperX', 'FunASR'], "Chọn mô hình ASR", 'WhisperX')
        self.scroll_layout.addWidget(self.asr_model)

        # Kích thước mô hình WhisperX
        self.whisperx_size = RadioButtonGroup(['large', 'medium', 'small', 'base', 'tiny'], "Kích thước mô hình WhisperX", 'large')
        self.scroll_layout.addWidget(self.whisperx_size)

        # Batch Size
        self.batch_size = CustomSlider(1, 128, 1, "Batch Size (Kích thước lô)", 2)
        self.scroll_layout.addWidget(self.batch_size)

        # Tách nhiều người nói
        self.separate_speakers = RadioButtonGroup([True, False], "Tách nhiều người nói", True)
        self.scroll_layout.addWidget(self.separate_speakers)

        # Số người nói tối thiểu
        self.min_speakers = RadioButtonGroup([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], "Số người nói tối thiểu", None)
        self.scroll_layout.addWidget(self.min_speakers)

        # Số người nói tối đa
        self.max_speakers = RadioButtonGroup([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], "Số người nói tối đa", None)
        self.scroll_layout.addWidget(self.max_speakers)

        # Cấu hình dịch thuật
        self.scroll_layout.addWidget(QLabel("=== Cấu hình dịch thuật ==="))
        # Phương thức dịch
        self.translation_method_label = QLabel("Phương thức dịch")
        self.scroll_layout.addWidget(self.translation_method_label)
        self.translation_method = RadioButtonGroup(
            ['OpenAI', 'LLM', 'Google Translate', 'Bing Translate', 'Ernie', '火山引擎-deepseek', "deepseek-api",
             "阿里云-通义千问","Ollama"], "Phương thức dịch", 'LLM')
        self.scroll_layout.addWidget(self.translation_method)

        # Ngôn ngữ mục tiêu (Dịch)
        self.target_language_translation_label = QLabel("Ngôn ngữ mục tiêu (Dịch)")
        self.scroll_layout.addWidget(self.target_language_translation_label)
        self.target_language_translation = RadioButtonGroup(
            ['Tiếng Việt', 'Tiếng Trung (Giản thể)', 'Tiếng Trung (Phồn thể)', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn'], "Ngôn ngữ mục tiêu (Dịch)", 'Tiếng Việt')
        self.scroll_layout.addWidget(self.target_language_translation)

        # Cấu hình TTS
        self.scroll_layout.addWidget(QLabel("=== Cấu hình tổng hợp giọng nói ==="))
        # Phương pháp tạo giọng nói AI
        self.tts_method_label = QLabel("Phương pháp tạo giọng nói AI")
        self.scroll_layout.addWidget(self.tts_method_label)
        self.tts_method = RadioButtonGroup(['xtts', 'cosyvoice', 'EdgeTTS'], "Phương pháp tạo giọng nói AI", 'EdgeTTS')
        self.scroll_layout.addWidget(self.tts_method)

        # Ngôn ngữ mục tiêu (TTS)
        self.target_language_tts_label = QLabel("Ngôn ngữ mục tiêu (TTS)")
        self.scroll_layout.addWidget(self.target_language_tts_label)
        self.target_language_tts = RadioButtonGroup(
            ['Tiếng Việt', 'Tiếng Trung', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn', 'Tiếng Tây Ban Nha', 'Tiếng Pháp'], "Ngôn ngữ mục tiêu (TTS)", 'Tiếng Việt')
        self.scroll_layout.addWidget(self.target_language_tts)

        # Chọn giọng nói EdgeTTS
        self.edge_tts_voice_label = QLabel("Chọn giọng nói EdgeTTS")
        self.scroll_layout.addWidget(self.edge_tts_voice_label)
        self.edge_tts_voice = RadioButtonGroup(
            ['vi-VN-HoaiMyNeural', 'vi-VN-NamMinhNeural', 'zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural', 'en-US-JennyNeural', 'ja-JP-NanamiNeural'],
            "Chọn giọng nói EdgeTTS", 'vi-VN-HoaiMyNeural')
        self.scroll_layout.addWidget(self.edge_tts_voice)

        # Cấu hình tổng hợp video
        self.scroll_layout.addWidget(QLabel("=== Cấu hình tổng hợp video ==="))
        # Thêm phụ đề
        self.add_subtitles = RadioButtonGroup([True, False], "Thêm phụ đề", True)
        self.scroll_layout.addWidget(self.add_subtitles)

        # Tốc độ tăng tốc
        self.speed_factor = FloatSlider(0.5, 2, 0.05, "Tốc độ tăng tốc", 1.00)
        self.scroll_layout.addWidget(self.speed_factor)

        # Tốc độ khung hình
        self.frame_rate = CustomSlider(1, 60, 1, "Tốc độ khung hình (FPS)", 30)
        self.scroll_layout.addWidget(self.frame_rate)

        # Nhạc nền
        self.background_music = AudioSelector("Nhạc nền")
        self.scroll_layout.addWidget(self.background_music)

        # Âm lượng nhạc nền
        self.bg_music_volume = FloatSlider(0, 1, 0.05, "Âm lượng nhạc nền", 0.5)
        self.scroll_layout.addWidget(self.bg_music_volume)

        # Âm lượng video
        self.video_volume = FloatSlider(0, 1, 0.05, "Âm lượng video", 1.0)
        self.scroll_layout.addWidget(self.video_volume)

        # Độ phân giải (đầu ra)
        self.output_resolution = RadioButtonGroup(
            ['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'],
            "Độ phân giải đầu ra",
            '1080p'
        )
        self.scroll_layout.addWidget(self.output_resolution)

        # Cấu hình nâng cao
        self.scroll_layout.addWidget(QLabel("=== Cấu hình nâng cao ==="))
        # Số luồng tối đa (Max Workers)
        self.max_workers = CustomSlider(1, 100, 1, "Số luồng tối đa (Max Workers)", 1)
        self.scroll_layout.addWidget(self.max_workers)

        # Số lần thử lại tối đa (Max Retries)
        self.max_retries = CustomSlider(1, 10, 1, "Số lần thử lại tối đa (Max Retries)", 3)
        self.scroll_layout.addWidget(self.max_retries)

    def select_output_folder(self):
        """选择输出文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def get_config(self):
        """从UI控件中获取当前配置"""
        config = {
            "video_folder": self.video_folder.text(),
            "resolution": self.resolution.value(),
            "video_count": self.video_count.value(),
            "model": self.model.value(),
            "device": self.device.value(),
            "shifts": self.shifts.value(),
            "asr_model": self.asr_model.value(),
            "whisperx_size": self.whisperx_size.value(),
            "batch_size": self.batch_size.value(),
            "separate_speakers": self.separate_speakers.value(),
            "min_speakers": self.min_speakers.value(),
            "max_speakers": self.max_speakers.value(),
            "translation_method": self.translation_method.value(),
            "target_language_translation": self.target_language_translation.value(),
            "tts_method": self.tts_method.value(),
            "target_language_tts": self.target_language_tts.value(),
            "edge_tts_voice": self.edge_tts_voice.value(),
            "add_subtitles": self.add_subtitles.value(),
            "speed_factor": self.speed_factor.value(),
            "frame_rate": self.frame_rate.value(),
            "background_music": self.background_music.value(),
            "bg_music_volume": self.bg_music_volume.value(),
            "video_volume": self.video_volume.value(),
            "output_resolution": self.output_resolution.value(),
            "max_workers": self.max_workers.value(),
            "max_retries": self.max_retries.value()
        }
        return config

    def apply_config(self, config):
        """将配置应用到UI控件"""
        try:
            # 基本设置
            self.video_folder.setText(config.get("video_folder", "videos"))

            # 为每个单选按钮组应用更健壮的选择逻辑
            # 分辨率
            resolution_value = config.get("resolution", "1080p")
            self._set_radio_button(self.resolution.buttons, resolution_value, "1080p")

            # 视频数量
            self.video_count.setValue(config.get("video_count", 5))

            # 模型
            model_value = config.get("model", "htdemucs")
            self._set_radio_button(self.model.buttons, model_value, "htdemucs")

            # 设备
            device_value = config.get("device", "auto")
            self._set_radio_button(self.device.buttons, device_value, "auto")

            # 移位次数
            self.shifts.setValue(config.get("shifts", 5))

            # ASR模型
            asr_model_value = config.get("asr_model", "WhisperX")
            self._set_radio_button(self.asr_model.buttons, asr_model_value, "WhisperX")

            # WhisperX模型大小
            whisperx_size_value = config.get("whisperx_size", "large")
            self._set_radio_button(self.whisperx_size.buttons, whisperx_size_value, "large")

            # 批处理大小
            self.batch_size.setValue(config.get("batch_size", 4))

            # 分离多个说话人
            separate_speakers_value = config.get("separate_speakers", True)
            self._set_radio_button(self.separate_speakers.buttons, separate_speakers_value, True)

            # 最小说话人数
            min_speakers_value = config.get("min_speakers", None)
            self._set_radio_button(self.min_speakers.buttons, min_speakers_value, None)

            # 最大说话人数
            max_speakers_value = config.get("max_speakers", None)
            self._set_radio_button(self.max_speakers.buttons, max_speakers_value, None)

            # 翻译方式
            translation_method_value = config.get("translation_method", "LLM")
            self._set_radio_button(self.translation_method.buttons, translation_method_value, "LLM")

            # 目标语言 (翻译)
            target_lang_trans_value = config.get("target_language_translation", "简体中文")
            self._set_radio_button(self.target_language_translation.buttons, target_lang_trans_value, "简体中文")

            # TTS方法
            tts_method_value = config.get("tts_method", "EdgeTTS")
            self._set_radio_button(self.tts_method.buttons, tts_method_value, "EdgeTTS")

            # 目标语言 (TTS)
            target_lang_tts_value = config.get("target_language_tts", "中文")
            self._set_radio_button(self.target_language_tts.buttons, target_lang_tts_value, "中文")

            # EdgeTTS声音选择
            edge_tts_voice_value = config.get("edge_tts_voice", "zh-CN-XiaoxiaoNeural")
            self._set_radio_button(self.edge_tts_voice.buttons, edge_tts_voice_value, "zh-CN-XiaoxiaoNeural")

            # 添加字幕
            add_subtitles_value = config.get("add_subtitles", True)
            self._set_radio_button(self.add_subtitles.buttons, add_subtitles_value, True)

            # 加速倍数
            self.speed_factor.setValue(config.get("speed_factor", 1.00))

            # 帧率
            self.frame_rate.setValue(config.get("frame_rate", 30))

            # 背景音乐
            if config.get("background_music"):
                self.background_music.file_path.setText(config.get("background_music"))

            # 背景音乐音量
            self.bg_music_volume.setValue(config.get("bg_music_volume", 0.5))

            # 视频音量
            self.video_volume.setValue(config.get("video_volume", 1.0))

            # 输出分辨率
            output_resolution_value = config.get("output_resolution", "1080p")
            self._set_radio_button(self.output_resolution.buttons, output_resolution_value, "1080p")

            # 最大工作线程数
            self.max_workers.setValue(config.get("max_workers", 1))

            # 最大重试次数
            self.max_retries.setValue(config.get("max_retries", 3))

        except Exception as e:
            QMessageBox.warning(self, "Lỗi tải cấu hình", f"Có lỗi khi tải cấu hình: {str(e)}")

    def _set_radio_button(self, buttons, value, default_value):
        """辅助方法：安全地设置单选按钮值"""
        try:
            # 尝试找到匹配的选项并选中对应的按钮
            for option, button in buttons:
                if option == value:
                    button.setChecked(True)
                    return

            # 如果没找到，使用默认值
            for option, button in buttons:
                if option == default_value:
                    button.setChecked(True)
                    return
        except Exception:
            # 如果出现任何错误，尝试使用默认值
            for option, button in buttons:
                if option == default_value:
                    button.setChecked(True)
                    return

    def save_config(self):
        """保存配置到JSON文件"""
        try:
            config = self.get_config()
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(config_dir, "config.json")

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)

            QMessageBox.information(self, "Lưu thành công", f"Cấu hình đã được lưu vào {config_path}")

            # 发送配置变更信号
            self.config_changed.emit(config)

        except Exception as e:
            QMessageBox.critical(self, "Lưu thất bại", f"Có lỗi khi lưu cấu hình: {str(e)}")

    def load_config(self):
        """从JSON文件加载配置"""
        try:
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(config_dir, "config.json")

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.apply_config(config)
        except Exception as e:
            QMessageBox.warning(self, "Tải cấu hình thất bại", f"Có lỗi khi tải cấu hình: {str(e)}")

    def reset_config(self):
        """Đặt lại cấu hình về mặc định"""
        if QMessageBox.question(self, "Xác nhận đặt lại", "Bạn có chắc chắn muốn đặt lại tất cả cấu hình về mặc định không?") == QMessageBox.Yes:
            # 应用默认配置
            default_config = {
                "video_folder": "videos",
                "resolution": "1080p",
                "video_count": 5,
                "model": "htdemucs",
                "device": "auto",
                "shifts": 1,
                "asr_model": "WhisperX",
                "whisperx_size": "large",
                "batch_size": 2,
                "separate_speakers": True,
                "min_speakers": None,
                "max_speakers": None,
                "translation_method": "LLM",
                "target_language_translation": "Tiếng Việt",
                "tts_method": "EdgeTTS",
                "target_language_tts": "Tiếng Việt",
                "edge_tts_voice": "vi-VN-HoaiMyNeural",
                "add_subtitles": True,
                "speed_factor": 1.00,
                "frame_rate": 30,
                "background_music": None,
                "bg_music_volume": 0.5,
                "video_volume": 1.0,
                "output_resolution": "1080p",
                "max_workers": 1,
                "max_retries": 3
            }
            self.apply_config(default_config)
            QMessageBox.information(self, "Đặt lại thành công", "Tất cả cấu hình đã được đặt lại về giá trị mặc định")