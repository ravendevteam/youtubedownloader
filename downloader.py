import sys
import os
import re
import logging
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
    QWidget, QPushButton, QTextEdit, QProgressBar, QLabel,
    QFileDialog, QLineEdit, QScrollArea
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import yt_dlp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DownloadThread(QThread):
    progress_signal = pyqtSignal(int, str)
    completion_signal = pyqtSignal(str, str)

    def __init__(self, url, output_dir):
        super().__init__()
        self.url = url
        self.output_dir = output_dir

    def run(self):
        def progress_hook(d):
            if d['status'] == 'downloading':
                percentage = d.get('_percent_str', '').strip().replace('%', '')
                try:
                    progress = int(float(percentage))
                    self.progress_signal.emit(progress, self.url)
                except (ValueError, TypeError):
                    logging.error(f"Failed to parse progress percentage: {percentage}")
                    self.progress_signal.emit(0, self.url)
            elif d['status'] == 'finished':
                self.completion_signal.emit(self.url, 'Completed')

        os.makedirs(self.output_dir, exist_ok=True)

        ydl_opts = {
            'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
            'format': 'best',
            'progress_hooks': [progress_hook],
            'quiet': True,
        }

        try:
            logging.info(f"Starting download: {self.url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            logging.info(f"Download completed: {self.url}")
        except Exception as e:
            logging.error(f"Error downloading {self.url}: {e}")
            self.progress_signal.emit(0, self.url)
            self.completion_signal.emit(f"Error downloading {self.url}: {str(e)}", 'Failed')


class RavenYTDLApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raven YouTube Downloader")
        self.setGeometry(300, 300, 600, 400)

        self.urls = []
        self.download_count = 0
        self.active_downloads = 0
        self.progress_values = {}

        self.download_directory = os.path.expanduser("~\\Downloads")
        self.initUI()
        self.threads = []

        self.setStyleSheet("""
            QMainWindow {
                background-color: black;
                color: white;
                font-family: 'Segoe UI';
            }
            QTextEdit, QLineEdit {
                background-color: black;
                color: white;
                border: 1px solid #444;
                padding: 5px;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: black;
                color: white;
                border: 1px solid #444;
                padding: 5px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                background-color: #333;
            }
            QScrollArea {
                background-color: black;
            }
            QWidget#progress_widget {
                background-color: black;
                border: 1px solid #444;
            }
            QProgressBar {
                background-color: #444;
                text-align: center;
                border: 1px solid #444;
            }
            QProgressBar::chunk {
                background-color: #28a745;
            }
            QLabel {
                font-family: 'Segoe UI';
                background-color: black;
                color: white;
            }
        """)

    def initUI(self):
        main_layout = QVBoxLayout()

        self.url_text_edit = QTextEdit(self)
        self.url_text_edit.setPlaceholderText("URLs here. One per line")
        main_layout.addWidget(self.url_text_edit)

        directory_layout = QHBoxLayout()
        self.directory_input = QLineEdit(self)
        self.directory_input.setPlaceholderText("Download to")
        self.directory_input.setReadOnly(True)
        self.directory_input.setText(self.download_directory)

        self.directory_input.setFixedHeight(30)
        directory_layout.addWidget(self.directory_input)

        browse_button = QPushButton("Browse", self)
        browse_button.clicked.connect(self.select_directory)
        browse_button.setFixedHeight(30)
        directory_layout.addWidget(browse_button)

        main_layout.addLayout(directory_layout)

        self.download_button = QPushButton("Download", self)
        self.download_button.clicked.connect(self.start_downloads)
        main_layout.addWidget(self.download_button)

        self.total_progress_bar = QProgressBar(self)
        self.total_progress_bar.setFixedHeight(20)
        self.total_progress_bar.setValue(0)
        main_layout.addWidget(self.total_progress_bar)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.progress_widget = QWidget()
        self.progress_widget.setObjectName("progress_widget")
        self.progress_widget.setStyleSheet("border: 1px solid #444;")
        self.scroll_area.setWidget(self.progress_widget)
        self.progress_layout = QVBoxLayout(self.progress_widget)
        self.progress_widget.setLayout(self.progress_layout)
        main_layout.addWidget(self.scroll_area)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory", "")
        if directory:
            self.download_directory = directory
            self.directory_input.setText(directory)

    def is_valid_url(self, url):
        url_pattern = re.compile(
            r'^https://(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/.+$'
        )
        return re.match(url_pattern, url) is not None

    def start_downloads(self):
        self.clear_previous_statuses()
        self.urls = list(set(self.url_text_edit.toPlainText().splitlines()))
        self.download_count = len(self.urls)

        if not self.urls:
            status_label = QLabel("No URLs provided.", self)
            status_label.setStyleSheet("color: orange; padding: 5px;")
            status_label.setFixedHeight(30)
            status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.progress_layout.addWidget(status_label)
            return

        valid_urls = [url for url in self.urls if self.is_valid_url(url)]
        if not valid_urls:
            status_label = QLabel("No valid URLs provided.", self)
            status_label.setStyleSheet("color: orange; padding: 5px;")
            status_label.setFixedHeight(30)
            status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.progress_layout.addWidget(status_label)
            return

        self.download_button.setEnabled(False)

        for url in valid_urls:
            url = url.strip()
            self.progress_values[url] = 0
            status_label = QLabel(f"Pending: {url}", self)
            status_label.setStyleSheet("color: white; padding: 5px;")
            status_label.setFixedHeight(30)
            status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.progress_layout.addWidget(status_label)

            thread = DownloadThread(url, self.download_directory)
            thread.progress_signal.connect(self.update_progress)
            thread.completion_signal.connect(self.download_completed)
            self.threads.append(thread)
            self.active_downloads += 1
            thread.start()

    def clear_previous_statuses(self):
        for label in self.progress_layout.findChildren(QLabel):
            self.progress_layout.removeWidget(label)
            label.deleteLater()
        self.total_progress_bar.setValue(0)
        self.active_downloads = 0
        self.progress_values.clear()
        self.threads = []

    def update_progress(self, progress, url):
        self.progress_values[url] = progress
        total_progress = sum(self.progress_values.values()) / self.download_count
        self.total_progress_bar.setValue(int(total_progress))

    def download_completed(self, url, status):
        self.active_downloads -= 1
        if status == 'Completed':
            self.total_progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #28a745; }")
        else:
            self.total_progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #ff4747; }")
            error_message = f"Download failed: {url}"
            status_label = QLabel(error_message, self)
            status_label.setStyleSheet("color: red; padding: 5px;")
            status_label.setFixedHeight(30)
            status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            self.progress_layout.addWidget(status_label)

        self.progress_values[url] = 100 if status == 'Completed' else 0
        if self.active_downloads == 0:
            self.download_button.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    ravenytdl = RavenYTDLApp()
    ravenytdl.show()
    sys.exit(app.exec_())
