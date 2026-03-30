from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QMessageBox, QCheckBox, QGroupBox, QFileDialog)

from ui_components import CustomSlider, RadioButtonGroup
import shutil

# 尝试导入实际的功能模块
try:
    from tools.step010_demucs_vr import separate_all_audio_under_folder
except ImportError:
    pass


class DemucsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # Thư mục video
        self.video_folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_video_folder)
        self.video_folder_layout.addWidget(self.video_folder)
        self.video_folder_layout.addWidget(self.btn_select_folder)
        
        self.layout.addWidget(QLabel("Thư mục video"))
        self.layout.addLayout(self.video_folder_layout)

        # File video lẻ
        self.video_file_layout = QHBoxLayout()
        self.video_file = QLineEdit()
        self.btn_select_file = QPushButton("🎬 Chọn file lẻ")
        self.btn_select_file.clicked.connect(self.select_video_file)
        self.video_file_layout.addWidget(self.video_file)
        self.video_file_layout.addWidget(self.btn_select_file)
        
        self.layout.addWidget(QLabel("Hoặc chọn file Video cục bộ"))
        self.layout.addLayout(self.video_file_layout)

    def select_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file video", "", "Video Files (*.mp4 *.avi *.mkv);;All Files (*)")
        if file_path:
            self.video_file.setText(file_path)

        # Mô hình
        self.model = RadioButtonGroup(
            ['htdemucs', 'htdemucs_ft', 'htdemucs_6s', 'hdemucs_mmi', 'mdx', 'mdx_extra', 'mdx_q', 'mdx_extra_q',
             'SIG'],
            "Mô hình",
            'htdemucs_ft'
        )
        self.layout.addWidget(self.model)

        # Thiết bị tính toán
        self.device = RadioButtonGroup(['auto', 'cuda', 'cpu'], "Thiết bị tính toán", 'auto')
        self.layout.addWidget(self.device)

        # Hiển thị thanh tiến trình
        self.show_progress = QCheckBox("Hiển thị thanh tiến trình")
        self.show_progress.setChecked(True)
        self.layout.addWidget(self.show_progress)

        # Số lần dịch chuyển
        self.shifts = CustomSlider(0, 10, 1, "Số lần dịch chuyển (Shifts)", 1)
        self.layout.addWidget(self.shifts)

        # Nút thực hiện
        self.run_button = QPushButton("Bắt đầu tách")
        self.run_button.clicked.connect(self.run_separation)
        self.layout.addWidget(self.run_button)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.layout.addWidget(QLabel("Trạng thái kết quả tách:"))
        self.layout.addWidget(self.status_label)

        # Điều khiển phát âm thanh
        vocals_group = QGroupBox("Âm thanh giọng nói")
        vocals_layout = QVBoxLayout()
        self.vocals_play_button = QPushButton("Phát giọng nói")
        vocals_layout.addWidget(self.vocals_play_button)
        vocals_group.setLayout(vocals_layout)

        accompaniment_group = QGroupBox("Âm thanh nhạc nền (Accompaniment)")
        accompaniment_layout = QVBoxLayout()
        self.accompaniment_play_button = QPushButton("Phát nhạc nền")
        accompaniment_layout.addWidget(self.accompaniment_play_button)
        accompaniment_group.setLayout(accompaniment_layout)

        audio_layout = QHBoxLayout()
        audio_layout.addWidget(vocals_group)
        audio_layout.addWidget(accompaniment_group)

        self.layout.addLayout(audio_layout)
        self.setLayout(self.layout)

    def run_separation(self):
        # Đây là nơi gọi hàm separate_all_audio_under_folder gốc
        self.status_label.setText("Đang tách...")
        
        # Nếu có file lẻ được chọn, sao chép vào thư mục làm việc
        v_file = self.video_file.text()
        v_folder = self.video_folder.text()
        
        if v_file and os.path.exists(v_file):
            if not os.path.exists(v_folder):
                os.makedirs(v_folder, exist_ok=True)
            shutil.copy(v_file, os.path.join(v_folder, os.path.basename(v_file)))

        try:
            status, vocals_path, accompaniment_path = separate_all_audio_under_folder(
                v_folder,
                self.model.value(),
                self.device.value(),
                self.show_progress.isChecked(),
                self.shifts.value()
            )
            self.status_label.setText(status)
            if vocals_path and os.path.exists(vocals_path):
                self.vocals_play_button.setEnabled(True)
            if accompaniment_path and os.path.exists(accompaniment_path):
                self.accompaniment_play_button.setEnabled(True)
        except Exception as e:
            self.status_label.setText(f"Tách thất bại: {str(e)}")
