from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QComboBox, QPushButton, QMessageBox, QGroupBox, QFileDialog)

# 尝试导入实际的功能模块
try:
    from tools.step040_tts import generate_all_wavs_under_folder
    from tools.utils import SUPPORT_VOICE
except ImportError:
    # 定义临时的支持语音列表
    SUPPORT_VOICE = ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural',
                     'en-US-JennyNeural', 'ja-JP-NanamiNeural']


class TTSTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # Thư mục video
        self.video_folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_tts_folder)
        self.video_folder_layout.addWidget(self.video_folder)
        self.video_folder_layout.addWidget(self.btn_select_folder)
        
        self.layout.addWidget(QLabel("Thư mục video"))
        self.layout.addLayout(self.video_folder_layout)

        # File SRT lẻ
        self.srt_file_layout = QHBoxLayout()
        self.srt_file = QLineEdit()
        self.btn_select_file = QPushButton("📜 Chọn file SRT")
        self.btn_select_file.clicked.connect(self.select_srt_file)
        self.srt_file_layout.addWidget(self.srt_file)
        self.srt_file_layout.addWidget(self.btn_select_file)
        
        self.layout.addWidget(QLabel("Hoặc chọn file SRT cục bộ"))
        self.layout.addLayout(self.srt_file_layout)

    def select_tts_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_srt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file phụ đề", "", "Subtitle Files (*.srt);;All Files (*)")
        if file_path:
            self.srt_file.setText(file_path)

        # Phương pháp tạo giọng nói AI
        self.tts_method = QComboBox()
        self.tts_method.addItems(['xtts', 'cosyvoice', 'EdgeTTS'])
        self.tts_method.setCurrentText('EdgeTTS')
        self.layout.addWidget(QLabel("Phương pháp tạo giọng nói AI"))
        self.layout.addWidget(self.tts_method)

        # Ngôn ngữ mục tiêu
        self.target_language = QComboBox()
        self.target_language.addItems(['Tiếng Việt', 'Tiếng Trung', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn', 'Tiếng Tây Ban Nha', 'Tiếng Pháp'])
        self.target_language.setCurrentText('Tiếng Việt')
        self.layout.addWidget(QLabel("Ngôn ngữ mục tiêu"))
        self.layout.addWidget(self.target_language)

        # Chọn giọng nói EdgeTTS
        self.edge_tts_voice = QComboBox()
        self.edge_tts_voice.addItems(SUPPORT_VOICE)
        self.edge_tts_voice.setCurrentText('vi-VN-HoaiMyNeural')
        self.layout.addWidget(QLabel("Chọn giọng nói EdgeTTS"))
        self.layout.addWidget(self.edge_tts_voice)

        # Nút thực hiện
        self.run_button = QPushButton("Bắt đầu tạo giọng nói")
        self.run_button.clicked.connect(self.run_tts)
        self.layout.addWidget(self.run_button)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.layout.addWidget(QLabel("Trạng thái tổng hợp:"))
        self.layout.addWidget(self.status_label)

        # Điều khiển phát âm thanh
        synthesized_group = QGroupBox("Giọng nói tổng hợp")
        synthesized_layout = QVBoxLayout()
        self.synthesized_play_button = QPushButton("Phát giọng nói tổng hợp")
        synthesized_layout.addWidget(self.synthesized_play_button)
        synthesized_group.setLayout(synthesized_layout)

        original_group = QGroupBox("Âm thanh gốc")
        original_layout = QVBoxLayout()
        self.original_play_button = QPushButton("Phát âm thanh gốc")
        original_layout.addWidget(self.original_play_button)
        original_group.setLayout(original_layout)

        audio_layout = QHBoxLayout()
        audio_layout.addWidget(synthesized_group)
        audio_layout.addWidget(original_group)

        self.layout.addLayout(audio_layout)
        self.setLayout(self.layout)

    def select_tts_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_srt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file phụ đề", "", "Subtitle Files (*.srt);;All Files (*)")
        if file_path:
            self.srt_file.setText(file_path)

    def run_tts(self):
        # Đây là nơi gọi hàm generate_all_wavs_under_folder gốc
        self.status_label.setText("Đang tạo...")
        
        # Nếu có file lẻ được chọn, sao chép vào thư mục làm việc
        s_file = self.srt_file.text()
        v_folder = self.video_folder.text()
        
        if s_file and os.path.exists(s_file):
            if not os.path.exists(v_folder):
                os.makedirs(v_folder, exist_ok=True)
            shutil.copy(s_file, os.path.join(v_folder, os.path.basename(s_file)))

        try:
            status, synthesized_path, original_path = generate_all_wavs_under_folder(
                v_folder,
                self.tts_method.currentText(),
                self.target_language.currentText(),
                self.edge_tts_voice.currentText()
            )
            self.status_label.setText(status)
            if synthesized_path and os.path.exists(synthesized_path):
                self.synthesized_play_button.setEnabled(True)
            if original_path and os.path.exists(original_path):
                self.original_play_button.setEnabled(True)
        except Exception as e:
            self.status_label.setText(f"Tạo thất bại: {str(e)}")
