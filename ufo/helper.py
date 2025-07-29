import os
from openai import OpenAI
from openai_agents import Agent, SQLiteSession, Runner
from io import BytesIO
from PIL import ImageGrab
import base64
import queue
import pyaudio
from google.cloud import speech
from google.api_core import exceptions

RATE = 16000
CHUNK = int(RATE / 10)  # 100ms
TIMEOUT_FROM_RESPONSE = 6

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
        responses = client.streaming_recognize(streaming_config, requests, timeout=TIMEOUT_FROM_RESPONSE)
        result = listen_print_loop(responses)
        print(result)
        return result

system_prompt = """
You are a kind and patient digital assistant that helps elderly users who are not familiar with computers. 
When a user tells you what they want to do (e.g., check the weather, write a document), guide them step-by-step on how to perform the task.
Each time you will be given a screenshot. Use it to determine the next action they need to take.
Each response consists of a step(int), an instruction(string), and is_done(boolean).
step starts from 1 and increases by 1 for each response.
instruction is the next action they need to take. It must be written in Korean.
Avoid technical jargon; use simple expressions elderly people can understand.
When the task is complete, set is_done to True.
If the user asks a question that is not related to the task, set is_done to True.
"""

class Response():
    step: int
    instruction: str
    is_done: bool

class Helper():
    def __init__(self):
        self.step = 0
        self.request = None
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.buffer = BytesIO()
        self.agent = Agent(
            name="PC Helper",
            instructions = system_prompt,
            output_type = Response,
            model = "gpt-4o-mini"
        )
        self.session = SQLiteSession()

    def get_request(self):
        self.request = recognize_speech_assemblyai_streaming()
        return self.request

    def first_instruction(self, query):

        encoded_screenshot = self.take_screenshot()

        response = Runner.sync_run(
            agent = self.agent,
            session = self.session,
            input = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {"type": "image_url", "image_url": f"data:image/png;base64,{encoded_screenshot}"}
                ]
            }],
        )
        return response

    def next_instruction(self):

        encoded_screenshot = self.take_screenshot()

        response = Runner.sync_run(
            agent = self.agent,
            session = self.session,
            input = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "다음으로 뭘 해야해?"},
                    {"type": "image_url", "image_url": f"data:image/png;base64,{encoded_screenshot}"}
                ]
            }],
        )
        return response

    def take_screenshot(self):
        screenshot = ImageGrab.grab()
        screenshot.save(self.buffer, format="PNG")
        self.buffer.seek(0)
        encoded_screenshot = base64.b64encode(self.buffer.getvalue()).decode("utf-8")
        return encoded_screenshot


