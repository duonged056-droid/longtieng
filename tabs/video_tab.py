from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QCheckBox, QPushButton, QMessageBox, QFileDialog)

from ui_components import (FloatSlider, CustomSlider, RadioButtonGroup,
                           AudioSelector, VideoPlayer)
import shutil

# 尝试导入实际的功能模块
try:
    from tools.step050_synthesize_video import synthesize_all_video_under_folder
except ImportError:
    pass


class SynthesizeVideoTab(QWidget):
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
        self.btn_select_folder.clicked.connect(self.select_syn_folder)
        self.video_folder_layout.addWidget(self.video_folder)
        self.video_folder_layout.addWidget(self.btn_select_folder)
        
        self.scroll_layout.addWidget(QLabel("Thư mục video"))
        self.scroll_layout.addLayout(self.video_folder_layout)

        # File video lẻ và SRT lẻ
        self.file_selection_layout = QHBoxLayout()
        
        # Cột video lẻ
        self.video_file_vbox = QVBoxLayout()
        self.video_file = QLineEdit()
        self.btn_select_video = QPushButton("🎬 Chọn video lẻ")
        self.btn_select_video.clicked.connect(self.select_syn_video)
        self.video_file_vbox.addWidget(QLabel("Chọn video lẻ"))
        self.video_file_vbox.addWidget(self.video_file)
        self.video_file_vbox.addWidget(self.btn_select_video)
        
        # Cột SRT lẻ
        self.srt_file_vbox = QVBoxLayout()
        self.srt_file = QLineEdit()
        self.btn_select_srt = QPushButton("📜 Chọn file SRT")
        self.btn_select_srt.clicked.connect(self.select_syn_srt)
        self.srt_file_vbox.addWidget(QLabel("Chọn file SRT"))
        self.srt_file_vbox.addWidget(self.srt_file)
        self.srt_file_vbox.addWidget(self.btn_select_srt)
        
        self.file_selection_layout.addLayout(self.video_file_vbox)
        self.file_selection_layout.addLayout(self.srt_file_vbox)
        
        self.scroll_layout.addLayout(self.file_selection_layout)

    def select_syn_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_syn_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file video", "", "Video Files (*.mp4 *.avi *.mkv);;All Files (*)")
        if file_path:
            self.video_file.setText(file_path)

    def select_syn_srt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file phụ đề", "", "Subtitle Files (*.srt);;All Files (*)")
        if file_path:
            self.srt_file.setText(file_path)

        # Thêm phụ đề
        self.add_subtitles = QCheckBox("Thêm phụ đề")
        self.add_subtitles.setChecked(True)
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

        # Độ phân giải
        self.resolution = RadioButtonGroup(
            ['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'],
            "Độ phân giải",
            '1080p'
        )
        self.scroll_layout.addWidget(self.resolution)

        # Nút thực hiện
        self.run_button = QPushButton("Bắt đầu tổng hợp video")
        self.run_button.clicked.connect(self.run_synthesis)
        self.scroll_layout.addWidget(self.run_button)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.scroll_layout.addWidget(QLabel("Trạng thái tổng hợp:"))
        self.scroll_layout.addWidget(self.status_label)

        # Trình phát video
        self.video_player = VideoPlayer("Video tổng hợp")
        self.scroll_layout.addWidget(self.video_player)

        # 设置滚动区域
        self.scroll_area.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll_area)
        self.setLayout(self.layout)

    def select_syn_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

    def select_syn_video(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file video", "", "Video Files (*.mp4 *.avi *.mkv);;All Files (*)")
        if file_path:
            self.video_file.setText(file_path)

    def select_syn_srt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file phụ đề", "", "Subtitle Files (*.srt);;All Files (*)")
        if file_path:
            self.srt_file.setText(file_path)

    def run_synthesis(self):
        # Đây là nơi gọi hàm synthesize_all_video_under_folder gốc
        self.status_label.setText("Đang tổng hợp...")
        
        # Nếu có file video lẻ hoặc SRT lẻ được chọn, sao chép vào thư mục làm việc
        v_file = self.video_file.text()
        s_file = self.srt_file.text()
        v_folder = self.video_folder.text()
        
        if not os.path.exists(v_folder):
            os.makedirs(v_folder, exist_ok=True)
            
        if v_file and os.path.exists(v_file):
            shutil.copy(v_file, os.path.join(v_folder, os.path.basename(v_file)))
        if s_file and os.path.exists(s_file):
            shutil.copy(s_file, os.path.join(v_folder, os.path.basename(s_file)))

        try:
            status, video_path = synthesize_all_video_under_folder(
                v_folder,
                self.add_subtitles.isChecked(),
                self.speed_factor.value(),
                self.frame_rate.value(),
                self.background_music.value(),
                self.bg_music_volume.value(),
                self.video_volume.value(),
                self.resolution.value()
            )
            self.status_label.setText(status)
            if video_path and os.path.exists(video_path):
                self.video_player.set_video(video_path)
        except Exception as e:
            self.status_label.setText(f"Tổng hợp thất bại: {str(e)}")
