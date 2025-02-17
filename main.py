import os
import sys
import yt_dlp
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QComboBox, QFileDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QProgressBar, QMessageBox
from PyQt6.QtGui import QPixmap, QIcon, QImage
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from time import sleep
import configparser
import requests
from packaging import version
import json
from datetime import datetime

def resource_path(relative_path):
    """ Отримати абсолютний шлях до ресурсу """
    try:
        # PyInstaller створює тимчасову папку і зберігає шлях в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    path = os.path.join(base_path, relative_path)
    # Перевіряємо чи існує файл
    if not os.path.exists(path):
        print(f"Файл не знайдено: {path}")
    return path

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
                ydl_opts.update({
                    'format': 'bestvideo[height<=1080][vcodec!*=av1][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][vcodec!*=av1][vcodec!*=vp9][ext=mp4]/best',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4'
                    }],
                    'merge_output_format': 'mp4',
                    'audio_quality': 0,
                    'prefer_ffmpeg': True,
                    'format_sort': ['res:1080', 'vcodec:h264', 'acodec:m4a']
                })
            elif self.selected_format == "MP4 (4k)":
                ydl_opts.update({
                    'format': 'bestvideo[height<=2160][vcodec!*=av1][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][vcodec!*=av1][vcodec!*=vp9][ext=mp4]/best',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4'
                    }],
                    'merge_output_format': 'mp4',
                    'audio_quality': 0,
                    'prefer_ffmpeg': True,
                    'format_sort': ['res:2160', 'vcodec:h264', 'acodec:m4a']
                })
            elif self.selected_format == "MP3":
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '320'
                    }],
                    'audio_quality': 0,
                    'prefer_ffmpeg': True
                })
            elif self.selected_format == "M4A":
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'm4a',
                        'preferredquality': '0'
                    }],
                    'audio_quality': 0,
                    'prefer_ffmpeg': True
                })
            else:
                ydl_opts.update({
                    'format': 'bestvideo[vcodec!*=av1][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]/best[vcodec!*=av1][vcodec!*=vp9][ext=mp4]/best',
                    'postprocessors': [{
                        'key': 'FFmpegVideoConvertor',
                        'preferedformat': 'mp4'
                    }],
                    'merge_output_format': 'mp4',
                    'audio_quality': 0,
                    'prefer_ffmpeg': True,
                    'format_sort': ['vcodec:h264', 'acodec:m4a']
                })

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
    error = pyqtSignal(str)

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

            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                
                if not info:
                    self.error.emit("Не вдалося отримати інформацію про відео")
                    return
                    
                thumbnail_url = info.get('thumbnail')
                if not thumbnail_url:
                    self.error.emit("Не знайдено превью для відео")
                    return
                    
                response = requests.get(thumbnail_url)
                if response.status_code != 200:
                    self.error.emit("Помилка завантаження превью")
                    return
                    
                image = QImage()
                image.loadFromData(response.content)
                
                if image.isNull():
                    self.error.emit("Помилка обробки зображення")
                    return
                    
                pixmap = QPixmap.fromImage(image)
                title = info.get('title', 'Без назви')
                
                # Зберігаємо в кеш
                pixmap.save(cache_file, "JPEG")
                self.preview_ready.emit(pixmap, title)
        except Exception as e:
            self.error.emit(str(e))

class YouTubeDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.version = "1.0.8"
        self.init_ui()
        self.load_config()
        self.check_for_updates()

    def init_ui(self):
        """Ініціалізація інтерфейсу"""
        try:
            self.setWindowTitle("YouTube Downloader")
            self.resize(1024, 768)
            self.setup_layouts()
            self.setup_widgets()
            self.save_path = ""
            self.max_history_items = 100
            self.downloading = False  # Флаг для відстеження стану завантаження
        except Exception as e:
            QMessageBox.critical(self, "Помилка", f"Помилка ініціалізації: {str(e)}")

    def setup_layouts(self):
        """Налаштування layouts"""
        try:
            self.main_layout = QVBoxLayout()
            self.main_layout.setSpacing(10)
            self.main_layout.setContentsMargins(10, 10, 10, 10)
            self.setLayout(self.main_layout)

            self.top_layout = QHBoxLayout()
            self.top_layout.setSpacing(10)
            self.main_layout.addLayout(self.top_layout)
        except Exception as e:
            QMessageBox.critical(self, "Помилка", f"Помилка налаштування layouts: {str(e)}")

    def setup_widgets(self):
        """Налаштування віджетів"""
        try:
            # URL Input
            self.url_input = QLineEdit(self)
            self.url_input.setPlaceholderText("Вставте URL відео...")
            self.url_input.setFixedWidth(700)
            self.url_input.textChanged.connect(self.on_url_changed)
            self.top_layout.addWidget(self.url_input)

            # Format Combo
            self.format_combo = QComboBox(self)
            self.format_combo.addItems(["MP4 (1080p)", "MP4 (4k)", "MP3", "M4A"])
            self.format_combo.currentTextChanged.connect(self.on_format_changed)
            self.top_layout.addWidget(self.format_combo)

            # Folder Button
            self.select_folder_btn = QPushButton("Вибрати папку", self)
            self.select_folder_btn.setIcon(QIcon(resource_path('assets/folder.png')))
            self.select_folder_btn.clicked.connect(self.select_folder)
            self.top_layout.addWidget(self.select_folder_btn)

            # Download Button
            self.download_btn = QPushButton("Завантажити", self)
            self.download_btn.clicked.connect(self.start_download)
            self.download_btn.setFixedHeight(40)
            self.download_btn.setFixedWidth(200)
            self.main_layout.addWidget(self.download_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            # Preview and Info
            self.setup_preview_section()

            # Progress Bar
            self.progress_bar = QProgressBar(self)
            self.main_layout.addWidget(self.progress_bar)

            # History
            self.history_text = QTextEdit(self)
            self.history_text.setReadOnly(True)
            self.history_text.setPlaceholderText("Історія завантажень...")
            self.main_layout.addWidget(self.history_text)

        except Exception as e:
            QMessageBox.critical(self, "Помилка", f"Помилка налаштування віджетів: {str(e)}")

    def setup_preview_section(self):
        """Налаштування секції превью"""
        try:
            preview_layout = QHBoxLayout()
            preview_layout.setSpacing(20)
            
            # Ліва колонка - превью
            preview_container = QWidget()
            preview_container.setFixedSize(400, 220)
            preview_container.setStyleSheet("border: 1px solid gray;")
            
            self.preview_label = QLabel(preview_container)
            self.preview_label.setFixedSize(400, 220)
            self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview_layout.addWidget(preview_container)

            # Права колонка - інформація
            info_container = QWidget()
            info_container.setFixedHeight(220)
            
            info_layout = QVBoxLayout(info_container)
            info_layout.setSpacing(15)  # Збільшуємо відступ між елементами
            info_layout.setContentsMargins(0, 30, 0, 0)  # Додаємо відступ зверху
            
            # Створюємо віджети для інформації
            self.video_title = QLabel("Назва: ", self)
            self.video_title.setWordWrap(True)
            self.video_title.setStyleSheet("""
                font-weight: bold;
                padding: 5px;
            """)
            
            self.video_format = QLabel("Формат: ", self)
            self.video_format.setStyleSheet("""
                color: #666;
                padding: 5px;
            """)
            
            self.video_url = QLabel("URL: ", self)
            self.video_url.setWordWrap(True)
            self.video_url.setStyleSheet("""
                color: #666;
                padding: 5px;
            """)
            
            # Додаємо віджети в layout з відступами
            info_layout.addWidget(self.video_title)
            info_layout.addWidget(self.video_format)
            info_layout.addWidget(self.video_url)
            info_layout.addStretch()
            
            preview_layout.addWidget(info_container)
            
            # Додаємо головний layout
            preview_widget = QWidget()
            preview_widget.setLayout(preview_layout)
            self.main_layout.addWidget(preview_widget)
            
        except Exception as e:
            QMessageBox.critical(self, "Помилка", f"Помилка налаштування превью: {str(e)}")

    def start_download(self):
        """Початок завантаження з перевірками"""
        try:
            if self.downloading:
                QMessageBox.warning(self, "Увага", "Завантаження вже виконується!")
                return

            if not self.save_path:
                QMessageBox.warning(self, "Помилка", "Виберіть папку для збереження!")
                return

            url = self.url_input.text().strip()
            if not url:
                QMessageBox.warning(self, "Помилка", "Введіть URL відео!")
                return

            self.downloading = True
            self.download_btn.setEnabled(False)
            self.progress_bar.setValue(0)
            
            # Створюємо потік завантаження
            self.download_thread = DownloadThread(
                url=url,
                save_path=self.save_path,
                selected_format=self.format_combo.currentText()
            )
            
            # Підключаємо сигнали
            self.download_thread.progress_update.connect(self.update_progress)
            self.download_thread.download_finished.connect(self.download_complete)
            
            # Запускаємо завантаження
            self.download_thread.start()
            
        except Exception as e:
            self.downloading = False
            self.download_btn.setEnabled(True)
            QMessageBox.critical(self, "Помилка", f"Помилка запуску завантаження: {str(e)}")

    def update_progress(self, progress):
        """Оновлення прогрес-бару"""
        try:
            if 0 <= progress <= 100:
                self.progress_bar.setValue(progress)
        except Exception as e:
            print(f"Помилка оновлення прогрес-бару: {str(e)}")

    def download_complete(self, message):
        """Обробка завершення завантаження"""
        try:
            self.downloading = False
            self.download_btn.setEnabled(True)
            self.add_to_history(message)
            
            if not message.startswith("Помилка"):
                self.clear_interface()
                
        except Exception as e:
            print(f"Помилка обробки завершення завантаження: {str(e)}")

    def add_to_history(self, message):
        """Додавання запису в історію"""
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            self.history_text.append(f"[{current_time}] {message}")
        except Exception as e:
            print(f"Помилка додавання в історію: {str(e)}")

    def clear_interface(self):
        """Очистка інтерфейсу"""
        try:
            self.url_input.clear()
            self.preview_label.clear()
            self.video_title.setText("Назва: ")
            self.video_format.setText("Формат: ")
            self.video_url.setText("URL: ")
            self.progress_bar.setValue(0)
        except Exception as e:
            print(f"Помилка очистки інтерфейсу: {str(e)}")

    def on_url_changed(self):
        """Обробка зміни URL"""
        try:
            if not hasattr(self, '_url_timer'):
                self._url_timer = QTimer()
                self._url_timer.setSingleShot(True)
                self._url_timer.timeout.connect(self.show_preview)
            
            self._url_timer.stop()
            self._url_timer.start(500)  # Затримка 500мс перед оновленням превью
            
        except Exception as e:
            print(f"Помилка при зміні URL: {str(e)}")

    def on_format_changed(self, new_format):
        """Обробка зміни формату"""
        try:
            if hasattr(self, 'video_format'):
                self.video_format.setText(f"Формат: {new_format}")
        except Exception as e:
            print(f"Помилка при зміні формату: {str(e)}")

    def show_preview(self):
        """Показ превью відео"""
        try:
            url = self.url_input.text().strip()
            if url and not self.downloading:
                if not url.startswith(('http://', 'https://')):
                    self.add_to_history("Помилка: Невірний формат URL")
                    return
                
                self.preview_thread = PreviewThread(url)
                self.preview_thread.preview_ready.connect(self.update_preview)
                self.preview_thread.error.connect(self.handle_preview_error)
                self.preview_thread.start()
            
        except Exception as e:
            self.add_to_history(f"Помилка превью: {str(e)}")

    def handle_preview_error(self, error_message):
        """Обробка помилок превью"""
        self.add_to_history(f"Помилка завантаження превью: {error_message}")
        self.clear_preview()

    def clear_preview(self):
        """Очистка превью"""
        try:
            self.preview_label.clear()
            self.video_title.setText("Назва: ")
            self.video_format.setText(f"Формат: {self.format_combo.currentText()}")
            self.video_url.setText("URL: ")
        except Exception as e:
            print(f"Помилка очистки превью: {str(e)}")

    def update_preview(self, pixmap, title):
        """Оновлення превью"""
        try:
            scaled_pixmap = pixmap.scaled(
                400, 220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.preview_label.setPixmap(scaled_pixmap)
            
            # Форматуємо текст
            title = title if len(title) <= 50 else title[:47] + "..."
            url = self.url_input.text().strip()
            url = url if len(url) <= 50 else url[:47] + "..."
            
            self.video_title.setText(f"Назва: {title}")
            self.video_format.setText(f"Формат: {self.format_combo.currentText()}")
            self.video_url.setText(f"URL: {url}")
            
        except Exception as e:
            print(f"Помилка оновлення превью: {str(e)}")

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

    def setup_download_options(self):
        self.selected_format = self.format_combo.currentText()
        
        ffmpeg_path = resource_path('ffmpeg.exe')
        
        ydl_opts = {
            'ffmpeg_location': ffmpeg_path,
            'outtmpl': os.path.join(self.save_path, '%(title)s.%(ext)s'),
            'progress_hooks': [self.progress_hook],
            'quiet': True
        }

        if self.selected_format == "MP4 (1080p)":
            ydl_opts.update({
                'format': 'bestvideo[height<=1080][vcodec!*=av1][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][vcodec!*=av1][vcodec!*=vp9][ext=mp4]/best',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }],
                'merge_output_format': 'mp4',
                'audio_quality': 0,
                'prefer_ffmpeg': True,
                'format_sort': ['res:1080', 'vcodec:h264', 'acodec:m4a']
            })
        
        elif self.selected_format == "MP4 (4k)":
            ydl_opts.update({
                'format': 'bestvideo[height<=2160][vcodec!*=av1][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160][vcodec!*=av1][vcodec!*=vp9][ext=mp4]/best',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4'
                }],
                'merge_output_format': 'mp4',
                'audio_quality': 0,
                'prefer_ffmpeg': True,
                'format_sort': ['res:2160', 'vcodec:h264', 'acodec:m4a']
            })
        
        elif self.selected_format == "MP3":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320'
                }],
                'audio_quality': 0,
                'prefer_ffmpeg': True
            })
        
        elif self.selected_format == "M4A":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '0'
                }],
                'audio_quality': 0,
                'prefer_ffmpeg': True
            })
        
        return ydl_opts

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
