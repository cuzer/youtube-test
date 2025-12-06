import sys
import os
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QLabel, 
                             QMessageBox, QProgressBar)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import yt_dlp

# --- [1] 정보 조회용 작업 스레드 ---
class InfoWorker(QThread):
    finished = pyqtSignal(dict) # 작업 완료 시 데이터 전송
    error = pyqtSignal(str)     # 에러 발생 시 메시지 전송

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # API 없이 페이지 정보를 긁어옴
                info = ydl.extract_info(self.url, download=False)
                
                # 필요한 정보만 딕셔너리로 정리
                data = {
                    'title': info.get('title', '제목 없음'),
                    'thumbnail': info.get('thumbnail', ''),
                    'view_count': info.get('view_count', 0),
                    'like_count': info.get('like_count', 0),
                    'url': self.url
                }
                self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

# --- [2] 다운로드용 작업 스레드 (FFmpeg 연동 및 고화질 수정) ---
class DownloadWorker(QThread):
    finished = pyqtSignal(str)
    progress = pyqtSignal(str) 

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        # 0. 현재 폴더에 ffmpeg.exe가 있는지 확인 (중요)
        # ffmpeg가 없으면 고화질 다운로드가 안되거나 에러가 납니다.
        if not os.path.exists('ffmpeg.exe'):
             # 시스템 경로에 설치된 경우도 있으니 경고만 하고 진행하거나,
             # 확실하게 하려면 여기서 return으로 멈춰도 됩니다.
             print("주의: ffmpeg.exe를 찾을 수 없습니다. 고화질 병합이 실패할 수 있습니다.")

        try:
            ydl_opts = {
                # [핵심] 최고 화질 비디오 + 최고 화질 오디오
                'format': 'bestvideo+bestaudio/best', 
                
                # [핵심] FFmpeg를 사용하여 MP4로 병합
                'merge_output_format': 'mp4',
                
                # 혹시 ffmpeg를 못 찾을 경우를 대비해 현재 폴더 위치를 명시
                'ffmpeg_location': os.getcwd(), 
                
                'outtmpl': '%(title)s.%(ext)s',
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
            
            self.finished.emit("고화질 다운로드 완료! (ffmpeg 병합 성공)")
        except Exception as e:
            self.finished.emit(f"다운로드 실패: {str(e)}")

# --- [3] 메인 윈도우 UI ---
class YoutubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle("YouTube Downloader (yt-dlp)")
        self.setGeometry(100, 100, 500, 600)

        # 메인 위젯 설정
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # 1. 상단: URL 입력 및 조회 버튼
        input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("유튜브 링크를 붙여넣으세요...")
        self.btn_search = QPushButton("조회")
        self.btn_search.clicked.connect(self.start_search)
        
        input_layout.addWidget(self.url_input)
        input_layout.addWidget(self.btn_search)
        layout.addLayout(input_layout)

        # 2. 중간: 정보 표시 영역 (썸네일, 제목, 조회수/좋아요)
        self.lbl_thumbnail = QLabel()
        self.lbl_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumbnail.setMinimumHeight(250)
        self.lbl_thumbnail.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        layout.addWidget(self.lbl_thumbnail)

        self.lbl_title = QLabel("영상 제목이 여기에 표시됩니다.")
        self.lbl_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_title.setWordWrap(True) # 긴 제목 줄바꿈
        layout.addWidget(self.lbl_title)

        stats_layout = QHBoxLayout()
        self.lbl_views = QLabel("조회수: -")
        self.lbl_likes = QLabel("좋아요: -")
        stats_layout.addWidget(self.lbl_views)
        stats_layout.addWidget(self.lbl_likes)
        layout.addLayout(stats_layout)

        layout.addStretch(1) # 빈 공간 채우기

        # 3. 하단: 다운로드 버튼 및 상태 표시
        self.status_label = QLabel("준비됨")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.btn_download = QPushButton("영상 다운로드")
        self.btn_download.setFixedHeight(50)
        self.btn_download.setStyleSheet("background-color: #ff0000; color: white; font-weight: bold;")
        self.btn_download.setEnabled(False) # 조회 전에는 비활성화
        self.btn_download.clicked.connect(self.start_download)
        layout.addWidget(self.btn_download)

        # 데이터 저장소
        self.current_video_data = None

    # --- 기능 함수들 ---
    def start_search(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "경고", "URL을 입력해주세요.")
            return

        self.status_label.setText("정보를 가져오는 중...")
        self.btn_search.setEnabled(False)
        
        # 스레드 시작
        self.worker = InfoWorker(url)
        self.worker.finished.connect(self.update_ui)
        self.worker.error.connect(self.show_error)
        self.worker.start()

    def update_ui(self, data):
        self.current_video_data = data
        self.btn_search.setEnabled(True)
        self.status_label.setText("정보 조회 완료")

        # 텍스트 정보 업데이트 (숫자에 콤마 추가)
        self.lbl_title.setText(data['title'])
        self.lbl_views.setText(f"조회수: {data['view_count']:,}회")
        self.lbl_likes.setText(f"좋아요: {data['like_count']:,}개")

        # 썸네일 이미지 다운로드 및 표시
        if data['thumbnail']:
            try:
                image_data = requests.get(data['thumbnail']).content
                pixmap = QPixmap()
                pixmap.loadFromData(image_data)
                # 이미지 크기를 라벨에 맞게 조정 (비율 유지)
                scaled_pixmap = pixmap.scaled(self.lbl_thumbnail.width(), self.lbl_thumbnail.height(), 
                                            Qt.AspectRatioMode.KeepAspectRatio)
                self.lbl_thumbnail.setPixmap(scaled_pixmap)
            except:
                self.lbl_thumbnail.setText("이미지 로드 실패")
        
        self.btn_download.setEnabled(True)

    def start_download(self):
        if not self.current_video_data:
            return

        self.status_label.setText("다운로드 중... 잠시만 기다려주세요.")
        self.btn_download.setEnabled(False)
        self.url_input.setEnabled(False)

        # 다운로드 스레드 시작
        self.dl_worker = DownloadWorker(self.current_video_data['url'])
        self.dl_worker.finished.connect(self.download_finished)
        self.dl_worker.start()

    def download_finished(self, message):
        self.status_label.setText(message)
        self.btn_download.setEnabled(True)
        self.url_input.setEnabled(True)
        QMessageBox.information(self, "알림", message)

    def show_error(self, err_msg):
        self.status_label.setText("에러 발생")
        self.btn_search.setEnabled(True)
        QMessageBox.critical(self, "에러", f"정보를 가져오는데 실패했습니다.\n{err_msg}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = YoutubeDownloader()
    window.show()
    sys.exit(app.exec())