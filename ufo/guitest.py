from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QPlainTextEdit,
                                QVBoxLayout, QWidget, QDesktopWidget, QLineEdit)
from PyQt5.QtCore import QProcess, QProcessEnvironment, Qt, QSize
from PyQt5.QtGui import QIcon
import sys
import os
from helper import Helper

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.p = None

        self.setWindowTitle("INO")

        icon = QIcon()
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "ino_window_logo.png")
        icon.addFile(icon_path, QSize(32, 32))
        self.setWindowIcon(icon)
        
        # 화면 오른쪽 하단에 위치시키기
        self.resize(400, 300)  # 창 크기 설정
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.command_btn = QPushButton("요청하기")
        self.command_btn.pressed.connect(self.start_process)

        self.help_btn = QPushButton("도움받기")
        self.help_btn.pressed.connect(self.start_agent)

        self.command_voice_btn = QPushButton("말로 요청하기")
        self.command_voice_btn.pressed.connect(self.start_process_voice)
        self.command_voice_btn.hide()

        self.command_text_btn = QPushButton("글로 요청하기")
        self.command_text_btn.pressed.connect(self.start_process_text)
        self.command_text_btn.hide()

        self.command_text_input = QLineEdit()
        self.command_text_input.returnPressed.connect(self.submit_text)
        self.command_text_input.hide()

        # 다음 단계 버튼 (처음에는 숨김)
        self.next_btn = QPushButton("다음 단계")
        self.next_btn.pressed.connect(self.next_instruction)
        self.next_btn.hide()  # 처음에는 숨김
        
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)

        l = QVBoxLayout()
        l.addWidget(self.command_btn)
        l.addWidget(self.help_btn)
        l.addWidget(self.next_btn)
        l.addWidget(self.command_voice_btn)
        l.addWidget(self.command_text_btn)
        l.addWidget(self.command_text_input)  # 텍스트 입력창 추가
        l.addWidget(self.text)

        w = QWidget()
        w.setLayout(l)

        self.setCentralWidget(w)

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
        margin = 20

        # 화면 경계 내에서 계산
        x = max(0, screen_geometry.width() - window_width - margin)
        y = max(0, screen_geometry.height() - window_height - margin)
        
        # 창 위치 이동
        self.move(x, y)

    def message(self, s):
        self.text.appendPlainText(s)

    def start_process(self):
        if self.p is None:
            self.message("Executing process")
            self.command_btn.hide()
            self.help_btn.hide()
            self.command_voice_btn.show()
            self.command_text_btn.show()

    def start_process_voice(self):
        self.message("Executing process with voice recognition")
        self.command_voice_btn.hide()
        self.command_text_btn.hide()
        
        self._start_ufo_process([])  # 기본 UFO 실행

    def start_process_text(self):
        self.command_voice_btn.hide()
        self.command_text_btn.hide()
        self.command_text_input.show()
        self.command_text_input.setPlaceholderText("원하는 작업을 입력하세요...")
        self.command_text_input.setFocus()  # 입력창에 포커스

    def submit_text(self):
        text = self.command_text_input.text().strip()
        
        if not text:  # 빈 텍스트 체크
            self.message("텍스트를 입력해주세요!")
            return
            
        self.message(f"Executing process with text: {text}")
        self.command_text_input.hide()
        self.command_text_input.clear()  # 입력창 초기화
        
        self._start_ufo_process(["-r", text])  # 공통 함수 사용

    def _start_ufo_process(self, args):
        """UFO 프로세스를 시작하는 공통 함수"""
        if self.p is not None:
            self.message("Process already running!")
            return
            
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
        self.p.stateChanged.connect(self.handle_state)
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

    def handle_state(self, s):
        states = {
            QProcess.NotRunning: "Not running",
            QProcess.Starting: "Starting",
            QProcess.Running: "Running",
        }
        self.message("State changed to %s" % states[s])

    def process_finished(self):
        self.message("Process finished")
        self.p = None
        # 프로세스 종료 후 초기 상태로 복귀
        self.reset_to_initial_state()
    
    def reset_to_initial_state(self):
        """모든 버튼을 초기 상태로 복귀"""
        self.command_btn.show()
        self.help_btn.show()
        self.next_btn.hide()
        self.command_voice_btn.hide()
        self.command_text_btn.hide()
        self.command_text_input.hide()
        self.command_text_input.clear()

    def start_agent(self):
        self.help_btn.hide()  # 도움받기 버튼 숨기기
        self.command_btn.hide()  # 요청하기 버튼 숨기기

        self.message("Starting agent")
        self.helper = Helper()
        request = self.helper.get_request()
        self.message(f"request: {request}")
        response = self.helper.first_instruction(request)
        self.message(f"response: {response}")
        
        # 첫 번째 응답 후 다음 단계 버튼 표시
        self.next_btn.show()
    
    def next_instruction(self):
        self.message("Getting next instruction...")
        response = self.helper.next_instruction()
        self.message(f"response: {response}")
        
        # 응답이 완료되었는지 확인하여 버튼 상태 변경
        if hasattr(response, 'is_done') and response.is_done:
            self.reset_to_initial_state()
            self.message("Task completed!")



if __name__ == "__main__":
    app = QApplication(sys.argv)

    w = MainWindow()
    w.show()

    app.exec_()