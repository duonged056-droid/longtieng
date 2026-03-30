import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QMessageBox, QScrollArea, QFileDialog)

from ui_components import CustomSlider, RadioButtonGroup, VideoPlayer

# 尝试导入实际的功能模块
try:
    from tools.step000_video_downloader import download_from_url
except ImportError:
    pass


class DownloadTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # URL Video
        self.video_url = QLineEdit()
        self.video_url.setPlaceholderText("Vui lòng nhập URL video, danh sách phát hoặc kênh từ Youtube hoặc Bilibili")
        self.video_url.setText("https://www.bilibili.com/video/BV1kr421M7vz/")
        self.layout.addWidget(QLabel("URL Video"))
        self.layout.addWidget(self.video_url)

        # Thư mục đầu ra video
        self.video_folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_download_folder)
        self.video_folder_layout.addWidget(self.video_folder)
        self.video_folder_layout.addWidget(self.btn_select_folder)
        
        self.layout.addWidget(QLabel("Thư mục đầu ra video"))
        self.layout.addLayout(self.video_folder_layout)

    def select_download_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

        # Độ phân giải
        self.resolution = RadioButtonGroup(
            ['4320p', '2160p', '1440p', '1080p', '720p', '480p', '360p', '240p', '144p'],
            "Độ phân giải",
            '1080p'
        )
        self.layout.addWidget(self.resolution)

        # Số lượng video tải xuống
        self.video_count = CustomSlider(1, 100, 1, "Số lượng video tải xuống", 5)
        self.layout.addWidget(self.video_count)

        # Nút thực hiện
        self.run_button = QPushButton("Bắt đầu tải")
        self.run_button.clicked.connect(self.run_download)
        self.layout.addWidget(self.run_button)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.layout.addWidget(QLabel("Trạng thái tải xuống:"))
        self.layout.addWidget(self.status_label)

        # Trình phát video
        self.video_player = VideoPlayer("Video mẫu")
        self.layout.addWidget(self.video_player)

        # Thông tin tải xuống
        self.download_info = QLabel("Thông tin tải xuống sẽ hiển thị ở đây")
        self.layout.addWidget(QLabel("Thông tin tải xuống:"))
        self.scroll_area_info = QScrollArea() # Add a scroll area for long info
        self.scroll_area_info.setWidget(self.download_info)
        self.scroll_area_info.setWidgetResizable(True)
        self.layout.addWidget(self.scroll_area_info)

        self.setLayout(self.layout)

    def run_download(self):
        # Đây là nơi gọi hàm download_from_url gốc
        # Triển khai tạm thời, trong ứng dụng thực tế cần thay thế bằng lời gọi thực
        self.status_label.setText("Đang tải...")
        QMessageBox.information(self, "Gợi ý tính năng", "Tính năng tải xuống đang được thực hiện...")

        # 实际应用中解除以下注释

        try:
            status, video_path, info = download_from_url(
                self.video_url.text(),
                self.video_folder.text(),
                self.resolution.value(),
                self.video_count.value()
            )
            self.status_label.setText(status)
            if video_path and os.path.exists(video_path):
                self.video_player.set_video(video_path)
            self.download_info.setText(str(info))
        except Exception as e:
            self.status_label.setText(f"Tải thất bại: {str(e)}")
