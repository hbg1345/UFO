from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QPlainTextEdit,
                                QVBoxLayout, QHBoxLayout, QWidget, QDesktopWidget, QLabel, QStackedLayout, QLineEdit)
from PyQt5.QtCore import QProcess, QProcessEnvironment, Qt, QSize, QTimer, QThreadPool
from PyQt5.QtGui import QIcon, QPixmap
import sys
import os
from helper import Helper
from stt import recognize_speech_streaming
from tts import SpeakThread

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.p = None
        self.helper = None
        self.threadpool = QThreadPool()
        
        # 드래그 기능을 위한 변수들
        self.drag_start_position = None
        
        self.setWindowTitle("INO")

        icon = QIcon()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "ino_window_logo.png")
        icon.addFile(icon_path, QSize(32, 32))
        self.setWindowIcon(icon)
        
        # 화면 오른쪽 하단에 위치시키기
        self.resize(300, 400)  # 창 크기 설정
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 전체 스타일 설정
        self.apply_styles()

        self.text_box = QWidget()
        self.text_box.setFixedSize(290, 120)
        self.text_box.setObjectName("text_box")

        self.info_text = QLabel()
        self.info_text.setFixedSize(290, 120)
        self.info_text.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.info_text.setObjectName("info_text")
        self.info_text.setWordWrap(True)
        self.info_text.setTextFormat(Qt.RichText)  # Rich Text 모드 활성화

        self.command_text_input = QPlainTextEdit()
        self.command_text_input.setPlaceholderText("여기에 요청하고 싶은 일을 \n입력해 주세요.\n음성 인식 버튼을 눌러 \n말로 요청할 수도 있어요.")

        self.help_text_input = QPlainTextEdit()
        self.help_text_input.setPlaceholderText("여기에 하고 싶은 일을 입력하세요.\n차근차근 도와 드릴게요.\n음성 인식 버튼을 눌러 \n말로 이야기할 수도 있어요.")

        self.question_text_input = QPlainTextEdit()
        self.question_text_input.setPlaceholderText("여기에 질문을 \n입력해 주세요.\n음성 인식 버튼을 눌러 \n말로 질문할 수도 있어요.")

        self.text_box_layout = QStackedLayout()
        self.text_box_layout.setContentsMargins(0, 0, 0, 0)  # 스택 레이아웃 여백 제거
        self.text_box_layout.addWidget(self.info_text)
        self.text_box_layout.addWidget(self.command_text_input)
        self.text_box_layout.addWidget(self.help_text_input)
        self.text_box_layout.addWidget(self.question_text_input)
        self.text_box.setLayout(self.text_box_layout)

        self.main_btns = QWidget()
        self.main_btns.setFixedSize(290, 34)  # 테두리 공간 포함하여 34px로 증가

        self.command_btn = QPushButton("인터넷 사용")
        self.command_btn.setFixedSize(138, 30)
        self.command_btn.pressed.connect(self.start_process)
        self.command_btn.setCursor(Qt.PointingHandCursor)

        self.help_btn = QPushButton("컴퓨터 도움말")
        self.help_btn.setFixedSize(138, 30)
        self.help_btn.pressed.connect(self.start_help)
        self.help_btn.setCursor(Qt.PointingHandCursor)

        self.main_btns_layout = QHBoxLayout()
        self.main_btns_layout.setSpacing(0)  # 버튼 사이 간격 제거
        self.main_btns_layout.setContentsMargins(0, 0, 0, 0)  # 레이아웃 여백 제거
        self.main_btns_layout.addWidget(self.command_btn)
        self.main_btns_layout.addStretch()
        self.main_btns_layout.addWidget(self.help_btn)
        self.main_btns.setLayout(self.main_btns_layout)

        self.exit_btn = QPushButton("종료하기")
        self.exit_btn.pressed.connect(self.close)
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.setFixedSize(290, 30)

        self.command_btns = QWidget()
        self.command_btns.setFixedSize(290, 34)

        self.command_voice_btn = QPushButton("음성인식")
        self.command_voice_btn.setCursor(Qt.PointingHandCursor)
        self.command_voice_btn.setFixedSize(138, 30)
        self.command_voice_btn.pressed.connect(lambda: self._start_ufo_process([]))

        self.command_text_btn = QPushButton("시작하기")
        self.command_text_btn.setCursor(Qt.PointingHandCursor)
        self.command_text_btn.setFixedSize(138, 30)
        self.command_text_btn.pressed.connect(lambda: self._start_ufo_process(["-r", self.command_text_input.toPlainText()]))

        self.command_btns_layout = QHBoxLayout()
        self.command_btns_layout.setSpacing(0)
        self.command_btns_layout.setContentsMargins(0, 0, 0, 0)
        self.command_btns_layout.addWidget(self.command_voice_btn)
        self.command_btns_layout.addStretch()
        self.command_btns_layout.addWidget(self.command_text_btn)
        self.command_btns.setLayout(self.command_btns_layout)

        self.help_btns = QWidget()
        self.help_btns.setFixedSize(290, 34)

        self.help_voice_btn = QPushButton("음성인식")
        self.help_voice_btn.setCursor(Qt.PointingHandCursor)
        self.help_voice_btn.setFixedSize(138, 30)
        self.help_voice_btn.pressed.connect(self.start_help_voice)

        self.help_text_btn = QPushButton("시작하기")
        self.help_text_btn.setCursor(Qt.PointingHandCursor)
        self.help_text_btn.setFixedSize(138, 30)
        self.help_text_btn.pressed.connect(lambda: self.start_agent(self.help_text_input.toPlainText()))

        self.help_btns_layout = QHBoxLayout()
        self.help_btns_layout.setSpacing(0)
        self.help_btns_layout.setContentsMargins(0, 0, 0, 0)
        self.help_btns_layout.addWidget(self.help_voice_btn)
        self.help_btns_layout.addStretch()
        self.help_btns_layout.addWidget(self.help_text_btn)
        self.help_btns.setLayout(self.help_btns_layout)

        self.helping_btns = QWidget()
        self.helping_btns.setFixedSize(290, 34)

        self.question_btn = QPushButton("질문하기")
        self.question_btn.setFixedSize(138, 30)
        self.question_btn.setCursor(Qt.PointingHandCursor)
        self.question_btn.pressed.connect(self.start_question)
        
        self.next_btn = QPushButton("다음 단계")
        self.next_btn.pressed.connect(self.next_instruction)
        self.next_btn.setFixedSize(138, 30)
        self.next_btn.setCursor(Qt.PointingHandCursor)

        self.helping_btns_layout = QHBoxLayout()
        self.helping_btns_layout.setSpacing(0)
        self.helping_btns_layout.setContentsMargins(0, 0, 0, 0)
        self.helping_btns_layout.addWidget(self.question_btn)
        self.helping_btns_layout.addStretch()
        self.helping_btns_layout.addWidget(self.next_btn)
        self.helping_btns.setLayout(self.helping_btns_layout)

        self.question_btns = QWidget()
        self.question_btns.setFixedSize(290, 34)

        self.question_voice_btn = QPushButton("음성 인식")
        self.question_voice_btn.setCursor(Qt.PointingHandCursor)
        self.question_voice_btn.setFixedSize(138, 30)
        self.question_voice_btn.pressed.connect(self.submit_question_voice)

        self.question_text_btn = QPushButton("질문 전송")
        self.question_text_btn.setCursor(Qt.PointingHandCursor)
        self.question_text_btn.setFixedSize(138, 30)
        self.question_text_btn.pressed.connect(self.submit_question_text)

        self.question_btns_layout = QHBoxLayout()
        self.question_btns_layout.setSpacing(0)
        self.question_btns_layout.setContentsMargins(0, 0, 0, 0)
        self.question_btns_layout.addWidget(self.question_voice_btn)
        self.question_btns_layout.addStretch()
        self.question_btns_layout.addWidget(self.question_text_btn)
        self.question_btns.setLayout(self.question_btns_layout)

        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.pressed.connect(self.cancel)
        self.cancel_btn.setFixedSize(290, 30)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)

        
        # 캐릭터 애니메이션 설정
        self.character = QLabel()
        self.character.setObjectName("character")
        self.character.setAlignment(Qt.AlignCenter | Qt.AlignBottom)
        self.character.setFixedSize(200, 200)
        self.character.setCursor(Qt.PointingHandCursor)  # 드래그 가능한 커서
        
        # 캐릭터 이미지 경로 설정
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        self.character_image1 = os.path.join(assets_dir, "ino_character1.png")
        self.character_image2 = os.path.join(assets_dir, "ino_character2.png")
        self.current_character = 0  # 현재 표시 중인 캐릭터 (0 또는 1)
        
        # 애니메이션 타이머 설정
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_character_animation)
    

        l = QVBoxLayout()
        l.setSpacing(0)
        l.setContentsMargins(0, 0, 0, 0)  # 메인 레이아웃 여백 완전 제거
        l.addWidget(self.text_box)
        l.addWidget(self.main_btns)
        l.addWidget(self.exit_btn)
        l.addWidget(self.command_btns)
        l.addWidget(self.help_btns)
        l.addWidget(self.helping_btns)
        l.addWidget(self.question_btns)
        l.addWidget(self.cancel_btn)
        l.addWidget(self.character, 0, Qt.AlignHCenter)  # 캐릭터를 가로 기준 중앙에 정렬

        w = QWidget()
        w.setLayout(l)

        self.setCentralWidget(w)
        self.reset_to_initial_state()
        self.speak("안녕하세요! 저는 이노예요")

    def apply_styles(self):
        """QSS 스타일 적용"""
        style = """
        /* 메인 윈도우 스타일 */
        QMainWindow {
            background: transparent;
        }
        
        /* 중앙 위젯 스타일 */
        QWidget {
            background: transparent;
            font-family: "Segoe UI", "맑은 고딕";
            font-size: 17px;
        }

        QWidget#text_box {
            background: #FCF8ED;
            border: 2px solid #413B3A;
            border-radius: 10px;
            color: #413B3A;
            margin: 0;
        }

        QLabel#info_text {
            margin: 0;  /* margin 제거 */
            padding: 8px;  /* padding으로 변경하여 내부 여백만 유지 */
            text-align: left;
            vertical-align: top;
        }
        
        /* 버튼 공통 스타일 */
        QPushButton {
            background: #FCF8ED;
            border: 2px solid #413B3A;
            border-radius: 10px;
            color: #413B3A;
            font-weight: bold;
            margin: 0;
            padding: 0;
            vertical-align: top;
        }
        
        /* 텍스트 영역 스타일 */
        QPlainTextEdit {
            margin: 0;
            padding: 8px;
            text-align: left;
            vertical-align: top;
        }

        QPlainTextEdit:focus {
            border: none;
        }

        QLabel#character {
            margin: 0;
            padding: 0;
            text-align: center;
        }

        """
        self.setStyleSheet(style)

    def update_character_animation(self):
        """캐릭터 이미지를 번갈아 표시하는 애니메이션"""
        try:
            if self.current_character == 0:
                image_path = self.character_image1
                self.current_character = 1
            else:
                image_path = self.character_image2
                self.current_character = 0
            
            # 이미지 파일이 존재하는지 확인
            if os.path.exists(image_path):
                pixmap = QPixmap(image_path)
                # 이미지 크기를 라벨 크기에 맞게 조정 (비율 유지)
                scaled_pixmap = pixmap.scaled(self.character.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.character.setPixmap(scaled_pixmap)
            else:
                # 이미지 파일이 없으면 텍스트로 대체
                self.character.setText(f"🤖 INO {'1' if self.current_character == 0 else '2'}")
                
        except Exception as e:
            # 오류 발생 시 기본 텍스트 표시
            self.character.setText("🤖 INO")

    def showEvent(self, event):
        """창이 표시될 때 호출되는 이벤트 - 정확한 위치 계산"""
        super().showEvent(event)
        self.move_to_bottom_right()

    def move_to_bottom_right(self):
        """창을 화면 오른쪽 하단으로 이동"""
        # 데스크톱 화면 정보 가져오기
        desktop = QDesktopWidget()
        screen_geometry = desktop.availableGeometry()  # 사용 가능한 화면 영역 (작업표시줄 제외)

        # 창의 실제 크기 가져오기 (프레임 포함)
        window_rect = self.frameGeometry()  # 프레임 포함된 전체 크기
        window_width = window_rect.width()
        window_height = window_rect.height()

        # 안전한 여백 (작업표시줄 높이 고려)
        margin = 15

        # 화면 경계 내에서 계산
        x = max(0, screen_geometry.width() - window_width - margin)
        y = max(0, screen_geometry.height() - window_height - margin)
        
        # 창 위치 이동
        self.move(x, y)

    def reset_to_initial_state(self):
        """모든 버튼을 초기 상태로 복귀"""
        # 애니메이션 다시 시작 및 캐릭터 표시
        self.character.show()
        
        self.text_box_layout.setCurrentIndex(0)
        self.info_text.setText("""
            <p>인터넷 사용을 요청하고 싶으시면<br>
            <b>인터넷 사용</b> 버튼을 눌러 주세요.<br>
            컴퓨터 사용 도움말이 필요하면<br>
            <b>컴퓨터 도움말</b> 버튼을 눌러 주세요.</p>
        """)
        self.command_text_input.clear()
        self.help_text_input.clear()
        self.question_text_input.clear()
        self.command_btns.hide()
        self.help_btns.hide()
        self.helping_btns.hide()
        self.question_btns.hide()
        self.cancel_btn.hide()
        self.main_btns.show()
        self.exit_btn.show()

    def speak(self, text: str):
        self.animation_timer.start(500)
        speak_thread = SpeakThread(text)
        self.threadpool.start(speak_thread)
        speak_thread.signals.finished.connect(self.stop_animation)
    
    def stop_animation(self):
        self.animation_timer.stop()
        self.current_character = 0
        self.update_character_animation()

    def message(self, s):
        self.info_text.setText(s)

    def start_process(self):
        if self.p is None:
            self.text_box_layout.setCurrentIndex(1)
            self.main_btns.hide()
            self.exit_btn.hide()
            self.command_btns.show()
            self.cancel_btn.show()

    def _start_ufo_process(self, args):
        """UFO 프로세스를 시작하는 공통 함수"""

        if len(args) == 2 and args[1] == "":
            return

        self.text_box_layout.setCurrentIndex(0)
        self.info_text.setText("<p>잠시만 기다려 주세요...</p>")   
        self.command_btns.hide()
        self.cancel_btn.show()

        if self.p is not None:
            self.p.kill()
            self.p.waitForFinished(1000)
            self.p = None
            
        # 현재 Python 실행 파일 경로 사용 (가상환경이 활성화되어 있다면 자동으로 사용됨)
        python_exe = sys.executable
        
        self.p = QProcess()

        # UTF-8 환경변수 설정
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")  # Python 3.7+
        self.p.setProcessEnvironment(env)

        self.p.readyReadStandardOutput.connect(self.handle_stdout)
        self.p.readyReadStandardError.connect(self.handle_stderr)
        #self.p.stateChanged.connect(self.handle_state)
        self.p.finished.connect(self.process_finished)
        
        # UFO 모듈 실행
        cmd_args = ["-m", "ufo"] + args
        self.p.start(python_exe, cmd_args)

    def handle_stdout(self):
        data = self.p.readAllStandardOutput()
        stdout = bytes(data).decode("utf8", errors="replace")
        self.message(stdout)

    def handle_stderr(self):
        data = self.p.readAllStandardError()
        stderr = bytes(data).decode("utf8", errors="replace")
        self.message(stderr)

    def cancel(self):
        if self.p is not None:
            self.p.kill()
            self.p.waitForFinished(1000)
            self.p = None
        self.helper = None
        self.reset_to_initial_state()

    def process_finished(self):
        self.cancel()
        self.message("요청 수행을 완료했어요!")

    def start_help(self):
        self.text_box_layout.setCurrentIndex(2)
        self.main_btns.hide()
        self.exit_btn.hide()
        self.help_btns.show()
        self.cancel_btn.show()

    def start_help_voice(self):
        self.text_box_layout.setCurrentIndex(0)
        self.help_btns.hide()
        self.message("음성 인식 중이에요. 하고 싶은 일을 말씀해 주세요!")
        QApplication.processEvents()
        request = recognize_speech_streaming()
        self.message(request)
        self.start_agent(request)
    
    def start_agent(self, request):
        self.helper = Helper()
        self.text_box_layout.setCurrentIndex(0)
        self.message("<p>잠시만 기다려 주세요...</p>")
        self.speak("잠시만 기다려 주세요")
        
        # UI 업데이트를 강제로 처리
        QApplication.processEvents()
        
        response = self.helper.first_instruction(request)
        self.message(response.instruction)
        self.speak(response.instruction)
        self.help_btns.hide()
        self.helping_btns.show()
    
    def next_instruction(self, query="이 화면에서 뭘 해야해?"):
        self.text_box_layout.setCurrentIndex(0)
        self.question_btns.hide()
        self.helping_btns.show()
        self.message("<p>잠시만 기다려 주세요...</p>")
        
        # UI 업데이트를 강제로 처리
        QApplication.processEvents()
        
        response = self.helper.next_instruction(query)
        self.message(response.instruction)
        self.speak(response.instruction)
        
        # 응답이 완료되었는지 확인하여 버튼 상태 변경
        if hasattr(response, 'is_done') and response.is_done:
            self.reset_to_initial_state()

    def start_question(self):
        self.text_box_layout.setCurrentIndex(3)
        self.question_btns.show()
        self.helping_btns.hide()

    def submit_question_voice(self):
        self.text_box_layout.setCurrentIndex(0)
        self.question_btns.hide()
        self.message("음성 인식 중이에요. 궁금한 내용을 말씀해 주세요!")
        question = recognize_speech_streaming()
        self.message(f"question: {question}")
        self.next_instruction(question)

    def submit_question_text(self):
        question = self.question_text_input.toPlainText().strip()
        self.question_text_input.clear()
        self.next_instruction(question)

    def mousePressEvent(self, event):
        """캐릭터 영역에서 마우스 클릭 시 드래그 시작 위치 저장"""
        if event.button() == Qt.LeftButton:
            # 캐릭터 영역 내에서 클릭했는지 확인
            character_rect = self.character.geometry()
            if character_rect.contains(event.pos()):
                self.drag_start_position = event.globalPos() - self.frameGeometry().topLeft()
                # 드래그 가능한 상태임을 시각적으로 표시
                self.character.setCursor(Qt.ClosedHandCursor)
                event.accept()
            else:
                # 캐릭터 영역이 아니면 드래그 비활성화
                self.drag_start_position = None

    def mouseMoveEvent(self, event):
        """마우스 드래그 시 창 위치 이동"""
        if event.buttons() == Qt.LeftButton and self.drag_start_position:
            new_position = event.globalPos() - self.drag_start_position
            self.move(new_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        """마우스 릴리스 시 드래그 종료"""
        if event.button() == Qt.LeftButton:
            self.drag_start_position = None
            # 커서를 원래대로 복원
            self.character.setCursor(Qt.PointingHandCursor)
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    w = MainWindow()
    w.show()

    app.exec_()