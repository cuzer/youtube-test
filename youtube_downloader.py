import sys
import requests
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLineEdit, QPushButton, QLabel, QProgressBar, QMessageBox, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
import yt_dlp

# --- [1] 정보 조회용 쓰레드 (UI 멈춤 방지) ---
class InfoWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            # yt-dlp 옵션: 다운로드 하지 않고 정보만 가져옴
            ydl_opts = {'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.finished.emit(info)
        except Exception as e:
            self.error.emit(str(e))

# --- [2] 다운로드용 쓰레드 ---
class DownloadWorker(QThread):
    progress = pyqtSignal(float)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        # yt-dlp 진행률 콜백 함수
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    p = d.get('_percent_str', '0%').replace('%', '')
                    self.progress.emit(float(p))
                except:
                    pass
            elif d['status'] == 'finished':
                self.progress.emit(100)

        ydl_opts = {
            'format': 'best',  # 최고 화질
            'outtmpl': '%(title)s.%(ext)s',  # 파일명 설정
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

# --- [3] 메인 윈도우 UI ---
class YoutubeApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.current_video_info = None # 현재 조회된 비디오 정보 저장

    def initUI(self):
        self.setWindowTitle('나만의 유튜브 다운로더 (yt-dlp)')
        self.setGeometry(300, 300, 500, 600)

        layout = QVBoxLayout()

        # 1. URL 입력 부분
        input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("유튜브 링크를 여기에 붙여넣으세요")
        self.search_btn = QPushButton("조회")
        self.search_btn.clicked.connect(self.search_video)
        
        input_layout.addWidget(self.url_input)
        input_layout.addWidget(self.search_btn)
        layout.addLayout(input_layout)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # 2. 정보 표시 부분 (썸네일, 제목 등)
        self.thumbnail_label = QLabel("썸네일이 여기에 표시됩니다")
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumHeight(250)
        self.thumbnail_label.setStyleSheet("border: 1px solid #ccc; background: #f0f0f0;")
        layout.addWidget(self.thumbnail_label)

        self.title_label = QLabel("- 제목: 대기중")
        self.title_label.setWordWrap(True) # 긴 제목 줄바꿈
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px;")
        layout.addWidget(self.title_label)

        self.views_label = QLabel("- 조회수: 0회")
        layout.addWidget(self.views_label)

        self.likes_label = QLabel("- 좋아요: 0개")
        layout.addWidget(self.likes_label)

        layout.addStretch() # 여백 추가

        # 3. 다운로드 버튼 및 진행바
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.download_btn = QPushButton("다운로드 시작")
        self.download_btn.setEnabled(False) # 조회 전에는 비활성화
        self.download_btn.setStyleSheet("background-color: #ff0000; color: white; font-weight: bold; padding: 10px;")
        self.download_btn.clicked.connect(self.download_video)
        layout.addWidget(self.download_btn)

        self.status_label = QLabel("준비 완료")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    # --- 조회 기능 ---
    def search_video(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "경고", "링크를 입력해주세요!")
            return

        self.status_label.setText("정보 조회 중... 잠시만 기다려주세요.")
        self.search_btn.setEnabled(False)
        
        # 쓰레드 실행
        self.info_worker = InfoWorker(url)
        self.info_worker.finished.connect(self.update_info)
        self.info_worker.error.connect(self.show_error)
        self.info_worker.start()

    def update_info(self, info):
        self.current_video_info = info
        self.search_btn.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.status_label.setText("조회 성공! 다운로드가 가능합니다.")

        # 텍스트 정보 업데이트 (천단위 콤마 추가)
        title = info.get('title', '제목 없음')
        views = f"{info.get('view_count', 0):,}"
        likes = f"{info.get('like_count', 0):,}"

        self.title_label.setText(f"- 제목: {title}")
        self.views_label.setText(f"- 조회수: {views}회")
        self.likes_label.setText(f"- 좋아요: {likes}개")

        # 썸네일 이미지 로드
        thumbnail_url = info.get('thumbnail')
        if thumbnail_url:
            image_data = requests.get(thumbnail_url).content
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            # 라벨 크기에 맞춰 비율 유지하며 리사이즈
            scaled_pixmap = pixmap.scaled(self.thumbnail_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.thumbnail_label.setPixmap(scaled_pixmap)

    # --- 다운로드 기능 ---
    def download_video(self):
        if not self.url_input.text():
            return
        
        self.status_label.setText("다운로드 시작...")
        self.download_btn.setEnabled(False)
        self.progress_bar.setValue(0)

        # 쓰레드 실행
        self.download_worker = DownloadWorker(self.url_input.text())
        self.download_worker.progress.connect(self.update_progress)
        self.download_worker.finished.connect(self.download_finished)
        self.download_worker.error.connect(self.show_error)
        self.download_worker.start()

    def update_progress(self, percent):
        self.progress_bar.setValue(int(percent))
        self.status_label.setText(f"다운로드 중... {percent}%")

    def download_finished(self):
        self.status_label.setText("다운로드 완료!")
        self.download_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "성공", "영상이 현재 폴더에 저장되었습니다.")

    def show_error(self, message):
        self.status_label.setText("오류 발생")
        self.search_btn.setEnabled(True)
        self.download_btn.setEnabled(True)
        QMessageBox.critical(self, "에러", f"작업 중 오류가 발생했습니다:\n{message}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = YoutubeApp()
    ex.show()
    sys.exit(app.exec())