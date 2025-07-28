from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QPlainTextEdit,
                                QVBoxLayout, QWidget, QDesktopWidget)
from PyQt5.QtCore import QProcess, QProcessEnvironment, Qt, QSize
from PyQt5.QtGui import QIcon
import sys
import os

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

        self.btn = QPushButton("요청하기")
        self.btn.pressed.connect(self.start_process)
        
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)

        l = QVBoxLayout()
        l.addWidget(self.btn)
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
            self.message("Excecuting process")

            # 가상환경 경로 설정
            venv_path = r"C:\Users\serin\workspace\madcamp\UFO\ufo_env"
            python_exe = os.path.join(venv_path, "Scripts", "python.exe")  # Windows
            # python_exe = os.path.join(venv_path, "bin", "python")  # Linux/Mac

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
            self.p.start(python_exe, ["-m", "ufo", "-t", "task_name"])

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


if __name__ == "__main__":
    app = QApplication(sys.argv)

    w = MainWindow()
    w.show()

    app.exec_()