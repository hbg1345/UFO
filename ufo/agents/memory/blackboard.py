# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from ufo.agents.memory.memory import Memory, MemoryItem
from ufo.automator.ui_control.screenshot import PhotographerFacade
from ufo.config.config import Config

configs = Config.get_instance().config_data


@dataclass
class ImageMemoryItemNames:
    """
    The variables for the image memory item.
    """

    METADATA: str = "metadata"
    IMAGE_PATH: str = "image_path"
    IMAGE_STR: str = "image_str"


@dataclass
class ImageMemoryItem(MemoryItem):
    """
    The class for the image memory item.
    """

    _memory_attributes = list(ImageMemoryItemNames.__annotations__.keys())


class Blackboard:
    """
    Class for the blackboard, which stores the data and images which are visible to all the agents.
    """

    def __init__(self) -> None:
        """
        Initialize the blackboard.
        """
        self._questions: Memory = Memory()
        self._requests: Memory = Memory()
        self._trajectories: Memory = Memory()
        self._screenshots: Memory = Memory()

        if configs.get("USE_CUSTOMIZATION", False):
            self.load_questions(
                configs.get("QA_PAIR_FILE", ""), configs.get("QA_PAIR_NUM", -1)
            )

    @property
    def questions(self) -> Memory:
        """
        Get the data from the blackboard.
        :return: The questions from the blackboard.
        """
        return self._questions

    @property
    def requests(self) -> Memory:
        """
        Get the data from the blackboard.
        :return: The requests from the blackboard.
        """
        return self._requests

    @property
    def trajectories(self) -> Memory:
        """
        Get the data from the blackboard.
        :return: The trajectories from the blackboard.
        """
        return self._trajectories

    @property
    def screenshots(self) -> Memory:
        """
        Get the images from the blackboard.
        :return: The images from the blackboard.
        """
        return self._screenshots

    def add_data(
        self, data: Union[MemoryItem, Dict[str, str], str], memory: Memory
    ) -> None:
        """
        Add the data to the a memory in the blackboard.
        :param data: The data to be added. It can be a dictionary or a MemoryItem or a string.
        :param memory: The memory to add the data to.
        """

        if isinstance(data, dict):
            data_memory = MemoryItem()
            data_memory.add_values_from_dict(data)
            memory.add_memory_item(data_memory)
        elif isinstance(data, MemoryItem):
            memory.add_memory_item(data)
        elif isinstance(data, str):
            data_memory = MemoryItem()
            data_memory.add_values_from_dict({"text": data})
            memory.add_memory_item(data_memory)
        else:
            print(f"Warning: Unsupported data type: {type(data)} when adding data.")

    def add_questions(self, questions: Union[MemoryItem, Dict[str, str]]) -> None:
        """
        Add the data to the blackboard.
        :param questions: The data to be added. It can be a dictionary or a MemoryItem or a string.
        """

        self.add_data(questions, self.questions)

    def add_requests(self, requests: Union[MemoryItem, Dict[str, str]]) -> None:
        """
        Add the data to the blackboard.
        :param requests: The data to be added. It can be a dictionary or a MemoryItem or a string.
        """

        self.add_data(requests, self.requests)

    def add_trajectories(self, trajectories: Union[MemoryItem, Dict[str, str]]) -> None:
        """
        Add the data to the blackboard.
        :param trajectories: The data to be added. It can be a dictionary or a MemoryItem or a string.
        """

        self.add_data(trajectories, self.trajectories)

    def add_image(
        self,
        screenshot_path: str = "",
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Add the image to the blackboard.
        :param screenshot_path: The path of the image.
        :param metadata: The metadata of the image.
        """

        if os.path.exists(screenshot_path):

            screenshot_str = PhotographerFacade().encode_image_from_path(
                screenshot_path
            )
        else:
            print(f"Screenshot path {screenshot_path} does not exist.")
            screenshot_str = ""

        image_memory_item = ImageMemoryItem()
        image_memory_item.add_values_from_dict(
            {
                ImageMemoryItemNames.METADATA: metadata.get(
                    ImageMemoryItemNames.METADATA
                ),
                ImageMemoryItemNames.IMAGE_PATH: screenshot_path,
                ImageMemoryItemNames.IMAGE_STR: screenshot_str,
            }
        )

        self.screenshots.add_memory_item(image_memory_item)

    def questions_to_json(self) -> str:
        """
        Convert the data to a dictionary.
        :return: The data in the dictionary format.
        """
        return self.questions.to_json()

    def requests_to_json(self) -> str:
        """
        Convert the data to a dictionary.
        :return: The data in the dictionary format.
        """
        return self.requests.to_json()

    def trajectories_to_json(self) -> str:
        """
        Convert the data to a dictionary.
        :return: The data in the dictionary format.
        """
        return self.trajectories.to_json()

    def screenshots_to_json(self) -> str:
        """
        Convert the images to a dictionary.
        :return: The images in the dictionary format.
        """
        return self.screenshots.to_json()

    def load_questions(self, file_path: str, last_k=-1) -> None:
        """
        Load the data from a file.
        :param file_path: The path of the file.
        :param last_k: The number of lines to read from the end of the file. If -1, read all lines.
        """
        qa_list = self.read_json_file(file_path, last_k)
        for qa in qa_list:
            self.add_questions(qa)

    def texts_to_prompt(self, memory: Memory, prefix: str, max_items: int = 2) -> List[str]:
        """
        Convert the data to a prompt with limited items to reduce context usage.
        :param memory: The memory to convert.
        :param prefix: The prefix for the prompt.
        :param max_items: Maximum number of items to include (default: 2).
        :return: The prompt.
        """
        # Limit the number of items to reduce context usage
        if len(memory.list_content) > max_items:
            recent_content = memory.list_content[-max_items:]
        else:
            recent_content = memory.list_content

        user_content = [
            {"type": "text", "text": f"{prefix}\n {json.dumps(recent_content)}"}
        ]

        return user_content

    def screenshots_to_prompt(self, max_screenshots: int = 2) -> List[str]:
        """
        Convert the images to a prompt with limited screenshots to reduce context usage.
        :param max_screenshots: Maximum number of screenshots to include (default: 2).
        :return: The prompt.
        """
        user_content = []
        
        # Limit the number of screenshots to reduce context usage
        if len(self.screenshots.list_content) > max_screenshots:
            recent_screenshots = self.screenshots.list_content[-max_screenshots:]
        else:
            recent_screenshots = self.screenshots.list_content
            
        for screenshot_dict in recent_screenshots:
            user_content.append(
                {
                    "type": "text",
                    "text": json.dumps(
                        screenshot_dict.get(ImageMemoryItemNames.METADATA, "")
                    ),
                }
            )
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": screenshot_dict.get(ImageMemoryItemNames.IMAGE_STR, "")
                    },
                }
            )

        return user_content

    def blackboard_to_dict(self) -> Dict[str, List[Dict[str, str]]]:
        """
        Convert the blackboard to a dictionary.
        :return: The blackboard in the dictionary format.
        """
        blackboard_dict = {
            "questions": self.questions.to_list_of_dicts(),
            "requests": self.requests.to_list_of_dicts(),
            "trajectories": self.trajectories.to_list_of_dicts(),
            "screenshots": self.screenshots.to_list_of_dicts(),
        }

        return blackboard_dict

    def blackboard_to_json(self) -> str:
        """
        Convert the blackboard to a JSON string.
        :return: The JSON string.
        """
        return json.dumps(self.blackboard_to_dict())

    def blackboard_from_dict(
        self, blackboard_dict: Dict[str, List[Dict[str, str]]]
    ) -> None:
        """
        Convert the dictionary to the blackboard.
        :param blackboard_dict: The dictionary.
        """
        self.questions.from_list_of_dicts(blackboard_dict.get("questions", []))
        self.requests.from_list_of_dicts(blackboard_dict.get("requests", []))
        self.trajectories.from_list_of_dicts(blackboard_dict.get("trajectories", []))
        self.screenshots.from_list_of_dicts(blackboard_dict.get("screenshots", []))

    def blackboard_to_prompt(self) -> List[str]:
        """
        Convert the blackboard to a prompt.
        :return: The prompt.
        """
        prefix = [
            {
                "type": "text",
                "text": "[Blackboard:]",
            }
        ]

        blackboard_prompt = (
            prefix
            + self.texts_to_prompt(self.questions, "[Questions & Answers:]")
            + self.texts_to_prompt(self.requests, "[Request History:]")
            + self.texts_to_prompt(
                self.trajectories, "[Step Trajectories Completed Previously:]"
            )
            + self.screenshots_to_prompt()
        )

        return blackboard_prompt

    def is_empty(self) -> bool:
        """
        Check if the blackboard is empty.
        :return: True if the blackboard is empty, False otherwise.
        """
        return (
            self.questions.is_empty()
            and self.requests.is_empty()
            and self.trajectories.is_empty()
            and self.screenshots.is_empty()
        )

    def clear(self) -> None:
        """
        Clear the blackboard.
        """
        self.questions.clear()
        self.requests.clear()
        self.trajectories.clear()
        self.screenshots.clear()

    def cleanup_old_data(self, keep_recent_trajectories: int = 2, keep_recent_screenshots: int = 2) -> None:
        """
        Clean up old data to reduce memory usage and context size.
        :param keep_recent_trajectories: Number of recent trajectories to keep (default: 2).
        :param keep_recent_screenshots: Number of recent screenshots to keep (default: 2).
        """
        # Clean up old trajectories
        if len(self.trajectories.list_content) > keep_recent_trajectories:
            recent_trajectories = self.trajectories.list_content[-keep_recent_trajectories:]
            self.trajectories.from_list_of_dicts(recent_trajectories)
            print(f"Cleaned up trajectories: kept {keep_recent_trajectories} recent items")
        
        # Clean up old screenshots
        if len(self.screenshots.list_content) > keep_recent_screenshots:
            recent_screenshots = self.screenshots.list_content[-keep_recent_screenshots:]
            self.screenshots.from_list_of_dicts(recent_screenshots)
            print(f"Cleaned up screenshots: kept {keep_recent_screenshots} recent items")
        
        # Clean up old requests (keep only recent 2)
        if len(self.requests.list_content) > 2:
            recent_requests = self.requests.list_content[-2:]
            self.requests.from_list_of_dicts(recent_requests)
            print("Cleaned up requests: kept 2 recent items")

    @staticmethod
    def read_json_file(file_path: str, last_k=-1) -> Dict[str, str]:
        """
        Read the json file.
        :param file_path: The path of the file.
        :param last_k: The number of lines to read from the end of the file. If -1, read all lines.
        :return: The data in the file.
        """

        data_list = []

        # Check if the file exists
        if os.path.exists(file_path):
            # Open the file and read the lines
            with open(file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

            # If last_k is not -1, only read the last k lines
            if last_k != -1:
                lines = lines[-last_k:]

            # Parse the lines as JSON
            for line in lines:
                try:
                    data = json.loads(line.strip())
                    data_list.append(data)
                except json.JSONDecodeError:
                    print(f"Warning: Unable to parse line as JSON: {line}")

        return data_list


if __name__ == "__main__":

    blackboard = Blackboard()
    blackboard.add_data({"key1": "value1", "key2": "value2"})
    print(blackboard.blackboard_to_prompt())
