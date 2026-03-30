import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QSlider, QRadioButton, QLineEdit, QPushButton,
                               QFileDialog, QGroupBox)
from PySide6.QtCore import Qt, QUrl
# 正确导入QVideoWidget
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput


class CustomSlider(QWidget):
    """Thanh trượt giá trị nguyên"""

    def __init__(self, minimum, maximum, step, label, value, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        self.label = QLabel(label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(minimum)
        self.slider.setMaximum(maximum)
        self.slider.setSingleStep(step)
        self.slider.setValue(value)

        self.value_label = QLabel(str(value))
        self.slider.valueChanged.connect(self.update_value)

        self.layout.addWidget(self.label)

        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.value_label)

        self.layout.addLayout(slider_layout)
        self.setLayout(self.layout)

    def update_value(self, value):
        self.value_label.setText(str(value))

    def value(self):
        return self.slider.value()

    def setValue(self, value):
        self.slider.setValue(value)
        self.value_label.setText(str(value))


class FloatSlider(QWidget):
    """Thanh trượt giá trị thực"""

    def __init__(self, minimum, maximum, step, label, value, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.step = step

        self.label = QLabel(label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(int(minimum / step))
        self.slider.setMaximum(int(maximum / step))
        self.slider.setSingleStep(1)
        self.slider.setValue(int(value / step))

        self.value_label = QLabel(f"{value:.2f}")
        self.slider.valueChanged.connect(self.update_value)

        self.layout.addWidget(self.label)

        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.value_label)

        self.layout.addLayout(slider_layout)
        self.setLayout(self.layout)

    def update_value(self, value):
        float_value = value * self.step
        self.value_label.setText(f"{float_value:.2f}")

    def value(self):
        return self.slider.value() * self.step

    def setValue(self, value):
        self.slider.setValue(int(value / self.step))
        self.value_label.setText(f"{value:.2f}")


class RadioButtonGroup(QWidget):
    """Nhóm nút chọn một (Radio Buttons)"""

    def __init__(self, options, label, default_value, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.group_box = QGroupBox(label)
        self.button_layout = QVBoxLayout()

        self.buttons = []
        for option in options:
            option_str = str(option) if option is not None else "None"
            radio = QRadioButton(option_str)
            self.buttons.append((option, radio))
            if option == default_value:
                radio.setChecked(True)
            self.button_layout.addWidget(radio)

        self.group_box.setLayout(self.button_layout)
        self.layout.addWidget(self.group_box)
        self.setLayout(self.layout)

    def value(self):
        for option, button in self.buttons:
            if button.isChecked():
                return option
        return None


class AudioSelector(QWidget):
    """Chọn tệp âm thanh"""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        self.label = QLabel(label)
        self.layout.addWidget(self.label)

        self.file_layout = QHBoxLayout()
        self.file_path = QLineEdit()
        self.browse_button = QPushButton("Duyệt...")
        self.browse_button.clicked.connect(self.browse_file)

        self.file_layout.addWidget(self.file_path)
        self.file_layout.addWidget(self.browse_button)

        self.layout.addLayout(self.file_layout)
        self.setLayout(self.layout)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn tệp âm thanh", "", "Tệp âm thanh (*.mp3 *.wav *.ogg)")
        if file_path:
            self.file_path.setText(file_path)

    def value(self):
        return self.file_path.text() if self.file_path.text() else None


class VideoPlayer(QWidget):
    """Trình phát video nâng cao"""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        self.label = QLabel(label)
        self.layout.addWidget(self.label)

        # 创建视频部件
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(200)  # 设置最小高度确保可见

        # 创建媒体播放器并配置音频输出
        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)

        # 使用音频输出对象控制音量
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)  # 设置音频输出
        self.audio_output.setVolume(0.7)  # 设置默认音量为70%

        # 添加音量控制滑块
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setToolTip("音量")
        self.volume_slider.valueChanged.connect(self.set_volume)

        # 连接错误信号
        self.media_player.errorOccurred.connect(self.handle_error)

        # 创建控制部件
        self.controls_layout = QHBoxLayout()
        self.play_button = QPushButton("Phát")
        self.play_button.clicked.connect(self.play_pause)

        # Thêm nút tạm dừng và dừng
        self.stop_button = QPushButton("Dừng")
        self.stop_button.clicked.connect(self.stop_video)

        # Nhãn trạng thái
        self.status_label = QLabel("Sẵn sàng")

        # 组装控制栏
        self.controls_layout.addWidget(self.play_button)
        self.controls_layout.addWidget(self.stop_button)

        # Thêm điều khiển âm lượng
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Âm lượng:"))
        volume_layout.addWidget(self.volume_slider)

        self.controls_layout.addLayout(volume_layout)
        self.controls_layout.addWidget(self.status_label)

        self.layout.addWidget(self.video_widget)
        self.layout.addLayout(self.controls_layout)
        self.setLayout(self.layout)

        self.video_path = None

    def set_volume(self, volume):
        # Chuyển phạm vi âm lượng từ 0-100 thành 0.0-1.0
        self.audio_output.setVolume(volume / 100.0)
        self.status_label.setText(f"Âm lượng: {volume}%")

    def set_video(self, path):
        """Thiết lập nguồn video"""
        if not os.path.exists(path):
            self.status_label.setText(f"Lỗi: Tệp không tồn tại")
            return

        self.video_path = path
        try:
            # Sử dụng QUrl để xây dựng đường dẫn tệp
            url = QUrl.fromLocalFile(os.path.abspath(path))
            self.media_player.setSource(url)
            self.status_label.setText(f"Đã tải: {os.path.basename(path)}")
            self.play_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        except Exception as e:
            self.status_label.setText(f"Lỗi: {str(e)}")

    def play_pause(self):
        """Phát hoặc tạm dừng video"""
        if not self.video_path:
            self.status_label.setText("Lỗi: Chưa tải video")
            return

        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.play_button.setText("Phát")
            self.status_label.setText("Đã tạm dừng")
        else:
            self.media_player.play()
            self.play_button.setText("Tạm dừng")
            self.status_label.setText("Đang phát")

    def stop_video(self):
        """Dừng phát video"""
        self.media_player.stop()
        self.play_button.setText("Phát")
        self.status_label.setText("Đã dừng")

    def handle_error(self, error, error_string):
        """Xử lý lỗi trình phát đa phương tiện"""
        self.status_label.setText(f"Lỗi phát lại: {error_string}")
        print(f"Video player error ({error}): {error_string}")