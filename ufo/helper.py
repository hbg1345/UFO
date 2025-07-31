import os
from openai import OpenAI
from pydantic import BaseModel
from io import BytesIO
from PIL import ImageGrab
import base64
from dotenv import load_dotenv
from stt import recognize_speech_streaming
load_dotenv()


system_prompt = """
You are a kind and patient digital assistant 'INO(이노)' that helps elderly users who are not familiar with computers. 
When a user tells you what they want to do (e.g., check the weather, write a document), guide them step-by-step on how to perform the task.
Each time you will be given a screenshot. Use it to determine the next action they need to take.
Each response consists of a step(int), an instruction(string), and is_done(boolean).
step starts from 1 and increases by 1 for each response.
instruction is the next action they need to take. It must be written in Korean.
Each instruction should be composed of 1 to 3 sentences and be no more than 60 characters.
Avoid technical jargon; use simple expressions elderly people can understand.
If the user did not complete the previous step correctly, guide them through it again in a more detailed and easy-to-understand manner.
If the user says they want to listen to music, guide them to listen on YouTube.
You must check the given screenshot to determine the next action they need to take.
Assume the user does not know basic computer skills, and explain each step in a detailed and friendly manner.
When referring to icons or buttons that need to be clicked, include detailed information such as their location, color, and shape.
When the user needs to click an icon on the desktop, instruct them to double-click it quickly.
When the task is complete, set is_done to True.
If the user asks a question that is not related to using the computer, set is_done to True.
"""

class ResponseFormat(BaseModel):
    step: int
    instruction: str
    is_done: bool

class Helper():
    def __init__(self):
        self.step = 0
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.buffer = BytesIO()
        self.history = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

    def get_request(self):
        request = recognize_speech_streaming()
        return request

    def first_instruction(self, query):

        encoded_screenshot = self.take_screenshot()

        response = self.client.responses.parse(
            model = "gpt-4o-2024-08-06",
            input = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": query},
                        {"type": "input_image", "image_url": f"data:image/png;base64,{encoded_screenshot}"}
                    ]
                }
            ],
            text_format = ResponseFormat
        )
        
        self.previous_response_id = response.id
        parsed_response = response.output_parsed
        print(parsed_response)
        return parsed_response

    def next_instruction(self, query="이 화면에서 뭘 해야해?"):

        encoded_screenshot = self.take_screenshot()

        response = self.client.responses.parse(
            model = "gpt-4o-2024-08-06",
            input = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": query},
                        {"type": "input_image", "image_url": f"data:image/png;base64,{encoded_screenshot}"}
                    ]
                }
            ],
            previous_response_id = self.previous_response_id,
            text_format = ResponseFormat
        )
        
        self.previous_response_id = response.id
        parsed_response = response.output_parsed
        print(parsed_response)
        return parsed_response

    def take_screenshot(self):
        screenshot = ImageGrab.grab()
        screenshot.save(self.buffer, format="PNG")
        self.buffer.seek(0)
        encoded_screenshot = base64.b64encode(self.buffer.getvalue()).decode("utf-8")
        return encoded_screenshot


