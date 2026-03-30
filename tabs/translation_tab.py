from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QComboBox, QPushButton, QMessageBox, QScrollArea, QFileDialog)

# 尝试导入实际的功能模块
try:
    from tools.step030_translation import translate_all_transcript_under_folder
except ImportError:
    pass


class TranslationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # Thư mục video
        self.video_folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_trans_folder)
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

    def select_trans_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_srt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file phụ đề", "", "Subtitle Files (*.srt);;All Files (*)")
        if file_path:
            self.srt_file.setText(file_path)

        # Phương thức dịch
        self.translation_method = QComboBox()
        self.translation_method.addItems(['OpenAI', 'LLM', 'Google Translate', 'Bing Translate', 'Ernie'])
        self.translation_method.setCurrentText('LLM')
        self.layout.addWidget(QLabel("Phương thức dịch"))
        self.layout.addWidget(self.translation_method)

        # Ngôn ngữ mục tiêu
        self.target_language = QComboBox()
        self.target_language.addItems(['Tiếng Việt', 'Tiếng Trung (Giản thể)', 'Tiếng Trung (Phồn thể)', 'English', 'Tiếng Quảng Đông', 'Tiếng Nhật', 'Tiếng Hàn'])
        self.target_language.setCurrentText('Tiếng Việt')
        self.layout.addWidget(QLabel("Ngôn ngữ mục tiêu"))
        self.layout.addWidget(self.target_language)

        # Nút thực hiện
        self.run_button = QPushButton("Bắt đầu dịch")
        self.run_button.clicked.connect(self.run_translation)
        self.layout.addWidget(self.run_button)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.layout.addWidget(QLabel("Trạng thái dịch:"))
        self.layout.addWidget(self.status_label)

        # Tóm tắt kết quả
        self.summary_label = QLabel("Tóm tắt kết quả sẽ hiển thị ở đây")
        self.layout.addWidget(QLabel("Tóm tắt kết quả:"))
        self.layout.addWidget(self.summary_label)

        # Kết quả dịch
        self.translation_result = QLabel("Kết quả dịch sẽ hiển thị ở đây")
        self.layout.addWidget(QLabel("Kết quả dịch:"))

        # 使用滚动区域显示详细结果
        result_scroll = QScrollArea()
        result_scroll.setWidgetResizable(True)
        result_scroll.setWidget(self.translation_result)
        self.layout.addWidget(result_scroll)

        self.setLayout(self.layout)

    def select_trans_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_srt_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file phụ đề", "", "Subtitle Files (*.srt);;All Files (*)")
        if file_path:
            self.srt_file.setText(file_path)

    def run_translation(self):
        # Đây là nơi gọi hàm translate_all_transcript_under_folder gốc
        self.status_label.setText("Đang dịch...")
        
        # Nếu có file lẻ được chọn, sao chép vào thư mục làm việc
        s_file = self.srt_file.text()
        v_folder = self.video_folder.text()
        
        if s_file and os.path.exists(s_file):
            if not os.path.exists(v_folder):
                os.makedirs(v_folder, exist_ok=True)
            shutil.copy(s_file, os.path.join(v_folder, os.path.basename(s_file)))

        try:
            status, summary, translation = translate_all_transcript_under_folder(
                v_folder,
                self.translation_method.currentText(),
                self.target_language.currentText()
            )
            self.status_label.setText(status)
            self.summary_label.setText(str(summary))
            self.translation_result.setText(str(translation))
        except Exception as e:
            self.status_label.setText(f"Dịch thất bại: {str(e)}")
