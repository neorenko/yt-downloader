import os
import sys
import yt_dlp
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QComboBox, QFileDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QProgressBar, QMessageBox
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from time import sleep
import configparser

class DownloadThread(QThread):
    progress_update = pyqtSignal(int)
    download_finished = pyqtSignal(str)

    def __init__(self, url, save_path, selected_format):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.selected_format = selected_format
        self.last_progress = 0
        self.progress_history = []

    def run(self):
        try:
            # Скидання прогресу перед початком
            self.last_progress = 0
            self.progress_history = []
            self.progress_update.emit(0)  # Явне встановлення 0% на початку
            
            ydl_opts = {
                'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
            }

            # Налаштування формату відео
            if self.selected_format == "MP4 (1080p)":
                ydl_opts['format'] = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'
            elif self.selected_format == "MP4 (4k)":
                ydl_opts['format'] = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]/best'
            elif self.selected_format == "MP3":
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
            elif self.selected_format == "M4A":
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'}]
            else:
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            
            # Переконуємося, що прогрес досяг 100%
            if self.last_progress < 100:
                self.progress_update.emit(100)
            
            self.download_finished.emit(f"Завантажено: {self.url} у форматі {self.selected_format}")
        except Exception as e:
            error_message = str(e)
            # Скидання прогресу при помилці
            self.progress_update.emit(0)
            self.download_finished.emit(f"Помилка: {error_message}")

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            try:
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                
                # Перевірка валідності значень
                if not isinstance(total_bytes, (int, float)) or not isinstance(downloaded_bytes, (int, float)):
                    return
                
                if total_bytes <= 0:
                    return
                
                # Захист від некоректних значень
                if downloaded_bytes > total_bytes:
                    downloaded_bytes = total_bytes
                
                progress = int((downloaded_bytes / total_bytes) * 100)
                
                # Обмеження прогресу в межах 0-99%
                progress = max(0, min(99, progress))
                
                # Якщо це перші оновлення прогресу
                if len(self.progress_history) < 3:
                    if progress > self.last_progress:
                        self.last_progress = progress
                        self.progress_update.emit(progress)
                else:
                    # Згладжування прогресу
                    self.progress_history.append(progress)
                    if len(self.progress_history) > 10:
                        self.progress_history.pop(0)
                    
                    # Захист від викидів у значеннях прогресу
                    sorted_progress = sorted(self.progress_history)
                    filtered_progress = sorted_progress[1:-1] if len(sorted_progress) > 4 else sorted_progress
                    avg_progress = sum(filtered_progress) / len(filtered_progress)
                    
                    if avg_progress > self.last_progress and avg_progress < 99:
                        self.last_progress = avg_progress
                        self.progress_update.emit(int(avg_progress))
                    
            except Exception as e:
                # Не дозволяємо помилці зупинити процес завантаження
                print(f"Помилка оновлення прогресу: {str(e)}")
            
        elif d['status'] == 'finished':
            # Переконуємося, що прогрес-бар досягає 100% при завершенні
            if self.last_progress < 100:
                self.progress_update.emit(100)

