# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Type

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ufo.automator.basic import CommandBasic, ReceiverBasic
from ufo import utils


class SeleniumWebReceiver(ReceiverBasic):
    """
    Selenium-based web automation receiver for UFO.
    """

    _command_registry: Dict[str, Type[SeleniumWebCommand]] = {}

    def __init__(self) -> None:
        """
        Initialize the Selenium Web receiver.
        """
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self._setup_driver()

    def _setup_driver(self) -> None:
        """
        Setup Chrome driver with appropriate options.
        """
        try:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            # chrome_options.add_argument("--headless")  # Uncomment for headless mode
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)
            utils.print_with_color("Selenium WebDriver initialized successfully.", "green")
        except Exception as e:
            utils.print_with_color(f"Failed to initialize Selenium WebDriver: {e}", "red")
            raise

    def navigate_to_url(self, url: str) -> str:
        """
        Navigate to a specific URL.
        :param url: The URL to navigate to.
        :return: Success message or error.
        """
        try:
            self.driver.get(url)
            time.sleep(2)  # Wait for page to load
            return f"Successfully navigated to {url}"
        except Exception as e:
            return f"Failed to navigate to {url}: {e}"

    def get_page_source(self) -> str:
        """
        Get the current page's HTML source.
        :return: The HTML source of the current page.
        """
        try:
            return self.driver.page_source
        except Exception as e:
            return f"Failed to get page source: {e}"

    def get_page_title(self) -> str:
        """
        Get the current page's title.
        :return: The title of the current page.
        """
        try:
            return self.driver.title
        except Exception as e:
            return f"Failed to get page title: {e}"

    def find_element_by_text(self, text: str, element_type: str = "any") -> Dict[str, Any]:
        """
        Find an element by its text content.
        :param text: The text to search for.
        :param element_type: The type of element (button, link, input, etc.).
        :return: Element information or error message.
        """
        try:
            # Define selectors based on element type
            selectors = {
                "button": "//button[contains(text(), '{}')]",
                "link": "//a[contains(text(), '{}')]",
                "input": "//input[@placeholder='{}' or @value='{}']",
                "any": "//*[contains(text(), '{}')]"
            }
            
            xpath = selectors.get(element_type, selectors["any"]).format(text)
            element = self.wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            
            return {
                "found": True,
                "tag_name": element.tag_name,
                "text": element.text,
                "location": element.location,
                "size": element.size
            }
        except TimeoutException:
            return {"found": False, "error": f"Element with text '{text}' not found"}
        except Exception as e:
            return {"found": False, "error": str(e)}

    def click_element(self, text: str, element_type: str = "any") -> str:
        """
        Click an element by its text content.
        :param text: The text to search for.
        :param element_type: The type of element.
        :return: Success message or error.
        """
        try:
            selectors = {
                "button": "//button[contains(text(), '{}')]",
                "link": "//a[contains(text(), '{}')]",
                "any": "//*[contains(text(), '{}')]"
            }
            
            xpath = selectors.get(element_type, selectors["any"]).format(text)
            element = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            element.click()
            time.sleep(1)
            return f"Successfully clicked element with text '{text}'"
        except TimeoutException:
            return f"Element with text '{text}' not found or not clickable"
        except Exception as e:
            return f"Failed to click element: {e}"

    def input_text(self, text: str, input_selector: str, clear_first: bool = True) -> str:
        """
        Input text into a form field.
        :param text: The text to input.
        :param input_selector: CSS selector or XPath for the input field.
        :param clear_first: Whether to clear the field first.
        :return: Success message or error.
        """
        try:
            if input_selector.startswith("//"):
                element = self.wait.until(EC.presence_of_element_located((By.XPATH, input_selector)))
            else:
                element = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, input_selector)))
            
            if clear_first:
                element.clear()
            
            element.send_keys(text)
            time.sleep(0.5)
            return f"Successfully input text '{text}'"
        except TimeoutException:
            return f"Input field with selector '{input_selector}' not found"
        except Exception as e:
            return f"Failed to input text: {e}"

    def get_all_clickable_elements(self) -> List[Dict[str, Any]]:
        """
        Get all clickable elements on the current page.
        :return: List of clickable elements with their information.
        """
        try:
            elements = []
            
            # Find buttons
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for button in buttons:
                if button.is_displayed() and button.is_enabled():
                    elements.append({
                        "type": "button",
                        "text": button.text,
                        "tag_name": button.tag_name,
                        "location": button.location,
                        "size": button.size
                    })
            
            # Find links
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                if link.is_displayed() and link.is_enabled():
                    elements.append({
                        "type": "link",
                        "text": link.text,
                        "tag_name": link.tag_name,
                        "location": link.location,
                        "size": link.size
                    })
            
            # Find input fields
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            for input_elem in inputs:
                if input_elem.is_displayed():
                    elements.append({
                        "type": "input",
                        "text": input_elem.get_attribute("placeholder") or input_elem.get_attribute("value") or "",
                        "tag_name": input_elem.tag_name,
                        "input_type": input_elem.get_attribute("type"),
                        "location": input_elem.location,
                        "size": input_elem.size
                    })
            
            return elements
        except Exception as e:
            return [{"error": f"Failed to get elements: {e}"}]

    def take_screenshot(self, save_path: str = None) -> str:
        """
        Take a screenshot of the current page.
        :param save_path: Path to save the screenshot.
        :return: Success message or error.
        """
        try:
            if save_path:
                self.driver.save_screenshot(save_path)
                return f"Screenshot saved to {save_path}"
            else:
                return "Screenshot taken successfully"
        except Exception as e:
            return f"Failed to take screenshot: {e}"

    def close_driver(self) -> None:
        """
        Close the WebDriver.
        """
        if self.driver:
            self.driver.quit()

    @property
    def type_name(self):
        return "SELENIUM_WEB"

    @property
    def xml_format_code(self) -> int:
        return 0


