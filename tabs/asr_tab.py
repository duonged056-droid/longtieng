from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QComboBox, QCheckBox, QPushButton, QMessageBox, QFileDialog)

from ui_components import CustomSlider, RadioButtonGroup

# 尝试导入实际的功能模块
try:
    from tools.step020_asr import transcribe_all_audio_under_folder
except ImportError:
    pass


class ASRTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # 创建一个滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)

        # Thư mục video
        self.video_folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_asr_folder)
        self.video_folder_layout.addWidget(self.video_folder)
        self.video_folder_layout.addWidget(self.btn_select_folder)
        
        self.scroll_layout.addWidget(QLabel("Thư mục video"))
        self.scroll_layout.addLayout(self.video_folder_layout)

        # File video lẻ
        self.video_file_layout = QHBoxLayout()
        self.video_file = QLineEdit()
        self.btn_select_file = QPushButton("🎬 Chọn file lẻ")
        self.btn_select_file.clicked.connect(self.select_asr_file)
        self.video_file_layout.addWidget(self.video_file)
        self.video_file_layout.addWidget(self.btn_select_file)
        
        self.scroll_layout.addWidget(QLabel("Hoặc chọn file Video cục bộ"))
        self.scroll_layout.addLayout(self.video_file_layout)

    def select_asr_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_asr_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file video", "", "Video Files (*.mp4 *.avi *.mkv);;All Files (*)")
        if file_path:
            self.video_file.setText(file_path)

        # Chọn mô hình ASR
        self.asr_model = QComboBox()
        self.asr_model.addItems(['WhisperX', 'FunASR'])
        self.scroll_layout.addWidget(QLabel("Chọn mô hình ASR"))
        self.scroll_layout.addWidget(self.asr_model)

        # Kích thước mô hình WhisperX
        self.whisperx_size = RadioButtonGroup(['large', 'medium', 'small', 'base', 'tiny'], "Kích thước mô hình WhisperX", 'large')
        self.scroll_layout.addWidget(self.whisperx_size)

        # Thiết bị tính toán
        self.device = RadioButtonGroup(['auto', 'cuda', 'cpu'], "Thiết bị tính toán", 'auto')
        self.scroll_layout.addWidget(self.device)

        # Batch Size
        self.batch_size = CustomSlider(1, 128, 1, "Batch Size (Kích thước lô)", 4)
        self.scroll_layout.addWidget(self.batch_size)

        # Tách nhiều người nói
        self.separate_speakers = QCheckBox("Tách nhiều người nói")
        self.separate_speakers.setChecked(True)
        self.scroll_layout.addWidget(self.separate_speakers)

        # Số người nói tối thiểu
        self.min_speakers = RadioButtonGroup([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], "Số người nói tối thiểu", None)
        self.scroll_layout.addWidget(self.min_speakers)

        # Số người nói tối đa
        self.max_speakers = RadioButtonGroup([None, 1, 2, 3, 4, 5, 6, 7, 8, 9], "Số người nói tối đa", None)
        self.scroll_layout.addWidget(self.max_speakers)

        # Nút thực hiện
        self.run_button = QPushButton("Bắt đầu nhận dạng")
        self.run_button.clicked.connect(self.run_asr)
        self.scroll_layout.addWidget(self.run_button)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.scroll_layout.addWidget(QLabel("Trạng thái nhận dạng giọng nói:"))
        self.scroll_layout.addWidget(self.status_label)

        # Chi tiết kết quả nhận dạng
        self.result_detail = QLabel("Kết quả nhận dạng sẽ hiển thị ở đây")
        self.scroll_layout.addWidget(QLabel("Chi tiết kết quả nhận dạng:"))
        self.scroll_layout.addWidget(self.result_detail)

        # 设置滚动区域
        self.scroll_area.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll_area)
        self.setLayout(self.layout)

    def run_asr(self):
        # Đây là nơi gọi hàm transcribe_all_audio_under_folder gốc
        self.status_label.setText("Đang nhận dạng...")
        
        # Nếu có file lẻ được chọn, sao chép vào thư mục làm việc
        v_file = self.video_file.text()
        v_folder = self.video_folder.text()
        
        if v_file and os.path.exists(v_file):
            if not os.path.exists(v_folder):
                os.makedirs(v_folder, exist_ok=True)
            shutil.copy(v_file, os.path.join(v_folder, os.path.basename(v_file)))

        try:
            status, result_json = transcribe_all_audio_under_folder(
                v_folder,
                self.asr_model.currentText(),
                self.whisperx_size.value(),
                self.device.value(),
                self.batch_size.value(),
                self.separate_speakers.isChecked(),
                self.min_speakers.value(),
                self.max_speakers.value()
            )
            self.status_label.setText(status)
            self.result_detail.setText(str(result_json))
        except Exception as e:
            self.status_label.setText(f"Nhận dạng thất bại: {str(e)}")
