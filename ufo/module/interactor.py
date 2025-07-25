# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from .. import utils

from art import text2art
from typing import Tuple
import queue
import pyaudio
import websocket
import json
import threading
import time
from urllib.parse import urlencode
from dotenv import load_dotenv
import os
import assemblyai as aai
import sounddevice as sd
from scipy.io.wavfile import write
import tempfile
import numpy as np

load_dotenv()
aai.settings.api_key = os.getenv("AssemblyAI_KEY")

WELCOME_TEXT = """
Welcome to use UFO🛸, A UI-focused Agent for Windows OS Interaction. 
{art}
Please enter your request to be completed🛸: """.format(
    art=text2art("UFO")
)

# AssemblyAI 음성 인식 설정 (사용 전 pip install pyaudio websocket-client)
YOUR_API_KEY = os.getenv("AssemblyAI_KEY")  # 여기에 AssemblyAI API 키를 입력하세요
CONNECTION_PARAMS = {
    "sample_rate": 16000,
    "format_turns": True,
}
API_ENDPOINT_BASE_URL = "wss://streaming.assemblyai.com/v3/ws"
API_ENDPOINT = f"{API_ENDPOINT_BASE_URL}?{urlencode(CONNECTION_PARAMS)}"
FRAMES_PER_BUFFER = 800
SAMPLE_RATE = CONNECTION_PARAMS["sample_rate"]
CHANNELS = 1
FORMAT = pyaudio.paInt16
stop_event = threading.Event()

def recognize_speech_assemblyai_streaming(timeout=15):
    result_queue = queue.Queue()
    audio = pyaudio.PyAudio()
    stream = None
    ws_app = None
    audio_thread = None
    stop_event = threading.Event()

    def on_open(ws):
        def stream_audio():
            nonlocal stream
            while not stop_event.is_set():
                try:
                    audio_data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
                    ws.send(audio_data, websocket.ABNF.OPCODE_BINARY)
                except Exception:
                    break
        nonlocal audio_thread
        audio_thread = threading.Thread(target=stream_audio)
        audio_thread.daemon = True
        audio_thread.start()

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if data.get('type') == "Turn":
                transcript = data.get('transcript', '')
                is_final = data.get('turn_is_final', False)
                is_formatted = data.get('turn_is_formatted', False)
                if is_final or is_formatted:
                    print(f"\n[음성 인식 결과] {transcript}")
                    result_queue.put(transcript)
                    stop_event.set()
        except Exception:
            pass

    def on_error(ws, error):
        stop_event.set()
    def on_close(ws, close_status_code, close_msg):
        stop_event.set()
        if stream:
            try:
                if stream.is_active():
                    stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if audio:
            try:
                audio.terminate()
            except Exception:
                pass
        if audio_thread and audio_thread.is_alive():
            audio_thread.join(timeout=1.0)

    try:
        stream = audio.open(
            input=True,
            frames_per_buffer=FRAMES_PER_BUFFER,
            channels=CHANNELS,
            format=FORMAT,
            rate=SAMPLE_RATE,
        )
        print("마이크가 열렸습니다. 말씀하세요... (말이 끝나면 자동으로 인식)")
    except Exception as e:
        print(f"마이크 오류: {e}")
        if audio:
            audio.terminate()
        return ""
    ws_app = websocket.WebSocketApp(
        API_ENDPOINT,
        header={"Authorization": YOUR_API_KEY},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws_thread = threading.Thread(target=ws_app.run_forever)
    ws_thread.daemon = True
    ws_thread.start()
    try:
        transcript = result_queue.get(timeout=timeout)  # timeout 내에 결과가 오면 반환
    except queue.Empty:
        transcript = ""
        print("음성 인식 결과를 받지 못했습니다.")
    stop_event.set()
    if ws_app:
        ws_app.close()
    ws_thread.join(timeout=2.0)
    if stream:
        try:
            if stream.is_active():
                stream.stop_stream()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
    if audio:
        try:
            audio.terminate()
        except Exception:
            pass
    return transcript


def first_request() -> str:
    """
    Ask for the first request.
    :return: The first request.
    """
    return recognize_speech_assemblyai_streaming()


def new_request() -> Tuple[str, bool]:
    """
    Ask for a new request.
    :return: The new request and whether the conversation is complete.
    """

    utils.print_with_color(
        """Please enter your new request. Enter 'N' for exit.""", "cyan"
    )
    request = input()
    if request.upper() == "N":
        complete = True
    else:
        complete = False

    return request, complete


def experience_asker() -> bool:
    """
    Ask for saving the conversation flow for future reference.
    :return: Whether to save the conversation flow.
    """
    utils.print_with_color(
        """Would you like to save the current conversation flow for future reference by the agent?
[Y] for yes, any other key for no.""",
        "magenta",
    )

    ans = input()

    if ans.upper() == "Y":
        return True
    else:
        return False


def question_asker(question: str, index: int) -> str:
    """
    Ask for the user input for the question.
    :param question: The question to ask.
    :param index: The index of the question.
    :return: The user input.
    """

    utils.print_with_color(
        """[Question {index}:] {question}""".format(index=index, question=question),
        "cyan",
    )
    
    return input()


def sensitive_step_asker(action, control_text) -> bool:
    """
    Ask for confirmation for sensitive steps.
    :param action: The action to be performed.
    :param control_text: The control text.
    :return: Whether to proceed.
    """

    utils.print_with_color(
        "[Input Required:] UFO🛸 will apply {action} on the [{control_text}] item. Please confirm whether to proceed or not. Please input Y or N.".format(
            action=action, control_text=control_text
        ),
        "magenta",
    )

    while True:
        user_input = input().upper()

        if user_input == "Y":
            return True
        elif user_input == "N":
            return False
        else:
            print("Invalid choice. Please enter either Y or N. Try again.")
