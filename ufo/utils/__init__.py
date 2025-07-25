# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import importlib
import functools
import json
import os
from typing import Optional, Any, Dict

from colorama import Fore, Style, init

# init colorama
init()


def print_with_color(text: str, color: str = "", end: str = "\n") -> None:
    """
    Print text with specified color using ANSI escape codes from Colorama library.

    :param text: The text to print.
    :param color: The color of the text (options: red, green, yellow, blue, magenta, cyan, white, black).
    """
    color_mapping = {
        "red": Fore.RED,
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "blue": Fore.BLUE,
        "magenta": Fore.MAGENTA,
        "cyan": Fore.CYAN,
        "white": Fore.WHITE,
        "black": Fore.BLACK,
    }

    selected_color = color_mapping.get(color.lower(), "")
    colored_text = selected_color + text + Style.RESET_ALL

    print(colored_text, end=end)


def create_folder(folder_path: str) -> None:
    """
    Create a folder if it doesn't exist.

    :param folder_path: The path of the folder to create.
    """
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)


def check_json_format(string: str) -> bool:
    """
    Check if the string can be correctly parse by json.
    :param string: The string to check.
    :return: True if the string can be correctly parse by json, False otherwise.
    """
    import json

    try:
        json.loads(string)
    except ValueError:
        return False
    return True


def json_parser(json_string: str) -> Dict[str, Any]:
    """
    Parse json string to json object.
    :param json_string: The json string to parse.
    :return: The json object.
    """

    # Remove the ```json and ``` at the beginning and end of the string if exists.
    if json_string.startswith("```json"):
        json_string = json_string[7:-3]

    return json.loads(json_string)


def is_json_serializable(obj: Any) -> bool:
    """
    Check if the object is json serializable.
    :param obj: The object to check.
    :return: True if the object is json serializable, False otherwise.
    """
    try:
        json.dumps(obj)
        return True
    except TypeError:
        return False


def revise_line_breaks(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace '\\n' with '\n' in the arguments.
    :param args: The arguments.
    :return: The arguments with \\n replaced with \n.
    """
    if not args:
        return {}

    # Replace \\n with \\n
    for key in args.keys():
        if isinstance(args[key], str):
            args[key] = args[key].replace("\\n", "\n")

    return args


def LazyImport(module_name: str) -> Any:
    """
    Import a module as a global variable.
    :param module_name: The name of the module to import.
    :return: The imported module.
    """
    global_name = module_name.split(".")[-1]
    globals()[global_name] = importlib.import_module(module_name, __package__)
    return globals()[global_name]


def find_desktop_path() -> Optional[str]:
    """
    Find the desktop path of the user.
    """
    onedrive_path = os.environ.get("OneDrive")
    if onedrive_path:
        onedrive_desktop = os.path.join(onedrive_path, "Desktop")
        if os.path.exists(onedrive_desktop):
            return onedrive_desktop
    # Fallback to the local user desktop
    local_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.exists(local_desktop):
        return local_desktop
    return None


def append_string_to_file(file_path: str, string: str) -> None:
    """
    Append a string to a file.
    :param file_path: The path of the file.
    :param string: The string to append.
    """

    # If the file doesn't exist, create it.
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as file:
            pass

    # Append the string to the file.
    with open(file_path, "a", encoding="utf-8") as file:
        file.write(string + "\n")


@functools.lru_cache(maxsize=5)
def get_hugginface_embedding(
    model_name: str = "sentence-transformers/all-mpnet-base-v2",
):
    """
    Get the Hugging Face embeddings.
    :param model_name: The name of the model.
    :return: The Hugging Face embeddings.
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=model_name)


from google.cloud import texttospeech
from datetime import datetime
import tempfile
import os


def speak_text(
    text: str,
    lang: str = "en-US",
    speaking_rate: float = 1.0,
    pitch: float = 0.0
) -> str:
    """Generate an English speech file using Google Cloud TTS, play it with pygame, delete it, and return the file path (default: en-US, Standard-B)."""
    try:
        client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        if lang == "ko-KR":
            voice_name = "ko-KR-Standard-C"
        else:
            voice_name = "en-US-Standard-D"
        voice = texttospeech.VoiceSelectionParams(
            language_code=lang,
            name=voice_name,
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=speaking_rate,
            pitch=pitch
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
                continue
            pygame.mixer.music.unload()  # Release file handle
        except Exception as e2:
            print(f"[TTS Playback Error] pygame: {e2}\n(Install with: pip install pygame)")
        # Delete the audio file after playback
        try:
            os.remove(file_name)
            print(f"🗑️ 음성 파일 삭제 완료: {file_name}")
        except Exception as e:
            print(f"[TTS File Delete Error] {e}")
        return file_name
    except Exception as e:
        print(f"[TTS Error] {e}")
        return None
