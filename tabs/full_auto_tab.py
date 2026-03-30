import os
import threading
import datetime
import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QPushButton, QMessageBox, QSplitter,
                               QProgressBar, QTextEdit, QFileDialog)
from PySide6.QtCore import QTimer, Signal, QObject, Qt
import subprocess

from ui_components import VideoPlayer

# 尝试导入实际的功能模块
try:
    from tools.do_everything import do_everything
    from tools.utils import SUPPORT_VOICE
except ImportError:
    # 定义临时的支持语音列表
    SUPPORT_VOICE = ['zh-CN-XiaoxiaoNeural', 'zh-CN-YunxiNeural',
                     'en-US-JennyNeural', 'ja-JP-NanamiNeural']


# 创建一个信号类用于线程通信
class WorkerSignals(QObject):
    finished = Signal(str, str)  # 完成信号：状态, 视频路径
    progress = Signal(int, str)  # 进度信号：百分比, 状态信息
    log = Signal(str)  # 日志信号：日志文本


class FullAutoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 用于存储当前配置
        self.config = self.load_config()

        # 创建主水平布局，左侧放URL输入区域，右侧放处理按钮和视频播放器
        self.main_layout = QHBoxLayout(self)

        # 左侧配置区域 - 只保留URL输入
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)

        # Thêm ô nhập URL video
        self.video_url_label = QLabel("URL Video hoặc Đường dẫn Video:")
        self.video_url = QLineEdit()
        self.video_url.setPlaceholderText("Vui lòng nhập URL video hoặc đường dẫn file .mp4")
        self.video_url.setText("https://www.bilibili.com/video/BV1kr421M7vz/")

        # Nút chọn video địa phương
        self.select_video_button = QPushButton("📂 Chọn Video từ máy")
        self.select_video_button.clicked.connect(self.select_local_video)

        # Thêm ô nhập SRT
        self.srt_path_label = QLabel("Đường dẫn file SRT (Tùy chọn):")
        self.srt_path = QLineEdit()
        self.srt_path.setPlaceholderText("Để trống nếu muốn tự động nhận dạng (ASR)")
        self.select_srt_button = QPushButton("📂 Chọn file SRT")
        self.select_srt_button.clicked.connect(self.select_local_srt)

        # Checkbox bỏ qua dịch
        self.skip_translation_cb = gr.Checkbox(label='Lồng tiếng trực tiếp từ SRT (Không dịch)', value=False)
        # Wait, this is PySide6, not Gradio. I used 'gr.Checkbox' by mistake in my thought.
        from PySide6.QtWidgets import QCheckBox
        self.skip_translation_cb = QCheckBox("Lồng tiếng trực tiếp từ SRT (Không dịch)")

        self.left_layout.addWidget(self.video_url_label)
        self.left_layout.addWidget(self.video_url)
        self.left_layout.addWidget(self.select_video_button)
        
        self.left_layout.addSpacing(10)
        self.left_layout.addWidget(self.srt_path_label)
        self.left_layout.addWidget(self.srt_path)
        self.left_layout.addWidget(self.select_srt_button)
        self.left_layout.addWidget(self.skip_translation_cb)

        # 增加一个配置信息摘要
        self.config_summary = QTextEdit()
        self.config_summary.setReadOnly(True)
        self.config_summary.setMaximumHeight(200)
        self.update_config_summary()

        self.config_summary_label = QLabel("Tóm tắt cấu hình hiện tại:")
        self.left_layout.addWidget(self.config_summary_label)
        self.left_layout.addWidget(self.config_summary)

        # 右侧控制和显示区域
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)

        # 执行按钮区域
        self.button_layout = QHBoxLayout()

        # Nút Xử lý
        self.run_button = QPushButton("Xử lý ngay")
        self.run_button.clicked.connect(self.run_process)
        self.run_button.setMinimumHeight(50)
        self.run_button.setStyleSheet("background-color: #4CAF50; color: white;")

        # Nút Dừng
        self.stop_button = QPushButton("Dừng xử lý")
        self.stop_button.clicked.connect(self.stop_process)
        self.stop_button.setMinimumHeight(50)
        self.stop_button.setEnabled(False)  # Ban đầu vô hiệu hóa

        # Nút Xem trước
        self.preview_button = QPushButton("Xem trước video")
        self.preview_button.clicked.connect(self.preview_video)
        self.preview_button.setMinimumHeight(50)
        self.preview_button.setEnabled(False)  # Ban đầu vô hiệu hóa

        # Nút Mở thư mục
        self.open_folder_button = QPushButton("Mở thư mục chứa")
        self.open_folder_button.clicked.connect(self.open_folder)
        self.open_folder_button.setMinimumHeight(50)
        self.open_folder_button.setEnabled(False)  # Ban đầu vô hiệu hóa

        # 添加按钮到按钮布局
        self.button_layout.addWidget(self.run_button)
        self.button_layout.addWidget(self.stop_button)
        self.button_layout.addWidget(self.open_folder_button)
        self.button_layout.addWidget(self.preview_button)
        self.right_layout.addLayout(self.button_layout)

        # Thanh tiến trình
        self.progress_layout = QVBoxLayout()
        self.progress_label = QLabel("Sẵn sàng")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_layout.addWidget(QLabel("Tiến độ xử lý:"))
        self.progress_layout.addWidget(self.progress_bar)
        self.progress_layout.addWidget(self.progress_label)
        self.right_layout.addLayout(self.progress_layout)

        # Hiển thị trạng thái
        self.status_label = QLabel("Sẵn sàng")
        self.right_layout.addWidget(QLabel("Trạng thái xử lý:"))
        self.right_layout.addWidget(self.status_label)

        # 创建右侧的垂直分割器，上方放视频播放器，下方放日志
        self.right_splitter = QSplitter(Qt.Vertical)

        # Container video
        self.video_container = QWidget()
        self.video_layout = QVBoxLayout(self.video_container)
        self.video_layout.addWidget(QLabel("Xem trước video tổng hợp:"))
        self.video_player = VideoPlayer("Video tổng hợp")
        self.video_layout.addWidget(self.video_player)
        self.video_container.setLayout(self.video_layout)

        # Container nhật ký
        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.addWidget(QLabel("Nhật ký xử lý:"))

        # 日志文本区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)  # 设置为只读
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)  # 自动换行
        self.log_layout.addWidget(self.log_text)

        # Nút điều khiển nhật ký
        self.log_button_layout = QHBoxLayout()
        self.clear_log_button = QPushButton("Xóa nhật ký")
        self.clear_log_button.clicked.connect(self.clear_log)
        self.save_log_button = QPushButton("Lưu nhật ký")
        self.save_log_button.clicked.connect(self.save_log)
        self.log_button_layout.addWidget(self.clear_log_button)
        self.log_button_layout.addWidget(self.save_log_button)
        self.log_layout.addLayout(self.log_button_layout)

        self.log_container.setLayout(self.log_layout)

        # 添加视频和日志区域到右侧分割器
        self.right_splitter.addWidget(self.video_container)
        self.right_splitter.addWidget(self.log_container)

        # 设置初始分割比例 (60% 视频, 40% 日志)
        self.right_splitter.setSizes([600, 400])

        # 将分割器添加到右侧布局
        self.right_layout.addWidget(self.right_splitter)

        # 添加左右两个区域到主布局
        # 使用QSplitter允许用户调整左右两部分的宽度
        self.main_splitter = QSplitter()
        self.main_splitter.addWidget(self.left_widget)
        self.main_splitter.addWidget(self.right_widget)

        # 设置初始分割比例 (30% 左侧, 70% 右侧)
        self.main_splitter.setSizes([300, 700])

        self.main_layout.addWidget(self.main_splitter)
        self.setLayout(self.main_layout)

        # 处理线程
        self.worker_thread = None
        self.is_processing = False
        self.signals = WorkerSignals()
        self.signals.finished.connect(self.process_finished)
        self.signals.progress.connect(self.update_progress)
        self.signals.log.connect(self.append_log)

        # 存储生成的视频路径
        self.generated_video_path = None

        # 实际进度更新
        self.current_progress = 0
        self.progress_steps = [
            "下载视频...", "人声分离...", "AI智能语音识别...",
            "字幕翻译...", "AI语音合成...", "视频合成..."
        ]
        self.current_step = 0

        # Khởi tạo nhật ký
        self.append_log("Hệ thống khởi tạo hoàn tất, sẵn sàng")

    def update_config_summary(self):
        """更新配置摘要显示"""
        config = self.load_config()
        if config:
            summary_text = "● 视频输出目录: {}\n".format(config.get("video_folder", "videos"))
            summary_text += "● 分辨率: {}\n".format(config.get("resolution", "1080p"))
            summary_text += "● 人声分离: {}, 设备: {}\n".format(
                config.get("model", "htdemucs_ft"),
                config.get("device", "auto")
            )
            summary_text += "● 语音识别: {}, 模型: {}\n".format(
                config.get("asr_model", "WhisperX"),
                config.get("whisperx_size", "large")
            )
            summary_text += "● 翻译方式: {}\n".format(config.get("translation_method", "LLM"))
            summary_text += "● TTS方式: {}, 语言: {}\n".format(
                config.get("tts_method", "EdgeTTS"),
                config.get("target_language_tts", "中文")
            )
            summary_text += "● Thêm phụ đề: {}, Tốc độ: {}\n".format(
                "Có" if config.get("add_subtitles", True) else "Không",
                config.get("speed_factor", 1.00)
            )
            self.config_summary.setText(summary_text)
        else:
            self.config_summary.setText("Không tìm thấy cấu hình, sử dụng mặc định")

    def select_local_video(self):
        """选择本地视频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file Video", "", "Video Files (*.mp4 *.avi *.mkv *.mov *.flv)"
        )
        if file_path:
            self.video_url.setText(file_path)
            self.append_log(f"Đã chọn Video: {file_path}")

    def select_local_srt(self):
        """选择本地SRT文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file SRT", "", "Subtitle Files (*.srt)"
        )
        if file_path:
            self.srt_path.setText(file_path)
            self.append_log(f"Đã chọn SRT: {file_path}")

    def load_config(self):
        """从配置文件加载配置"""
        try:
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(config_dir, "config.json")

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return config
            else:
                return None
        except Exception as e:
            self.append_log(f"加载配置失败: {str(e)}")
            return None

    def update_config(self, new_config):
        """更新当前配置"""
        self.config = new_config
        self.update_config_summary()

    def update_progress(self, progress, status):
        """更新处理进度"""
        # 确保进度条与状态信息一致
        self.current_progress = progress
        self.progress_bar.setValue(progress)
        self.progress_label.setText(status)
        self.append_log(f"进度更新: {progress}% - {status}")

    def process_thread(self):
        """异步处理线程"""
        config = self.load_config() or {}
        try:
            self.signals.log.emit("开始处理...")
            self.signals.progress.emit(0, "初始化处理...")
            url = self.video_url.text()
            srt_path = self.srt_path.text() if self.srt_path.text() else None
            skip_translation = self.skip_translation_cb.isChecked()

            # 记录重要参数
            self.signals.log.emit(f"视频文件夹: {config.get('video_folder', 'videos')}")
            self.signals.log.emit(f"视频URL/Path: {url}")
            if srt_path:
                 self.signals.log.emit(f"Sử dụng file SRT: {srt_path}")
            self.signals.log.emit(f"Bỏ qua dịch thuật: {'Có' if skip_translation else 'Không'}")
            
            # 实际的处理调用
            result, video_path = do_everything(
                config.get('video_folder', 'videos'),  # 使用配置中的参数或默认值
                url,
                config.get('video_count', 5),
                config.get('resolution', '1080p'),
                config.get('model', 'htdemucs_ft'),
                config.get('device', 'auto'),
                config.get('shifts', 1),
                config.get('asr_model', 'WhisperX'),
                config.get('whisperx_size', 'large'),
                config.get('batch_size', 4),
                config.get('separate_speakers', True),
                config.get('min_speakers', None),
                config.get('max_speakers', None),
                config.get('translation_method', 'LLM'),
                config.get('target_language_translation', '简体中文'),
                config.get('tts_method', 'EdgeTTS'),
                config.get('target_language_tts', '中文'),
                config.get('edge_tts_voice', 'zh-CN-XiaoxiaoNeural'),
                config.get('add_subtitles', True),
                config.get('speed_factor', 1.00),
                config.get('frame_rate', 30),
                config.get('background_music', None),
                config.get('bg_music_volume', 0.5),
                config.get('video_volume', 1.0),
                config.get('output_resolution', '1080p'),
                config.get('max_workers', 1),
                config.get('max_retries', 3),
                progress_callback=None, # Signal handles it
                srt_path=srt_path,
                skip_asr=(srt_path is not None),
                skip_translation=skip_translation
            )

            # 完成处理，设置100%进度
            self.signals.progress.emit(100, "处理完成!")
            self.signals.log.emit(f"处理完成: {result}")
            if video_path:
                self.signals.log.emit(f"生成视频路径: {video_path}")

            # 处理完成，发送信号
            self.signals.finished.emit(result, video_path if video_path else "")

        except Exception as e:
            # 捕获并记录完整的堆栈跟踪信息
            import traceback
            stack_trace = traceback.format_exc()
            error_msg = f"处理失败: {str(e)}\n\n堆栈跟踪:\n{stack_trace}"
            self.signals.log.emit(error_msg)
            self.signals.progress.emit(0, "处理失败")
            self.signals.finished.emit(f"处理失败: {str(e)}", "")

    def run_process(self):
        """开始处理"""
        if self.is_processing:
            return

        self.is_processing = True
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.preview_button.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.status_label.setText("正在处理...")

        # 重置进度
        self.current_progress = 0
        self.current_step = 0
        self.progress_bar.setValue(0)
        self.progress_label.setText("准备处理...")

        # 记录开始处理
        self.append_log("-" * 50)
        self.append_log(f"开始处理 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.append_log(f"视频URL: {self.video_url.text()}")

        # 创建并启动处理线程
        self.worker_thread = threading.Thread(target=self.process_thread)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop_process(self):
        """停止处理"""
        if not self.is_processing:
            return

        # 在实际应用中，添加停止处理的逻辑
        # TODO: 添加中断处理线程的代码

        self.is_processing = False
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("处理已停止")
        self.append_log("用户手动停止处理")

    def process_finished(self, result, video_path):
        """处理完成回调"""
        self.is_processing = False
        self.run_button.setEnabled(True)  # 重新启用一键处理按钮
        self.stop_button.setEnabled(False)  # 禁用停止处理按钮
        self.status_label.setText(result)

        # 存储生成的视频路径
        self.generated_video_path = video_path

        # 记录处理完成
        self.append_log(f"处理完成 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.append_log(f"结果: {result}")

        # 如果有视频路径，启用预览按钮和打开文件夹按钮，并加载视频
        if video_path and os.path.exists(video_path):
            self.preview_button.setEnabled(True)
            self.open_folder_button.setEnabled(True)
            self.video_player.set_video(video_path)
            self.append_log(f"生成视频路径: {video_path}")
        else:
            self.append_log("未生成视频或视频路径无效")

    def preview_video(self):
        """预览生成的视频"""
        if self.generated_video_path and os.path.exists(self.generated_video_path):
            # 如果已经加载了视频，直接播放
            # 否则重新加载视频
            if not hasattr(self.video_player,
                           'video_path') or self.video_player.video_path != self.generated_video_path:
                self.video_player.set_video(self.generated_video_path)

            # 播放视频
            self.video_player.play_pause()
            self.append_log(f"预览视频: {self.generated_video_path}")

    def open_folder(self):
        """打开文件所在目录"""
        if self.generated_video_path and os.path.exists(self.generated_video_path):
            folder_path = os.path.dirname(self.generated_video_path)
            self.append_log(f"打开文件夹: {folder_path}")

            # 根据操作系统打开文件夹
            if os.name == 'nt':  # Windows
                os.startfile(folder_path)
            elif os.name == 'posix':  # macOS, Linux
                if 'darwin' in os.sys.platform:  # macOS
                    subprocess.run(['open', folder_path])
                else:  # Linux
                    subprocess.run(['xdg-open', folder_path])

    def append_log(self, message):
        """添加日志信息"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        self.log_text.append(log_message)
        # 滚动到最底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self.append_log("日志已清空")

    def save_log(self):
        """保存日志"""
        try:
            # 创建日志文件夹
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            # 创建日志文件名
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = os.path.join(log_dir, f"process_log_{timestamp}.txt")

            # 保存日志内容
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(self.log_text.toPlainText())

            self.append_log(f"日志已保存到: {log_file}")
        except Exception as e:
            self.append_log(f"保存日志失败: {str(e)}")