class PreviewThread(QThread):
    preview_ready = pyqtSignal(QPixmap, str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                thumbnail_url = info_dict.get('thumbnail')
                if thumbnail_url:
                    data = ydl.urlopen(thumbnail_url).read()
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    self.preview_ready.emit(pixmap, info_dict.get('title', ''))
        except Exception as e:
            print(f"Помилка при отриманні прев'ю: {e}")

class YouTubeDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.version = "1.0.1"  # Оновлюємо версію
        self.load_config()
        self.setWindowTitle("YouTube Downloader")
        self.resize(1024, 768)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Вставте URL відео...")
        self.url_input.setFixedWidth(700)
        self.url_input.textChanged.connect(self.show_preview)
        top_layout.addWidget(self.url_input)

        self.format_combo = QComboBox(self)
        self.format_combo.addItems([
            "MP4 (1080p)", "MP4 (4k)", "MP3", "M4A"
        ])
        top_layout.addWidget(self.format_combo)

        self.select_folder_btn = QPushButton("Вибрати папку", self)
        self.select_folder_btn.setIcon(QIcon('./assets/folder.png'))
        self.select_folder_btn.clicked.connect(self.select_folder)
        top_layout.addWidget(self.select_folder_btn)

        main_layout.addLayout(top_layout)

        self.download_btn = QPushButton("Завантажити", self)
        self.download_btn.clicked.connect(self.download_video)
        self.download_btn.setFixedHeight(40)
        self.download_btn.setFixedWidth(200)
        main_layout.addWidget(self.download_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        video_info_layout = QGridLayout()
        video_info_layout.setSpacing(10)

        self.preview_label = QLabel(self)
        self.preview_label.setFixedSize(400, 220)
        self.preview_label.setStyleSheet("border: 1px solid gray;")
        video_info_layout.addWidget(self.preview_label, 0, 0, 4, 1)

        self.video_title = QLabel("Назва: ")
        video_info_layout.addWidget(self.video_title, 0, 1)

        self.video_format = QLabel("Формат: ")
        video_info_layout.addWidget(self.video_format, 1, 1)

        self.video_url = QLabel("URL: ")
        video_info_layout.addWidget(self.video_url, 2, 1)

        self.progress_bar = QProgressBar(self)
        video_info_layout.addWidget(self.progress_bar, 3, 1)

        main_layout.addLayout(video_info_layout)
        video_info_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.history_text = QTextEdit(self)
        self.history_text.setReadOnly(True)
        self.history_text.setPlaceholderText("Історія завантажень...")
        main_layout.addWidget(self.history_text)

        self.setLayout(main_layout)

        self.save_path = ""

    def load_config(self):
        config = configparser.ConfigParser()
        try:
            config.read('config.ini')
            self.github_token = config['GitHub']['token']
            self.github_repo = config['GitHub']['repo']
        except Exception as e:
            print(f"Помилка завантаження конфігурації: {e}")
            self.github_token = ""
            self.github_repo = ""

    def select_folder(self):
        self.save_path = QFileDialog.getExistingDirectory(self, "Виберіть папку для збереження")
        if self.save_path:
            self.select_folder_btn.setText(self.save_path)

    def show_preview(self):
        url = self.url_input.text().strip()
        if url:
            if hasattr(self, 'preview_thread') and self.preview_thread.isRunning():
                self.preview_thread.quit()
            
            self.preview_thread = PreviewThread(url)
            self.preview_thread.preview_ready.connect(self.update_preview)
            self.preview_thread.start()

    def update_preview(self, pixmap, title):
        self.preview_label.setPixmap(pixmap)
        self.video_title.setText(f"Назва: {title}")
        
        selected_format = self.format_combo.currentText()
        self.video_format.setText(f"Формат: {selected_format}")
        
        url = self.url_input.text().strip()
        self.video_url.setText(f"URL: {url}")

    def download_video(self):
        url = self.url_input.text().strip()
        selected_format = self.format_combo.currentText()

        if not url:
            QMessageBox.warning(self, "Помилка", "Будь ласка, введіть URL відео.")
            return

        if not self.save_path:
            QMessageBox.warning(self, "Помилка", "Будь ласка, виберіть папку для збереження.")
            return

        self.download_thread = DownloadThread(url, self.save_path, selected_format)
        self.download_thread.progress_update.connect(self.progress_bar.setValue)
        self.download_thread.download_finished.connect(self.on_download_complete)
        self.download_thread.start()
        self.download_btn.setEnabled(False)

    def on_download_complete(self, message):
        self.history_text.append(message)
        self.download_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Очищення поля введення URL
        self.url_input.clear()
        
        # Очищення прев'ю
        self.preview_label.clear()
        self.video_title.setText("Назва: ")
        self.video_format.setText("Формат: ")
        self.video_url.setText("URL: ")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec())
