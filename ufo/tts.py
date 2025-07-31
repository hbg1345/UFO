import os
from datetime import datetime
from google.cloud import texttospeech
from PyQt5.QtCore import QRunnable, pyqtSlot, QObject, pyqtSignal
import time

class SpeakSignals(QObject):
    finished = pyqtSignal()

class SpeakThread(QRunnable):
    '''
    TTS thread
    '''
    def __init__(self, text: str):
        super().__init__()
        self.text = text
        self.signals = SpeakSignals()

    @pyqtSlot()
    def run(self):
        """Generate an English speech file using Google Cloud TTS, play it with pygame, delete it, and return the file path (default: en-US, Standard-B)."""
        try:
            client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(text=self.text)
            voice_name = "ko-KR-Standard-D"
            voice = texttospeech.VoiceSelectionParams(
                language_code="ko-KR",
                name=voice_name,
                ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0
            )
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"gcloud_tts-{voice_name}-{current_time}.mp3"
            with open(file_name, "wb") as out:
                out.write(response.audio_content)
                print(f"✅ 음성 파일 생성 완료: {file_name}")
            # Play the audio file with pygame only
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(file_name)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)  # 100ms 대기로 CPU 사용량 줄이기
                pygame.mixer.music.unload()  # Release file handle
            except Exception as e2:
                print(f"[TTS Playback Error] pygame: {e2}\n(Install with: pip install pygame)")
            # Delete the audio file after playback
            try:
                os.remove(file_name)
                print(f"🗑️ 음성 파일 삭제 완료: {file_name}")
            except Exception as e:
                print(f"[TTS File Delete Error] {e}")
        except Exception as e:
            print(f"[TTS Error] {e}")
        finally:
            self.signals.finished.emit()

