from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QPlainTextEdit,
                                QVBoxLayout, QWidget, QProgressBar)
from PyQt5.QtCore import QProcess, QProcessEnvironment
import sys
import os

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.p = None

        self.btn = QPushButton("Execute")
        self.btn.pressed.connect(self.start_process)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)

        l = QVBoxLayout()
        l.addWidget(self.btn)
        l.addWidget(self.text)

        w = QWidget()
        w.setLayout(l)

        self.setCentralWidget(w)

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