import os
import sys
import yt_dlp
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QComboBox, QFileDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QProgressBar, QMessageBox
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from time import sleep
import configparser
import requests
from packaging import version
import json

def resource_path(relative_path):
    """ Отримати абсолютний шлях до ресурсу """
    try:
        # PyInstaller створює тимчасову папку і зберігає шлях в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

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
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            self.is_cancelled = False
            self.last_progress = 0
            self.progress_history = []
            self.progress_update.emit(0) 
            
            ydl_opts = {
                'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
                'quiet': True,
            }

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
            
            if self.last_progress < 100:
                self.progress_update.emit(100)
            
            self.download_finished.emit(f"Завантажено: {self.url} у форматі {self.selected_format}")
        except Exception as e:
            error_message = str(e)
            self.progress_update.emit(0)
            self.download_finished.emit(f"Помилка: {error_message}")

    def progress_hook(self, d):
        if self.is_cancelled:
            raise Exception("Завантаження скасовано")
        if d['status'] == 'downloading':
            try:
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                
                if not isinstance(total_bytes, (int, float)) or not isinstance(downloaded_bytes, (int, float)):
                    return
                
                if total_bytes <= 0:
                    return
                
                if downloaded_bytes > total_bytes:
                    downloaded_bytes = total_bytes
                
                progress = int((downloaded_bytes / total_bytes) * 100)
                
                progress = max(0, min(99, progress))
                
                if len(self.progress_history) < 3:
                    if progress > self.last_progress:
                        self.last_progress = progress
                        self.progress_update.emit(progress)
                else:
                    self.progress_history.append(progress)
                    if len(self.progress_history) > 10:
                        self.progress_history.pop(0)
                    
                    sorted_progress = sorted(self.progress_history)
                    filtered_progress = sorted_progress[1:-1] if len(sorted_progress) > 4 else sorted_progress
                    avg_progress = sum(filtered_progress) / len(filtered_progress)
                    
                    if avg_progress > self.last_progress and avg_progress < 99:
                        self.last_progress = avg_progress
                        self.progress_update.emit(int(avg_progress))
                    
            except Exception as e:
                print(f"Помилка оновлення прогресу: {str(e)}")
            
        elif d['status'] == 'finished':
            if self.last_progress < 100:
                self.progress_update.emit(100)

class PreviewThread(QThread):
    preview_ready = pyqtSignal(QPixmap, str)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.cache_dir = os.path.join(os.path.expanduser('~'), '.ytdownloader_cache')
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def run(self):
        try:
            # Перевірка кешу
            cache_file = os.path.join(self.cache_dir, f"{hash(self.url)}.jpg")
            if os.path.exists(cache_file):
                pixmap = QPixmap(cache_file)
                if not pixmap.isNull():
                    self.preview_ready.emit(pixmap, "")
                    return

            ydl_opts = {'quiet': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                thumbnail_url = info_dict.get('thumbnail')
                if thumbnail_url:
                    data = ydl.urlopen(thumbnail_url).read()
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    # Зберігаємо в кеш
                    pixmap.save(cache_file, "JPEG")
                    self.preview_ready.emit(pixmap, info_dict.get('title', ''))
        except Exception as e:
            print(f"Помилка при отриманні прев'ю: {e}")

class YouTubeDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.version = "1.0.4"
        self.load_config()
        self.check_for_updates()
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
        self.select_folder_btn.setIcon(QIcon(resource_path('assets/folder.png')))
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
        self.max_history_items = 100  # Максимальна кількість записів в історії

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
            try:
                # Перевірка валідності URL
                if not url.startswith(('http://', 'https://', 'www.youtube.com', 'youtu.be')):
                    raise ValueError("Невалідний YouTube URL")
                
                if hasattr(self, 'preview_thread') and self.preview_thread.isRunning():
                    self.preview_thread.quit()
                
                self.preview_thread = PreviewThread(url)
                self.preview_thread.preview_ready.connect(self.update_preview)
                self.preview_thread.start()
            except Exception as e:
                QMessageBox.warning(self, "Помилка", f"Невалідний URL: {str(e)}")

    def update_preview(self, pixmap, title):
        self.preview_label.setPixmap(pixmap)
        self.video_title.setText(f"Назва: {title}")
        
        selected_format = self.format_combo.currentText()
        self.video_format.setText(f"Формат: {selected_format}")
        
        url = self.url_input.text().strip()
        self.video_url.setText(f"URL: {url}")

    def setup_download_options(self):
        ydl_opts = {
            'ffmpeg_location': resource_path('ffmpeg.exe'),
            'outtmpl': '%(title)s.%(ext)s'
        }

        if self.selected_format == "MP4 (1080p)":
            ydl_opts['format'] = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best'
            ydl_opts['merge_output_format'] = 'mp4'
        
        elif self.selected_format == "MP4 (4k)":
            ydl_opts['format'] = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][ext=mp4]/best'
            ydl_opts['merge_output_format'] = 'mp4'
        
        elif self.selected_format == "MP3":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        elif self.selected_format == "M4A":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            }]
        
        else:  # За замовчуванням найкраща якість MP4
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            ydl_opts['merge_output_format'] = 'mp4'

        return ydl_opts

    def download_video(self):
        try:
            url = self.url_input.text()
            ydl_opts = self.setup_download_options()
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
        except Exception as e:
            QMessageBox.warning(self, "Помилка", str(e))

    def check_for_updates(self):
        try:
            headers = {'Authorization': f'token {self.github_token}'} if self.github_token else {}
            response = requests.get(
                f'https://api.github.com/repos/{self.github_repo}/releases/latest',
                headers=headers
            )
            
            if response.status_code == 200:
                release_info = response.json()
                latest_version = release_info['tag_name'].replace('v', '')
                
                if version.parse(latest_version) > version.parse(self.version):
                    reply = QMessageBox.question(
                        self,
                        "Доступне оновлення",
                        f"Доступна нова версія {latest_version}. Бажаєте завантажити?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        for asset in release_info['assets']:
                            if asset['name'].endswith('.exe'):
                                self.download_update(asset['browser_download_url'])
                                break
        except Exception as e:
            print(f"Помилка перевірки оновлень: {e}")

    def download_update(self, download_url):
        try:
            progress_dialog = QMessageBox(self)
            progress_dialog.setWindowTitle("Завантаження оновлення")
            progress_dialog.setText("Завантаження оновлення...")
            progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
            progress_dialog.show()

            response = requests.get(download_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            update_file = "update.exe"
            block_size = 1024
            
            with open(update_file, 'wb') as f:
                for data in response.iter_content(block_size):
                    f.write(data)
                    
            progress_dialog.close()
            
            QMessageBox.information(
                self,
                "Оновлення завантажено",
                "Оновлення успішно завантажено. Будь ласка, закрийте програму та запустіть файл update.exe"
            )
            
        except Exception as e:
            QMessageBox.warning(self, "Помилка", f"Помилка завантаження оновлення: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec())
