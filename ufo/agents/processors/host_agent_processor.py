# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.


import json
import time
import re
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Dict, List

from pywinauto.controls.uiawrapper import UIAWrapper

from ufo import utils
from ufo.agents.processors.actions import (
    ActionExecutionLog,
    ActionSequence,
    BaseControlLog,
    OneStepAction,
)
from ufo.agents.processors.basic import BaseProcessor
from ufo.config.config import Config
from ufo.module.context import Context, ContextNames

configs = Config.get_instance().config_data


if TYPE_CHECKING:
    from ufo.agents.agent.host_agent import HostAgent


@dataclass
class HostAgentAdditionalMemory:
    """
    The additional memory for the host agent.
    """

    Step: int
    RoundStep: int
    AgentStep: int
    Round: int
    ControlLabel: str
    SubtaskIndex: int
    Action: str
    FunctionCall: str
    ActionType: str
    Request: str
    Agent: str
    AgentName: str
    Application: str
    Cost: float
    Results: str
    error: str
    time_cost: Dict[str, float]
    ControlLog: Dict[str, Any]


@dataclass
class HostAgentRequestLog:
    """
    The request log data for the AppAgent.
    """

    step: int
    image_list: List[str]
    os_info: Dict[str, str]
    plan: List[str]
    prev_subtask: List[str]
    request: str
    blackboard_prompt: List[str]
    prompt: Dict[str, Any]


