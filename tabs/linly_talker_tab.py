from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QComboBox, QMessageBox, QFileDialog)

from ui_components import VideoPlayer


class LinlyTalkerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # Thư mục video
        self.video_folder_layout = QHBoxLayout()
        self.video_folder = QLineEdit("videos")
        self.btn_select_folder = QPushButton("📂 Chọn")
        self.btn_select_folder.clicked.connect(self.select_talker_folder)
        self.video_folder_layout.addWidget(self.video_folder)
        self.video_folder_layout.addWidget(self.btn_select_folder)
        
        self.layout.addWidget(QLabel("Thư mục video"))
        self.layout.addLayout(self.video_folder_layout)

    def select_talker_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục video", self.video_folder.text())
        if folder:
            self.video_folder.setText(folder)

        # Phương pháp AI dubbing
        self.talker_method = QComboBox()
        self.talker_method.addItems(['Wav2Lip', 'Wav2Lipv2', 'SadTalker'])
        self.layout.addWidget(QLabel("Phương pháp AI dubbing"))
        self.layout.addWidget(self.talker_method)

        # Thông báo đang thi công
        construction_label = QLabel("Đang thi công, vui lòng chờ... Có thể tham khảo https://github.com/Kedreamix/Linly-Talker")
        construction_label.setOpenExternalLinks(True)
        self.layout.addWidget(construction_label)

        # Hiển thị trạng thái
        self.status_label = QLabel("Tính năng đang phát triển")
        self.layout.addWidget(QLabel("Trạng thái tổng hợp:"))
        self.layout.addWidget(self.status_label)

        # Trình phát video
        self.video_player = VideoPlayer("Video tổng hợp")
        self.layout.addWidget(self.video_player)

        self.setLayout(self.layout)