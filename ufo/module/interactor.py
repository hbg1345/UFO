# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import dotenv
dotenv.load_dotenv()
from ufo import utils
import queue
import sys
import time
from google.cloud import speech
import pyaudio
from art import text2art
from google.api_core import exceptions
from typing import Tuple

RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
TIMEOUT_FROM_RESPONSE = 6

WELCOME_TEXT = """
Welcome to use UFO🛸, A UI-focused Agent for Windows OS Interaction. 
{art}
Please enter your request to be completed🛸: """.format(
    art=text2art("UFO")
)

class MicrophoneStream:
    """Opens a recording stream as a generator yielding the audio chunks."""
    def __init__(self, rate: int = RATE, chunk: int = CHUNK) -> None:
        self._rate = rate
        self._chunk = chunk
        self._buff = queue.Queue()
        self.closed = True
    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk,
            stream_callback=self._fill_buffer,
        )
        self.closed = False
        return self
    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        self._buff.put(None)
        self._audio_interface.terminate()
    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        self._buff.put(in_data)
        return None, pyaudio.paContinue
    def generator(self):
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break
            yield b"".join(data)

def listen_print_loop(responses):
    transcript = ""
    try: 
        for response in responses:
            if not response.results:
                continue
            result = response.results[0]
            if not result.alternatives:
                continue
            transcript = result.alternatives[0].transcript
            if result.is_final:
                break
    except exceptions.DeadlineExceeded:
        return transcript
    
def recognize_speech_assemblyai_streaming():
    """
    Recognize speech from the microphone using Google Cloud Speech-to-Text.
    :param timeout: Not used (kept for compatibility)
    :return: The recognized transcript.
    """
    language_code = "ko-KR"  # or "en-US" for English
    client = speech.SpeechClient()
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=RATE,
        language_code=language_code,
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=config, interim_results=True
    )
    with MicrophoneStream(RATE, CHUNK) as stream:
        audio_generator = stream.generator()
        requests = (
            speech.StreamingRecognizeRequest(audio_content=content)
            for content in audio_generator
        )
        print("무엇을 도와드릴까요?")
        try:
            utils.speak_text("무엇을 도와드릴까요?", lang="ko-KR")
        except Exception as e:
            print(f"[TTS Error] {e}")
        print("🎤 음성 인식을 시작합니다...")
        return input()
        responses = client.streaming_recognize(streaming_config, requests, timeout=TIMEOUT_FROM_RESPONSE)
        result = listen_print_loop(responses)
        print(result)
        return result


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
    guide = """또 무엇을 도와드릴까요? 종료를 원하면 종료라고 말해주세요."""
    utils.print_with_color(
        guide, "cyan"
    )
    utils.speak_text(guide, lang="ko-KR")
    request = recognize_speech_assemblyai_streaming()
    if request.upper() == "N" or request.strip() == "종료":
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
    question_text = f"[Question {index}:] {question}"
    utils.print_with_color(question_text, "cyan")
    # Speak the question before input
    try:
        utils.speak_text(question_text)
    except Exception as e:
        print(f"[TTS Error] {e}")
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