class HostAgentProcessor(BaseProcessor):
    """
    The processor for the host agent at a single step.
    """

    def __init__(self, agent: "HostAgent", context: Context) -> None:
        """
        Initialize the host agent processor.
        :param agent: The host agent to be processed.
        :param context: The context.
        """

        super().__init__(agent=agent, context=context)

        self.host_agent = agent

        self._desktop_screen_url = None
        self._desktop_windows_dict = None
        self._desktop_windows_info = None
        self.bash_command = None
        
        # Web automation related attributes
        self._is_web_request = False
        self._selenium_receiver = None
        self._web_plan = []

    def _extract_url_from_request(self, user_request: str) -> str:
        """
        Extract URL from user request.
        :param user_request: The user's request.
        :return: Extracted URL or empty string.
        """
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, user_request)
        return urls[0] if urls else ""

    def _create_selenium_receiver(self) -> None:
        """
        Create Selenium Web receiver for web automation.
        """
        try:
            from ufo.automator.app_apis.web.selenium_webclient import SeleniumWebReceiver
            self._selenium_receiver = SeleniumWebReceiver()
            utils.print_with_color("Selenium Web receiver created successfully.", "green")
        except Exception as e:
            utils.print_with_color(f"Failed to create Selenium receiver: {e}", "red")
            self._selenium_receiver = None

    def _get_web_page_info(self, url: str = None) -> Dict[str, Any]:
        """
        Get information about the current web page.
        :param url: URL to navigate to (optional).
        :return: Dictionary containing page information.
        """
        if not self._selenium_receiver:
            return {"error": "Selenium receiver not available"}
        
        try:
            if url:
                self._selenium_receiver.navigate_to_url(url)
            
            page_info = {
                "title": self._selenium_receiver.get_page_title(),
                "url": self._selenium_receiver.driver.current_url if self._selenium_receiver.driver else "",
                "elements": self._selenium_receiver.get_all_clickable_elements()
            }
            
            return page_info
        except Exception as e:
            return {"error": f"Failed to get page info: {e}"}

    def _create_web_plan(self, user_request: str, page_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create a plan for web automation based on user request and page info.
        :param user_request: The user's request.
        :param page_info: Information about the current web page.
        :return: List of planned actions in function call format.
        """
        plan = []
        
        # Extract search terms from user request
        search_terms = []
        if "검색" in user_request:
            # Extract Korean search terms
            import re
            korean_pattern = r'["""]([가-힣\s]+)["""]'
            search_terms = re.findall(korean_pattern, user_request)
        
        # Basic web automation plan based on common patterns
        if "검색" in user_request or "search" in user_request.lower():
            # Navigate to appropriate search engine
            if "네이버" in user_request or "naver" in user_request.lower():
                plan.append({"function": "navigate_to_url", "args": {"url": "https://www.naver.com"}})
            elif "구글" in user_request or "google" in user_request.lower():
                plan.append({"function": "navigate_to_url", "args": {"url": "https://www.google.com"}})
            else:
                # Default to Google
                plan.append({"function": "navigate_to_url", "args": {"url": "https://www.google.com"}})
            
            # Add search input if search terms found
            if search_terms:
                search_term = search_terms[0].strip()
                plan.append({"function": "input_text", "args": {"text": search_term, "selector": "검색창"}})
                plan.append({"function": "click_element", "args": {"text": "검색", "element_type": "button"}})
            else:
                # Generic search plan
                plan.append({"function": "input_text", "args": {"text": "검색어", "selector": "검색창"}})
                plan.append({"function": "click_element", "args": {"text": "검색", "element_type": "button"}})
                
        elif "클릭" in user_request or "click" in user_request.lower():
            plan.append({"function": "get_clickable_elements", "args": {}})
            plan.append({"function": "click_element", "args": {"text": "클릭할요소", "element_type": "any"}})
            
        elif "입력" in user_request or "input" in user_request.lower():
            plan.append({"function": "input_text", "args": {"text": "입력할텍스트", "selector": "입력필드"}})
            
        else:
            # Generic web automation plan
            plan.append({"function": "get_page_source", "args": {}})
            plan.append({"function": "get_clickable_elements", "args": {}})
        
        return plan

    def _detect_web_request_from_llm_response(self, response_text: str) -> bool:
        """
        Detect if the LLM response indicates a web-related request.
        :param response_text: The LLM's response text.
        :return: True if web-related, False otherwise.
        """
        web_indicators = [
            '웹', '웹사이트', '웹페이지', '브라우저', '인터넷', '사이트', '페이지',
            'http://', 'https://', 'www.', '.com', '.org', '.net', '.kr',
            '검색', '클릭', '버튼', '링크', '폼', '입력', '제출',
            'web', 'website', 'browser', 'internet', 'site', 'page',
            'search', 'click', 'button', 'link', 'form', 'input', 'submit',
            'selenium', '웹 자동화', 'web automation'
        ]
        
        response_lower = response_text.lower()
        
        # 디버깅을 위해 매칭된 키워드 찾기
        matched_indicators = []
        for indicator in web_indicators:
            if indicator in response_lower:
                matched_indicators.append(indicator)
        
        if matched_indicators:
            utils.print_with_color(f"웹 요청으로 판단된 키워드: {matched_indicators}", "yellow")
            utils.print_with_color(f"검색된 텍스트: {response_text[:200]}...", "cyan")
        
        return len(matched_indicators) > 0

    def print_step_info(self) -> None:
        """
        Print the step information.
        """
        utils.print_with_color(
            "Round {round_num}, Step {step}, HostAgent: Analyzing the user intent and decomposing the request...".format(
                round_num=self.round_num + 1, step=self.round_step + 1
            ),
            "cyan",
        )

    @BaseProcessor.exception_capture
    @BaseProcessor.method_timer
    def capture_screenshot(self) -> None:
        """
        Capture the screenshot.
        """

        desktop_save_path = self.log_path + f"action_step{self.session_step}.png"

        self._memory_data.add_values_from_dict({"CleanScreenshot": desktop_save_path})

        # Capture the desktop screenshot for all screens.
        self.photographer.capture_desktop_screen_screenshot(
            all_screens=True, save_path=desktop_save_path
        )

        # Encode the desktop screenshot into base64 format as required by the LLM.
        self._desktop_screen_url = self.photographer.encode_image_from_path(
            desktop_save_path
        )

    @BaseProcessor.exception_capture
    @BaseProcessor.method_timer
    def get_control_info(self) -> None:
        """
        Get the control information.
        """

        # Get all available windows on the desktop, into a dictionary with format {index: application object}.
        self._desktop_windows_dict = self.control_inspector.get_desktop_app_dict(
            remove_empty=True
        )

        # Get the textual information of all windows.
        self._desktop_windows_info = self.control_inspector.get_desktop_app_info(
            self._desktop_windows_dict
        )

    @BaseProcessor.exception_capture
    @BaseProcessor.method_timer
    def get_prompt_message(self) -> None:
        """
        Get the prompt message.
        """

        if not self.host_agent.blackboard.is_empty():
            blackboard_prompt = self.host_agent.blackboard.blackboard_to_prompt()
        else:
            blackboard_prompt = []

        # Construct the prompt message for the host agent.
        self._prompt_message = self.host_agent.message_constructor(
            image_list=[self._desktop_screen_url],
            os_info=self._desktop_windows_info,
            plan=self.prev_plan,
            prev_subtask=self.previous_subtasks,
            request=self.request,
            blackboard_prompt=blackboard_prompt,
            html_source=getattr(self, 'html_source', ''),
            selenium_status=getattr(self, 'selenium_status', ''),
        )

        request_data = HostAgentRequestLog(
            step=self.session_step,
            image_list=[self._desktop_screen_url],
            os_info=self._desktop_windows_info,
            plan=self.prev_plan,
            prev_subtask=self.previous_subtasks,
            request=self.request,
            blackboard_prompt=blackboard_prompt,
            prompt=self._prompt_message,
        )

        # Log the prompt message. Only save them in debug mode.
        request_log_str = json.dumps(asdict(request_data), ensure_ascii=False)
        self.request_logger.debug(request_log_str)

    @BaseProcessor.exception_capture
    @BaseProcessor.method_timer
    def get_response(self) -> None:
        """
        Get the response from the LLM.
        """

        retry = 0
        while retry < configs.get("JSON_PARSING_RETRY", 3):
            # Try to get the response from the LLM. If an error occurs, catch the exception and log the error.
            self._response, self.cost = self.host_agent.get_response(
                self._prompt_message, "HOSTAGENT", use_backup_engine=True
            )

            try:
                self.host_agent.response_to_dict(self._response)
                break
            except Exception as e:
                print(f"Error in parsing response into json, retrying: {retry}")
                retry += 1

    @BaseProcessor.exception_capture
    @BaseProcessor.method_timer
    def parse_response(self) -> None:
        """
        Parse the response.
        """
        self._response_json = self.host_agent.response_to_dict(self._response)

        # Debug: Print the raw response JSON
        utils.print_with_color(f"Raw response JSON: {self._response_json}", "magenta")

        # New simplified response format
        self.observation = self._response_json.get("Observation", "")
        self.thought = self._response_json.get("Thought", "")
        self.response = self._response_json.get("Response", "")
        self.comment = self._response_json.get("Comment", "")
        self.web_automation = self._response_json.get("WebAutomation", False)
        self.web_plan = self._response_json.get("WebPlan", [])

        # Debug: Print parsed web automation fields
        utils.print_with_color(f"Parsed WebAutomation: {self.web_automation}", "yellow")
        utils.print_with_color(f"Parsed WebPlan: {self.web_plan}", "yellow")
        utils.print_with_color(f"WebPlan type: {type(self.web_plan)}", "yellow")

        # Keep some fields for backward compatibility but they won't be used for AppAgent assignment
        self.control_label = self._response_json.get("ControlLabel", "")
        self.control_text = self._response_json.get("ControlText", "")
        self.subtask = self._response_json.get("CurrentSubtask", "")
        self.host_message = self._response_json.get("Message", [])

        # Convert the plan from a string to a list if the plan is a string.
        self.plan = self.string2list(self._response_json.get("Plan", ""))
        self._response_json["Plan"] = self.plan

        self.question_list = self._response_json.get("Questions", [])
        self.bash_command = self._response_json.get("Bash", None)

        # Use LLM's WebAutomation field instead of keyword-based detection
        self._is_web_request = self.web_automation
        
        if self._is_web_request:
            utils.print_with_color("LLM이 웹 자동화가 필요하다고 판단했습니다.", "yellow")
            
            # Check if WebPlan is provided when WebAutomation is true
            if not self.web_plan or not isinstance(self.web_plan, list) or len(self.web_plan) == 0:
                error_msg = f"웹 자동화가 필요하다고 판단되었지만 WebPlan이 제공되지 않았습니다. WebPlan: {self.web_plan}"
                utils.print_with_color(error_msg, "red")
                raise ValueError(error_msg)
            
            # Create Selenium receiver if not exists
            if not self._selenium_receiver:
                self._create_selenium_receiver()
            
            # Check Selenium status
            selenium_status = "Not running"
            if self._selenium_receiver and self._selenium_receiver.driver:
                try:
                    current_url = self._selenium_receiver.driver.current_url
                    selenium_status = f"Running - Current URL: {current_url}"
                    utils.print_with_color(f"Selenium 상태: {selenium_status}", "green")
                except Exception as e:
                    selenium_status = f"Error - {str(e)}"
                    utils.print_with_color(f"Selenium 상태: {selenium_status}", "yellow")
            else:
                utils.print_with_color("Selenium이 실행되지 않았습니다.", "yellow")
            
            # Extract URL and get page info
            user_request = self.context.get(ContextNames.REQUEST)
            url = self._extract_url_from_request(user_request)
            page_info = self._get_web_page_info(url)
            
            # Get HTML source if available
            html_source = ""
            if self._selenium_receiver and self._selenium_receiver.driver:
                try:
                    html_source = self._selenium_receiver.get_page_source()
                    utils.print_with_color("HTML 소스를 성공적으로 가져왔습니다.", "green")
                except Exception as e:
                    utils.print_with_color(f"HTML 소스 가져오기 실패: {e}", "yellow")
            
            # Use LLM's WebPlan
            self._web_plan = self.web_plan
            utils.print_with_color("LLM의 WebPlan을 사용합니다.", "green")
            utils.print_with_color(f"WebPlan: {self._web_plan}", "cyan")
            
            # Update the response with web-specific information
            if page_info.get("title"):
                self.response += f"\n\n현재 페이지: {page_info['title']}"
            
            if page_info.get("elements"):
                element_count = len(page_info["elements"])
                self.response += f"\n발견된 클릭 가능한 요소: {element_count}개"
            
            # Store HTML source and Selenium status for AppAgent
            self.html_source = html_source
            self.selenium_status = selenium_status

        # Print the response to user
        self._print_user_response()

        # Handle Status field for session control
        status_from_llm = self._response_json.get("Status", "").upper()
        if status_from_llm == "FINISH":
            utils.print_with_color("LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
            self.status = self._agent_status_manager.FINISH.value
        elif status_from_llm == "CONTINUE":
            self.status = self._agent_status_manager.CONTINUE.value

    @BaseProcessor.exception_capture
    @BaseProcessor.method_timer
    def execute_action(self) -> None:
        """
        Execute the action.
        """
        # If not a web request, just continue without executing any action
        if not self._is_web_request:
            utils.print_with_color("웹 요청이 아니므로 액션 실행을 건너뜁니다.", "cyan")
            self.status = self._agent_status_manager.CONTINUE.value
            return

        # For web requests, create AppAgent and pass the web automation plan
        utils.print_with_color("웹 자동화를 위해 AppAgent를 생성하고 계획을 전달합니다.", "green")
        
        # Create AppAgent for web automation
        from ufo.agents.agent.app_agent import AppAgent
        from ufo.agents.processors.app_agent_processor import AppAgentProcessor
        
        # Create AppAgent instance with correct parameters
        app_agent = AppAgent(
            name="WebAppAgent",
            process_name="web_browser",
            app_root_name="web_browser",
            is_visual=configs["APP_AGENT"]["VISUAL_MODE"],
            main_prompt=configs["APPAGENT_PROMPT"],
            example_prompt=configs["APPAGENT_EXAMPLE_PROMPT"],
            api_prompt=configs["API_PROMPT"],
            mode="normal"
        )
        
        # Set the host for the AppAgent
        app_agent.host = self.host_agent
        
        # Create AppAgent processor
        app_processor = AppAgentProcessor(
            agent=app_agent,
            context=self.context
        )
        
        # Set up web automation plan from HostAgent's WebPlan
        app_processor.subtask = "웹 자동화 실행"
        app_processor.plan = self._web_plan  # Use the actual web plan (LLM's or backup)
        
        # Pass HTML source to AppAgent if available
        if hasattr(self, 'html_source') and self.html_source:
            app_processor.html_source = self.html_source
            utils.print_with_color("HTML 소스를 AppAgent에게 전달했습니다.", "cyan")
        
        # Instead of using the normal process flow, directly execute the web plan
        execution_results = []  # Store execution results for feedback
        
        # Import required Selenium modules
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        
        while True:
            try:
                # Use existing Selenium receiver instead of creating a new one
                if not self._selenium_receiver:
                    utils.print_with_color("Selenium receiver가 없습니다. 새로 생성합니다.", "yellow")
                    self._create_selenium_receiver()
                
                utils.print_with_color("HostAgent의 웹 자동화 계획을 직접 실행합니다.", "green")
                utils.print_with_color(f"실행할 웹 계획: {self._web_plan}", "cyan")
                
                # Execute each step in the web plan
                for i, step in enumerate(self._web_plan):
                    utils.print_with_color(f"단계 {i+1} 실행 중...", "cyan")
                    
                    if isinstance(step, dict) and 'function' in step and 'args' in step:
                        function = step['function']
                        args = step['args']
                        
                        utils.print_with_color(f"단계 {i+1}: {function} 실행 (args: {args})", "cyan")
                        
                        step_result = {
                            'step': i + 1,
                            'function': function,
                            'args': args,
                            'success': False,
                            'result': '',
                            'error': ''
                        }
                        
                        # Execute the web action using the existing Selenium receiver
                        try:
                            if function == "navigate_to_url":
                                url = args.get("url", "")
                                utils.print_with_color(f"URL로 이동: {url}", "green")
                                result = self._selenium_receiver.navigate_to_url(url)
                                utils.print_with_color(f"네비게이션 결과: {result}", "cyan")
                                step_result['success'] = True
                                step_result['result'] = result
                                
                            elif function == "click_element":
                                text = args.get("text", "")
                                element_type = args.get("element_type", "any")
                                selector = args.get("selector", "")
                                
                                if selector:
                                    utils.print_with_color(f"요소 클릭 (selector): {selector}", "green")
                                    selectors = [s.strip() for s in selector.split(',')]
                                    clicked = False
                                    last_error = ''
                                    for sel in selectors:
                                        if ':contains' in sel:
                                            continue  # Selenium 미지원, 건너뜀
                                        try:
                                            if sel.startswith("//"):
                                                element = self._selenium_receiver.wait.until(
                                                    EC.element_to_be_clickable((By.XPATH, sel))
                                                )
                                            else:
                                                element = self._selenium_receiver.wait.until(
                                                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                                                )
                                            element.click()
                                            result = f"Successfully clicked element with selector '{sel}'"
                                            utils.print_with_color(f"클릭 결과: {result}", "cyan")
                                            clicked = True
                                            break
                                        except Exception as e:
                                            last_error = str(e)
                                    if not clicked:
                                        result = f"Failed to click any selector. Last error: {last_error}"
                                        utils.print_with_color(f"클릭 실패: {result}", "red")
                                else:
                                    utils.print_with_color(f"요소 클릭: {text} ({element_type})", "green")
                                    result = self._selenium_receiver.click_element(text, element_type)
                                    utils.print_with_color(f"클릭 결과: {result}", "cyan")
                                
                                # Check if click was successful
                                if "not found" in result or "not clickable" in result or "Failed" in result:
                                    utils.print_with_color(f"수정된 계획의 클릭 실패: {result}", "red")
                                    
                                    # Get current page information for plan modification
                                    current_page_info = self._get_current_page_info()
                                    
                                    # Create step result for feedback
                                    failed_step = {
                                        'step': i + 1,
                                        'function': function,
                                        'args': args,
                                        'success': False,
                                        'error': result,
                                        'page_info': current_page_info
                                    }
                                    
                                    # Send feedback to HostAgent for plan modification
                                    self._request_plan_modification([], failed_step, current_page_info)
                                    break  # Stop execution and wait for new plan
                                
                            elif function == "input_text":
                                text = args.get("text", "")
                                selector = args.get("selector", "")
                                clear_first = args.get("clear_first", True)
                                utils.print_with_color(f"텍스트 입력: {text} (selector: {selector})", "green")
                                result = self._selenium_receiver.input_text(text, selector, clear_first)
                                utils.print_with_color(f"텍스트 입력 결과: {result}", "cyan")
                                
                                # Check if input was successful
                                if "not found" in result or "failed" in result or "Failed" in result:
                                    utils.print_with_color(f"수정된 계획의 텍스트 입력 실패: {result}", "red")
                                    
                                    # Get current page information for plan modification
                                    current_page_info = self._get_current_page_info()
                                    
                                    # Create step result for feedback
                                    failed_step = {
                                        'step': i + 1,
                                        'function': function,
                                        'args': args,
                                        'success': False,
                                        'error': result,
                                        'page_info': current_page_info
                                    }
                                    
                                    # Send feedback to HostAgent for plan modification
                                    self._request_plan_modification([], failed_step, current_page_info)
                                    break  # Stop execution and wait for new plan
                                
                            elif function == "get_page_source":
                                utils.print_with_color("페이지 소스 가져오기", "green")
                                result = self._selenium_receiver.get_page_source()
                                utils.print_with_color("페이지 소스 가져오기 완료", "cyan")
                                
                            else:
                                utils.print_with_color(f"지원하지 않는 웹 액션: {function}", "red")
                                continue
                            
                            # Small delay between actions
                            import time
                            time.sleep(1)
                            
                        except Exception as e:
                            utils.print_with_color(f"수정된 단계 {i+1} 실행 중 오류: {e}", "red")
                            
                            # Get current page information for plan modification
                            current_page_info = self._get_current_page_info()
                            
                            # Create step result for feedback
                            failed_step = {
                                'step': i + 1,
                                'function': function,
                                'args': args,
                                'success': False,
                                'error': str(e),
                                'page_info': current_page_info
                            }
                            
                            # Send feedback to HostAgent for plan modification
                            self._request_plan_modification([], failed_step, current_page_info)
                            break  # Stop execution and wait for new plan
                
                # Check if a new modified plan was generated
                if self._modified_plan:
                    utils.print_with_color("수정된 계획이 감지되어 다시 실행합니다.", "yellow")
                    self._web_plan = self._modified_plan
                    self._modified_plan = None
                    continue  # Loop to execute the new plan
                break  # No more modified plan, exit loop
            except Exception as e:
                utils.print_with_color(f"웹 자동화 실행 중 오류: {e}", "red")
                break
        # Set status to FINISH after web automation is completed
        self.status = self._agent_status_manager.FINISH.value
        utils.print_with_color("웹 자동화 완료. 작업을 종료합니다.", "green")

        # After all web plan execution (including modified plans), check if the user's request is truly complete
        # 1. Capture latest screenshot and HTML
        latest_html = ""
        latest_screenshot_url = ""
        try:
            if self._selenium_receiver and self._selenium_receiver.driver:
                latest_html = self._selenium_receiver.get_page_source()
        except Exception as e:
            latest_html = f"Failed to get HTML source: {e}"
        try:
            # If you have a photographer/capture method, use it. Otherwise, leave as empty or use previous screenshot.
            if hasattr(self, 'photographer') and hasattr(self.photographer, 'capture_desktop_screen_screenshot'):
                screenshot_path = self.photographer.capture_desktop_screen_screenshot(all_screens=True)
                if screenshot_path:
                    latest_screenshot_url = screenshot_path
            elif hasattr(self, '_desktop_screen_url'):
                latest_screenshot_url = self._desktop_screen_url
        except Exception as e:
            latest_screenshot_url = f"Failed to get screenshot: {e}"

        # 2. Ask LLM to judge if the user's request is truly complete
        original_request = self.context.get(ContextNames.REQUEST)
        post_action_prompt = [
            {"role": "system", "content": f"아래는 사용자의 요청 '{original_request}'을(를) 수행한 후의 스크린샷과 HTML입니다. 실제로 요청이 완료되었는지(예: 검색 결과가 화면에 나타났는지) 반드시 판단하세요. 요청이 완료되었다면 Status: FINISH, WebPlan: []로 응답하세요. 아직 미완료라면 Status: CONTINUE, WebPlan에 남은 단계만 포함하세요.\n\n작업 후 스크린샷: {latest_screenshot_url}\n작업 후 HTML:\n```html\n{latest_html}\n```"},
            {"role": "user", "content": f"위 작업 결과를 바탕으로, 사용자의 요청 '{original_request}'이(가) 실제로 완료되었는지 판단하고, Status와 WebPlan을 올바르게 응답하세요."}
        ]
        # 3. Get LLM's answer and update status/plan accordingly
        try:
            llm_response, _ = self.host_agent.get_response(post_action_prompt, "HOSTAGENT", use_backup_engine=True)
            llm_response_json = self.host_agent.response_to_dict(llm_response)
            status_from_llm = llm_response_json.get("Status", "").upper()
            if status_from_llm == "FINISH":
                utils.print_with_color("작업 후 LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
                self.status = self._agent_status_manager.FINISH.value
            elif status_from_llm == "CONTINUE":
                utils.print_with_color("작업 후 LLM이 CONTINUE 상태를 반환했습니다. 남은 계획을 실행합니다.", "yellow")
                self.status = self._agent_status_manager.CONTINUE.value
                self._web_plan = llm_response_json.get("WebPlan", [])
                # (선택) self._modified_plan = self._web_plan  # If you want to immediately re-enter the loop
            else:
                utils.print_with_color(f"작업 후 LLM Status 파싱 실패: {status_from_llm}", "red")
        except Exception as e:
            utils.print_with_color(f"작업 후 LLM 상태 판단 프롬프트 실패: {e}", "red")

    def _print_user_response(self) -> None:
        """
        Print the user response in the new simplified format.
        """
        response_dict = {
            "Observation": self.observation,
            "Thought": self.thought,
            "Response": self.response,
            "Comment": self.comment,
            "WebPlan": self._web_plan if self._is_web_request else self.web_plan
        }
        
        self.host_agent.print_response(response_dict)

    def _create_detailed_web_plan(self, user_request: str) -> List[str]:
        """
        Create a detailed web automation plan based on user request and LLM analysis.
        :param user_request: The user's request.
        :return: List of detailed web automation steps.
        """
        plan = []
        user_request_lower = user_request.lower()
        
        # Extract URL if present
        url = self._extract_url_from_request(user_request)
        
        # Create detailed plan based on request type
        if "검색" in user_request or "search" in user_request_lower:
            if url:
                plan.append(f"1. {url}로 이동")
            else:
                plan.append("1. https://www.google.com으로 이동")
            plan.append("2. 검색창을 찾아서 클릭")
            plan.append("3. 검색어 입력")
            plan.append("4. 검색 버튼 클릭")
            
        elif "클릭" in user_request or "click" in user_request_lower:
            if url:
                plan.append(f"1. {url}로 이동")
            plan.append("2. 클릭할 요소 찾기")
            plan.append("3. 해당 요소 클릭")
            
        elif "입력" in user_request or "input" in user_request_lower or "텍스트" in user_request:
            if url:
                plan.append(f"1. {url}로 이동")
            plan.append("2. 입력 필드 찾기")
            plan.append("3. 텍스트 입력")
            
        elif url:
            plan.append(f"1. {url}로 이동")
            plan.append("2. 페이지 로딩 대기")
            
        else:
            plan.append("1. 기본 웹페이지로 이동")
            plan.append("2. 페이지 분석")
            plan.append("3. 사용자 요청에 맞는 액션 수행")
        
        return plan

    def _is_window_interface_available(self, new_app_window: UIAWrapper) -> bool:
        """
        Check if the window interface is available for the visual element.
        :param new_app_window: The new application window.
        :return: True if the window interface is available, False otherwise.
        """
        try:
            new_app_window.is_normal()
            return True
        except Exception:
            utils.print_with_color(
                "Window interface {title} not available for the visual element.".format(
                    title=self.control_text
                ),
                "red",
            )
            return False

    def _is_same_window(self, window1: UIAWrapper, window2: UIAWrapper) -> bool:
        """
        Check if two windows are the same.
        :param window1: The first window.
        :param window2: The second window.
        :return: True if the two windows are the same, False otherwise.
        """

        equal = False

        try:
            equal = window1 == window2
        except:
            pass
        return equal

    def _switch_to_new_app_window(self, new_app_window: UIAWrapper) -> None:
        """
        Switch to the new application window if it is different from the current application window.
        :param new_app_window: The new application window.
        """

        if (
            not self._is_same_window(new_app_window, self.application_window)
            and self.application_window is not None
        ):
            utils.print_with_color("Switching to a new application...", "magenta")

        self.application_window = new_app_window

        self.context.set(ContextNames.APPLICATION_WINDOW, self.application_window)
        self.context.set(ContextNames.APPLICATION_ROOT_NAME, self.app_root)
        self.context.set(ContextNames.APPLICATION_PROCESS_NAME, self.control_text)

    def _select_application(self, application_window: UIAWrapper) -> None:
        """
        Create the app agent for the host agent.
        :param application_window: The application window.
        """

        action = OneStepAction(
            control_label=self.control_label,
            control_text=self.control_text,
            after_status=self.status,
            function="set_focus",
        )

        action.control_log = BaseControlLog(
            control_class=application_window.element_info.class_name,
            control_type=application_window.element_info.control_type,
            control_automation_id=application_window.element_info.automation_id,
        )

        self.actions = ActionSequence([action])

        # Get the root name of the application.
        self.app_root = self.control_inspector.get_application_root_name(
            application_window
        )

        # Check if the window interface is available for the visual element.
        if not self._is_window_interface_available(application_window):
            self.status = self._agent_status_manager.ERROR.value

            return

        # Switch to the new application window, if it is different from the current application window.
        self._switch_to_new_app_window(application_window)
        self.application_window.set_focus()
        if configs.get("MAXIMIZE_WINDOW", False):
            self.application_window.maximize()

        if configs.get("SHOW_VISUAL_OUTLINE_ON_SCREEN", True):
            self.application_window.draw_outline(colour="red", thickness=3)

    def _run_shell_command(self) -> None:
        """
        Run the shell command.
        """
        self.agent.create_puppeteer_interface()
        self.agent.Puppeteer.receiver_manager.create_api_receiver(
            self.app_root, self.control_text
        )

        action = OneStepAction(
            control_label=self.control_label,
            control_text=self.control_text,
            after_status=self.status,
            function="run_shell",
            args={"command": self.bash_command},
        )

        try:
            return_value = self.agent.Puppeteer.execute_command(
                "run_shell", {"command": self.bash_command}
            )
            error = ""
        except Exception as e:
            return_value = ""
            error = str(e)

        action.results = ActionExecutionLog(
            return_value=return_value, status=self.status, error=error
        )

        self.actions: ActionSequence = ActionSequence([action])

    def sync_memory(self):
        """
        Sync the memory of the HostAgent.
        """

        additional_memory = HostAgentAdditionalMemory(
            Step=self.session_step,
            RoundStep=self.round_step,
            AgentStep=self.host_agent.step,
            Round=self.round_num,
            ControlLabel=self.control_label,
            SubtaskIndex=-1,
            FunctionCall=self.actions.get_function_calls(),
            Action=self.actions.to_list_of_dicts(),
            ActionType="Bash" if self.bash_command else "UIControl",
            Request=self.request,
            Agent="HostAgent",
            AgentName=self.host_agent.name,
            Application=self.app_root,
            Cost=self._cost,
            Results=self.actions.get_results(),
            error=self._exeception_traceback,
            time_cost=self._time_cost,
            ControlLog=self.actions.get_control_logs(),
        )

        self.add_to_memory(self._response_json)
        self.add_to_memory(asdict(additional_memory))

    def update_memory(self) -> None:
        """
        Update the memory of the Agent.
        """

        # Sync the memory
        self.sync_memory()

        self.host_agent.add_memory(self._memory_data)

        # Log the memory item.
        self.context.add_to_structural_logs(self._memory_data.to_dict())
        # self.log(self._memory_data.to_dict())

        # Only memorize the keys in the HISTORY_KEYS list to feed into the prompt message in the future steps.
        memorized_action = {
            key: self._memory_data.to_dict().get(key) for key in configs["HISTORY_KEYS"]
        }

        self.host_agent.blackboard.add_trajectories(memorized_action)

    def _get_current_page_info(self) -> Dict[str, Any]:
        """
        Get current page information for plan modification.
        :return: Dictionary containing current page information.
        """
        try:
            # Wait for page to fully load
            utils.print_with_color("페이지 로딩을 기다립니다...", "cyan")
            import time
            time.sleep(3)  # Wait 3 seconds for page to load
            
            current_url = self._selenium_receiver.driver.current_url
            page_title = self._selenium_receiver.get_page_title()
            
            utils.print_with_color(f"현재 페이지: {page_title}", "cyan")
            utils.print_with_color(f"현재 URL: {current_url}", "cyan")
            
            return {
                'title': page_title,
                'url': current_url,
                'clickable_elements': [],
                'element_texts': []
            }
            
        except Exception as e:
            utils.print_with_color(f"페이지 정보 수집 실패: {e}", "red")
            return {
                'title': 'Unknown',
                'url': 'Unknown',
                'clickable_elements': [],
                'element_texts': [],
                'error': str(e)
            }

    def _request_plan_modification(self, execution_results: List[Dict], failed_step: Dict, page_info: Dict[str, Any]) -> None:
        """
        Request plan modification from HostAgent based on execution results.
        :param execution_results: List of all execution results.
        :param failed_step: The step that failed.
        :param page_info: Current page information.
        """
        try:
            utils.print_with_color("실행 결과를 바탕으로 계획 수정을 요청합니다...", "yellow")
            
            # Create feedback message for HostAgent
            feedback_message = {
                'type': 'web_automation_feedback',
                'execution_results': execution_results,
                'failed_step': failed_step,
                'page_info': page_info,
                'request': self.context.get(ContextNames.REQUEST),
                'timestamp': time.time()
            }
            
            # Store in blackboard for HostAgent to access
            if self.host_agent and self.host_agent.blackboard:
                self.host_agent.blackboard.add_trajectories(feedback_message)
                utils.print_with_color("실행 결과를 blackboard에 저장했습니다.", "cyan")
            
            # Create a new prompt for plan modification
            modification_prompt = self._create_modification_prompt(failed_step, page_info)
            
            # Get new plan from LLM
            utils.print_with_color("LLM에게 새로운 계획을 요청합니다...", "cyan")
            new_response, cost = self.host_agent.get_response(
                modification_prompt, "HOSTAGENT", use_backup_engine=True
            )
            
            # Parse the new response
            new_response_json = self.host_agent.response_to_dict(new_response)
            new_web_plan = new_response_json.get("WebPlan", [])
            
            if new_web_plan and isinstance(new_web_plan, list) and len(new_web_plan) > 0:
                utils.print_with_color("새로운 웹 자동화 계획이 생성되었습니다:", "green")
                utils.print_with_color(f"새 계획: {new_web_plan}", "cyan")
                
                # Store the modified plan
                self._modified_plan = new_web_plan
                
                # Continue with the new plan
                utils.print_with_color("새로운 계획으로 계속 실행합니다...", "green")
                self._web_plan = new_web_plan
                
            else:
                utils.print_with_color("새로운 계획을 생성할 수 없습니다.", "red")
                
        except Exception as e:
            utils.print_with_color(f"계획 수정 요청 중 오류: {e}", "red")

    def _summarize_execution_results(self, execution_results: list) -> str:
        """
        Summarize execution results for prompt brevity.
        :param execution_results: List of execution result dicts.
        :return: Summary string (max 10 lines).
        """
        if not execution_results:
            return "(이전 실행 결과 없음)"
        summary = []
        for step in execution_results[-10:]:  # 최근 10개만
            func = step.get('function', '')
            args = step.get('args', {})
            if step.get('success'):
                summary.append(f"성공: {func}({args})")
            else:
                summary.append(f"실패: {func}({args}) - {step.get('error', '')}")
        return '\n'.join(summary)

    def _create_modification_prompt(self, failed_step: Dict, page_info: Dict[str, Any], execution_results: list = None) -> List[Dict[str, Any]]:
        """
        Create a prompt for plan modification based on failed step and page info.
        :param failed_step: The step that failed.
        :param page_info: Current page information.
        :param execution_results: List of previous execution results (optional).
        :return: Prompt message for LLM.
        """
        original_request = self.context.get(ContextNames.REQUEST)
        # Get the actual HTML source of the current page
        html_source = ""
        try:
            if self._selenium_receiver and self._selenium_receiver.driver:
                html_source = self._selenium_receiver.get_page_source()
        except Exception as e:
            html_source = f"Failed to get HTML source: {e}"
        # Summarize execution results
        execution_summary = self._summarize_execution_results(execution_results)
        system_message = """당신은 웹 자동화 전문가입니다. 
실패한 웹 자동화 단계를 분석하고, 현재 페이지의 HTML 구조와 스크린샷을 바탕으로 새로운 계획을 수립해야 합니다.

- 새로운 WebPlan을 생성할 때, 이미 성공적으로 완료된 단계(예: 이미 이동한 페이지, 이미 입력한 텍스트, 이미 클릭한 버튼 등)는 다시 계획에 포함하지 마세요.
- WebPlan에는 반드시 '아직 완료되지 않은 단계'만 포함해야 하며, 중복된 단계나 이미 완료된 작업은 생략해야 합니다.

이전 단계 실행 요약:
{execution_summary}

실패한 단계 정보:
- 함수: {function}
- 인수: {args}
- 오류: {error}

현재 페이지 정보:
- 제목: {title}
- URL: {url}
- 스크린샷 정보: {screenshot_info}

현재 페이지의 HTML 소스:
```html
{html_source}
```

원래 요청: {request}

위 HTML 소스와 스크린샷 정보를 분석하여 실패한 단계를 대체할 수 있는 새로운 WebPlan을 생성하세요.
HTML에서 실제로 존재하는 요소들의 id, class, name, placeholder, type 등의 속성을 확인하여 정확한 selector를 사용하세요.

**중요한 가이드라인:**
1. HTML을 자세히 분석하여 실제로 존재하는 요소의 속성을 찾으세요
2. 검색창의 경우: input 태그의 name, id, class, placeholder 속성을 확인하세요
3. 버튼의 경우: button, input[type='submit'], a 태그의 text, id, class 속성을 확인하세요
4. selector는 CSS 선택자 또는 XPath를 사용할 수 있습니다

WebPlan은 함수 호출 형식(리스트의 딕셔너리)으로 작성해야 합니다.
지원하는 함수: navigate_to_url, click_element, input_text, get_page_source

응답은 다음 JSON 형식으로 작성하세요:
{{
    "Observation": "현재 상황 분석 (HTML 구조 기반)",
    "Thought": "새로운 계획 수립 과정",
    "WebPlan": [
        {{"function": "함수명", "args": {{"인수": "값"}}}},
        ...
    ],
    "Comment": "계획 수정 이유"
}}""".format(
            function=failed_step.get('function', ''),
            args=failed_step.get('args', {}),
            error=failed_step.get('error', ''),
            title=page_info.get('title', ''),
            url=page_info.get('url', ''),
            screenshot_info=page_info.get('screenshot_info', ''),
            html_source=html_source,
            request=original_request,
            execution_summary=execution_summary
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"실패한 단계를 수정해서 원래 요청 '{original_request}'을 완료할 수 있는 새로운 계획을 만들어주세요. HTML 구조와 스크린샷을 참고하여 정확한 selector를 사용하세요."}
        ]