class SeleniumWebCommand(CommandBasic):
    """
    Base class for Selenium web commands.
    """

    def __init__(self, receiver: SeleniumWebReceiver, params: Dict[str, Any]):
        super().__init__(receiver, params)


@SeleniumWebReceiver.register
class NavigateToUrlCommand(SeleniumWebCommand):
    """
    Command to navigate to a URL.
    """

    def execute(self) -> str:
        """
        Execute the navigation command.
        :return: The result of the navigation.
        """
        url = self.params.get("url", "")
        return self.receiver.navigate_to_url(url)

    @classmethod
    def name(cls) -> str:
        """
        Get the name of the command.
        :return: The command name.
        """
        return "navigate_to_url"


@SeleniumWebReceiver.register
class ClickElementCommand(SeleniumWebCommand):
    """
    Command to click an element.
    """

    def execute(self) -> str:
        """
        Execute the click command.
        :return: The result of the click action.
        """
        text = self.params.get("text", "")
        element_type = self.params.get("element_type", "any")
        return self.receiver.click_element(text, element_type)

    @classmethod
    def name(cls) -> str:
        """
        Get the name of the command.
        :return: The command name.
        """
        return "click_element"


@SeleniumWebReceiver.register
class InputTextCommand(SeleniumWebCommand):
    """
    Command to input text.
    """

    def execute(self) -> str:
        """
        Execute the input text command.
        :return: The result of the input action.
        """
        text = self.params.get("text", "")
        selector = self.params.get("selector", "")
        clear_first = self.params.get("clear_first", True)
        return self.receiver.input_text(text, selector, clear_first)

    @classmethod
    def name(cls) -> str:
        """
        Get the name of the command.
        :return: The command name.
        """
        return "input_text"


@SeleniumWebReceiver.register
class GetPageSourceCommand(SeleniumWebCommand):
    """
    Command to get page source.
    """

    def execute(self) -> str:
        """
        Execute the get page source command.
        :return: The page source.
        """
        return self.receiver.get_page_source()

    @classmethod
    def name(cls) -> str:
        """
        Get the name of the command.
        :return: The command name.
        """
        return "get_page_source"


@SeleniumWebReceiver.register
class GetClickableElementsCommand(SeleniumWebCommand):
    """
    Command to get all clickable elements.
    """

    def execute(self) -> str:
        """
        Execute the get elements command.
        :return: JSON string of clickable elements.
        """
        import json
        elements = self.receiver.get_all_clickable_elements()
        return json.dumps(elements, indent=2)

    @classmethod
    def name(cls) -> str:
        """
        Get the name of the command.
        :return: The command name.
        """
        return "get_clickable_elements" 