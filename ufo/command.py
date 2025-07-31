from PyQt5.QtCore import pyqtSignal, QThread
import re
_ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')


# 2) QRunnable에 시그널 객체를 붙이고 stdout을 가로채서 emit
class UfoThread(QThread):
    output = pyqtSignal(str)

    def __init__(self, args):
        super(UfoThread, self).__init__()
        self.args = args

    def run(self):
        import sys
        import comtypes
        comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
        from ufo import ufo

        # 3) stdout을 가로채는 임시 클래스
        class StreamCatcher:
            def __init__(self, signal):
                self.signal = signal
            def write(self, text):
                clean = _ansi_escape.sub('', text)
                if clean.strip():
                    self.signal.emit(clean)
            def flush(self):
                pass

        # 4) 원래 stdout 백업 후 교체
        old_stdout = sys.stdout
        sys.stdout = StreamCatcher(self.output)
        try:
            ufo.main(self.args)
        finally:
            sys.stdout = old_stdout
