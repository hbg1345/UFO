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
from ufo.rag.web_search import BingSearchWeb

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
        self._modified_plan = None  # For storing modified plans from LLM

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
        Get or create Selenium Web receiver for web automation.
        """
        try:
            from ufo.automator.app_apis.web.selenium_webclient import SeleniumWebReceiver
            
            # Get session-level Selenium receiver instead of creating a new one
            session = self.context.get(ContextNames.SESSION)
            if session:
                self._selenium_receiver = session.get_or_create_selenium_receiver()
                utils.print_with_color("Session-level Selenium receiver retrieved successfully.", "green")
            else:
                # Fallback: create new receiver if session is not available
                self._selenium_receiver = SeleniumWebReceiver()
                utils.print_with_color("New Selenium receiver created (fallback).", "yellow")
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
                plan.append({"function": "input_text", "args": {"text": search_term, "selector": "검색창", "press_enter": True}})
                # Also try clicking search button as backup
                plan.append({"function": "click_element", "args": {"text": "검색", "element_type": "button"}})
            else:
                # Generic search plan
                plan.append({"function": "input_text", "args": {"text": "검색어", "selector": "검색창", "press_enter": True}})
                # Also try clicking search button as backup
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

        # Remove blackboard from prompt to reduce context size
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
            clickable_elements = []
            if self._selenium_receiver and self._selenium_receiver.driver:
                try:
                    # Use interactive elements instead of full HTML source
                    html_source = self._extract_interactive_elements()
                    clickable_elements = self._selenium_receiver.get_all_clickable_elements()
                    utils.print_with_color("인터랙티브 요소들을 성공적으로 가져왔습니다.", "green")
                except Exception as e:
                    utils.print_with_color(f"인터랙티브 요소 가져오기 실패: {e}", "yellow")
            
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
            
            # Store HTML source, clickable elements and Selenium status for AppAgent
            self.html_source = html_source
            self.clickable_elements = clickable_elements
            self.selenium_status = selenium_status

        # Print the response to user
        self._print_user_response()

        # Handle Status field for session control
        status_from_llm = self._response_json.get("Status", "").upper()
        comment_from_llm = self._response_json.get("Comment", "")
        
        if status_from_llm == "FINISH":
            utils.print_with_color("LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
            if comment_from_llm:
                utils.print_with_color(f"LLM Comment: {comment_from_llm}", "cyan")
            self.status = self._agent_status_manager.FINISH.value
        elif status_from_llm == "CONTINUE":
            utils.print_with_color("작업 후 LLM이 CONTINUE 상태를 반환했습니다. 남은 계획을 실행합니다.", "yellow")
            if comment_from_llm:
                utils.print_with_color(f"LLM Comment (CONTINUE 이유): {comment_from_llm}", "red")
            self.status = self._agent_status_manager.CONTINUE.value
            self._web_plan = self._response_json.get("WebPlan", [])
            
            # If Selenium is running, get current page info for better planning
            if self._selenium_receiver and self._selenium_receiver.driver:
                try:
                    utils.print_with_color("Selenium이 실행 중이므로 현재 페이지 정보를 가져옵니다.", "cyan")
                    current_url = self._selenium_receiver.driver.current_url
                    page_title = self._selenium_receiver.get_page_title()
                    
                    # Get interactive elements for better context
                    html_source = self._extract_interactive_elements()
                    
                    # Update HTML source for next round
                    self.html_source = html_source
                    
                    utils.print_with_color(f"현재 페이지: {page_title}", "cyan")
                    utils.print_with_color(f"현재 URL: {current_url}", "cyan")
                    utils.print_with_color("HTML 소스 정보가 다음 라운드에 포함됩니다.", "green")
                    
                except Exception as e:
                    utils.print_with_color(f"현재 페이지 정보 가져오기 실패: {e}", "yellow")
            
            # Clean up context for new round to prevent context overflow
            utils.print_with_color("새로운 라운드를 위해 컨텍스트를 정리합니다.", "cyan")
            try:
                # Clear accumulated page info to prevent context overflow
                if hasattr(self, '_desktop_screen_url'):
                    self._desktop_screen_url = None
                
                # Clear any accumulated HTML/context data
                if hasattr(self, 'clickable_elements'):
                    self.clickable_elements = []
                
                utils.print_with_color("컨텍스트 정리 완료 - 새로운 라운드 준비됨", "green")
                
            except Exception as cleanup_error:
                utils.print_with_color(f"컨텍스트 정리 중 오류: {cleanup_error}", "yellow")

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
                            'success': False,
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
                                
                            elif function == "click_element":
                                text = args.get("text", "")
                                element_type = args.get("element_type", "any")
                                selector = args.get("selector", None)
                                utils.print_with_color(f"요소 클릭: {text} ({element_type}) selector: {selector}", "green")
                                result = self._selenium_receiver.click_element(text, element_type, selector)
                                utils.print_with_color(f"클릭 결과: {result}", "cyan")
                                
                                # Check if click was successful
                                if "not found" in result or "not clickable" in result or "Failed" in result:
                                    utils.print_with_color(f"클릭 실패: {result}", "red")
                                    
                                    # Update step_result with failure information
                                    step_result['success'] = False
                                    step_result['error'] = result
                                    execution_results.append(step_result)
                                    
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
                                    # First check if the user's request is already completed using existing logic
                                    if self._check_completion_status():
                                        utils.print_with_color("사용자 요청이 이미 완수되었습니다. 작업을 종료합니다.", "green")
                                        self.status = self._agent_status_manager.FINISH.value
                                        return
                                    
                                    self._request_plan_modification(execution_results, failed_step, current_page_info)
                                    break  # Stop execution and wait for new plan
                                
                            elif function == "input_text":
                                text = args.get("text", "")
                                selector = args.get("selector", "")
                                clear_first = args.get("clear_first", True)
                                press_enter = args.get("press_enter", False)
                                utils.print_with_color(f"텍스트 입력: {text} (selector: {selector}, press_enter: {press_enter})", "green")
                                result = self._selenium_receiver.input_text(text, selector, clear_first, press_enter)
                                
                                # Check if input was successful
                                if "not found" in result or "failed" in result or "Failed" in result:
                                    utils.print_with_color(f"텍스트 입력 실패: {result}", "red")
                                    
                                    # Update step_result with failure information
                                    step_result['success'] = False
                                    step_result['error'] = result
                                    execution_results.append(step_result)
                                    
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
                                    self._request_plan_modification(execution_results, failed_step, current_page_info)
                                    break  # Stop execution and wait for new plan
                                else:
                                    utils.print_with_color(f"텍스트 입력 성공: {result}", "cyan")
                                
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
                            
                            # Add successful step result to execution_results
                            if step_result['success']:
                                execution_results.append(step_result)
                                utils.print_with_color(f"단계 {i+1} 성공: {function} - execution_results에 추가됨", "green")
                            
                        except Exception as e:
                            utils.print_with_color(f"수정된 단계 {i+1} 실행 중 오류: {e}", "red")
                            
                            # Update step_result with exception information
                            step_result['success'] = False
                            step_result['error'] = str(e)
                            execution_results.append(step_result)
                            
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
                            self._request_plan_modification(execution_results, failed_step, current_page_info)
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
        
        # Get blackboard information for context
        blackboard_context = "Blackboard information removed to reduce context size."
        
        # Get interactive elements information
        interactive_elements = self._extract_interactive_elements()
        
        post_action_prompt = [
            {"role": "system", "content": f"""You are an expert in determining whether a user's request has been actually completed.

Original user request: '{original_request}'

**CRITICAL: You MUST analyze the page information below to determine completion status.**

**COMPLETION CRITERIA:**
**CRITICAL: You must determine if the user's original request has been ACTUALLY COMPLETED.**

- **If the user's request is fully satisfied** → FINISH
- **If the user's request is NOT fully satisfied** → CONTINUE

**Current page information:**
{interactive_elements}

**Blackboard information (previous execution records):**
{blackboard_context}

**MANDATORY ANALYSIS:**
You MUST examine the page information above and determine if the user's request is completely fulfilled.

**DECISION RULE:**
- **If user's request is completely fulfilled** → FINISH
- **If user's request is partially fulfilled or not fulfilled** → CONTINUE

Based on the above information, determine whether the user's request has been **actually completed**.

**CRITICAL: You must respond with EXACTLY one of these two status values:**
- **If completed**: Status: "FINISH", WebPlan: []
- **If still incomplete**: Status: "CONTINUE", include remaining steps in WebPlan

**Valid status values ONLY: "FINISH" or "CONTINUE"**
**Do NOT use "COMPLETED", "DONE", or any other status values.**

**IMPORTANT: If you choose CONTINUE, you MUST explain why in the Comment field.**

**Examples:**
- "Search for 석인호" → If search results are displayed → FINISH
- "Search for weather" → If weather info is displayed → FINISH
- "I want to listen to Jo Jae-min's piano on YouTube" → Just search results → CONTINUE (need video playing)
- "Login to Naver" → Must actually be logged in → FINISH"""},
            {"role": "user", "content": f"Based on the above work results, determine whether the user's request '{original_request}' has been actually completed and respond with correct Status and WebPlan. Use ONLY 'FINISH' or 'CONTINUE' as Status value. If you choose CONTINUE, explain why in the Comment field."}
        ]
        # 3. Get LLM's answer and update status/plan accordingly
        try:
            llm_response, _ = self.host_agent.get_response(post_action_prompt, "HOSTAGENT", use_backup_engine=True)
            llm_response_json = self.host_agent.response_to_dict(llm_response)
            status_from_llm = llm_response_json.get("Status", "").upper()
            comment_from_llm = llm_response_json.get("Comment", "")
            
            if status_from_llm == "FINISH":
                utils.print_with_color("작업 후 LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
                if comment_from_llm:
                    utils.print_with_color(f"LLM Comment: {comment_from_llm}", "cyan")
                self.status = self._agent_status_manager.FINISH.value
            elif status_from_llm == "CONTINUE":
                utils.print_with_color("작업 후 LLM이 CONTINUE 상태를 반환했습니다. 남은 계획을 실행합니다.", "yellow")
                if comment_from_llm:
                    utils.print_with_color(f"LLM Comment (CONTINUE 이유): {comment_from_llm}", "red")
                self.status = self._agent_status_manager.CONTINUE.value
                self._web_plan = llm_response_json.get("WebPlan", [])
                
                # Clean up context for new round to prevent context overflow
                utils.print_with_color("새로운 라운드를 위해 컨텍스트를 정리합니다.", "cyan")
                try:
                    # Clear accumulated page info to prevent context overflow
                    if hasattr(self, '_desktop_screen_url'):
                        self._desktop_screen_url = None
                    
                    # Clear any accumulated HTML/context data
                    if hasattr(self, 'clickable_elements'):
                        self.clickable_elements = []
                    
                    utils.print_with_color("컨텍스트 정리 완료 - 새로운 라운드 준비됨", "green")
                    
                except Exception as cleanup_error:
                    utils.print_with_color(f"컨텍스트 정리 중 오류: {cleanup_error}", "yellow")
            else:
                utils.print_with_color(f"작업 후 LLM Status 파싱 실패: {status_from_llm}", "red")
                # 파싱 실패 시 재요청
                utils.print_with_color("파싱 실패로 재요청합니다...", "yellow")
                retry_prompt = [
                    {"role": "system", "content": f"""Status parsing failed in the previous response.
Original request: '{original_request}'
Failed response: {llm_response[:500]}...

**CRITICAL: You MUST analyze the page information below to determine completion status.**

**COMPLETION CRITERIA:**
**CRITICAL: You must determine if the user's original request has been ACTUALLY COMPLETED.**

- **If the user's request is fully satisfied** → FINISH
- **If the user's request is NOT fully satisfied** → CONTINUE

**Current page information:**
{interactive_elements}

**Blackboard information (previous execution records):**
{blackboard_context}

**MANDATORY ANALYSIS:**
You MUST examine the page information above and determine if the user's request is completely fulfilled.

**DECISION RULE:**
- **If user's request is completely fulfilled** → FINISH
- **If user's request is partially fulfilled or not fulfilled** → CONTINUE

Based on the above information, determine whether the user's request has been **actually completed**.

**CRITICAL: You must respond with EXACTLY one of these two status values:**
- **If completed**: Status: "FINISH", WebPlan: []
- **If still incomplete**: Status: "CONTINUE", include remaining steps in WebPlan

**Valid status values ONLY: "FINISH" or "CONTINUE"**
**Do NOT use "COMPLETED", "DONE", or any other status values.**

**IMPORTANT: If you choose CONTINUE, you MUST explain why in the Comment field.**

**Examples:**
- "Search for 석인호" → If search results are displayed → FINISH
- "Search for weather" → If weather info is displayed → FINISH
- "I want to listen to Jo Jae-min's piano on YouTube" → Just search results → CONTINUE (need video playing)
- "Login to Naver" → Must actually be logged in → FINISH"""},
                    {"role": "user", "content": f"Determine whether the user's request '{original_request}' has been actually completed and respond with correct Status and WebPlan. Use ONLY 'FINISH' or 'CONTINUE' as Status value. If you choose CONTINUE, explain why in the Comment field."}
                ]
                
                retry_response, _ = self.host_agent.get_response(retry_prompt, "HOSTAGENT", use_backup_engine=True)
                retry_response_json = self.host_agent.response_to_dict(retry_response)
                retry_status = retry_response_json.get("Status", "").upper()
                retry_comment = retry_response_json.get("Comment", "")
                
                if retry_status == "FINISH":
                    utils.print_with_color("재요청 후 LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
                    if retry_comment:
                        utils.print_with_color(f"LLM Comment: {retry_comment}", "cyan")
                    self.status = self._agent_status_manager.FINISH.value
                elif retry_status == "CONTINUE":
                    utils.print_with_color("재요청 후 LLM이 CONTINUE 상태를 반환했습니다. 남은 계획을 실행합니다.", "yellow")
                    if retry_comment:
                        utils.print_with_color(f"LLM Comment (CONTINUE 이유): {retry_comment}", "red")
                    self.status = self._agent_status_manager.CONTINUE.value
                    self._web_plan = retry_response_json.get("WebPlan", [])
                else:
                    utils.print_with_color(f"재요청 후에도 Status 파싱 실패: {retry_status}", "red")
                    # 최종 fallback: 기본값으로 설정
                    self.status = self._agent_status_manager.FINISH.value
                    utils.print_with_color("최종 fallback으로 FINISH 상태로 설정합니다.", "yellow")
                    
        except Exception as e:
            utils.print_with_color(f"작업 후 LLM 상태 판단 프롬프트 실패: {e}", "red")
            # 예외 발생 시에도 재요청
            utils.print_with_color("예외 발생으로 재요청합니다...", "yellow")
            try:
                retry_prompt = [
                    {"role": "system", "content": f"""An exception occurred in the previous request.
Original request: '{original_request}'
Exception: {str(e)}

**CRITICAL: You MUST analyze the page information below to determine completion status.**

**COMPLETION CRITERIA:**
**CRITICAL: You must determine if the user's original request has been ACTUALLY COMPLETED.**

- **If the user's request is fully satisfied** → FINISH
- **If the user's request is NOT fully satisfied** → CONTINUE

**Current page information:**
{interactive_elements}

**Blackboard information (previous execution records):**
{blackboard_context}

**MANDATORY ANALYSIS:**
You MUST examine the page information above and determine if the user's request is completely fulfilled.

**DECISION RULE:**
- **If user's request is completely fulfilled** → FINISH
- **If user's request is partially fulfilled or not fulfilled** → CONTINUE

Based on the above information, determine whether the user's request has been **actually completed**.

**CRITICAL: You must respond with EXACTLY one of these two status values:**
- **If completed**: Status: "FINISH", WebPlan: []
- **If still incomplete**: Status: "CONTINUE", include remaining steps in WebPlan

**Valid status values ONLY: "FINISH" or "CONTINUE"**
**Do NOT use "COMPLETED", "DONE", or any other status values.**

Please respond in JSON format only."""},
                    {"role": "user", "content": f"Determine whether the user's request '{original_request}' has been actually completed and respond with correct Status and WebPlan. Use ONLY 'FINISH' or 'CONTINUE' as Status value. If you choose CONTINUE, explain why in the Comment field."}
                ]
                
                retry_response, _ = self.host_agent.get_response(retry_prompt, "HOSTAGENT", use_backup_engine=True)
                retry_response_json = self.host_agent.response_to_dict(retry_response)
                retry_status = retry_response_json.get("Status", "").upper()
                
                if retry_status == "FINISH":
                    utils.print_with_color("재요청 후 LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
                    self.status = self._agent_status_manager.FINISH.value
                elif retry_status == "CONTINUE":
                    utils.print_with_color("재요청 후 LLM이 CONTINUE 상태를 반환했습니다. 남은 계획을 실행합니다.", "yellow")
                    self.status = self._agent_status_manager.CONTINUE.value
                    self._web_plan = retry_response_json.get("WebPlan", [])
                else:
                    utils.print_with_color(f"재요청 후에도 Status 파싱 실패: {retry_status}", "red")
                    # 최종 fallback: 기본값으로 설정
                    self.status = self._agent_status_manager.FINISH.value
                    utils.print_with_color("최종 fallback으로 FINISH 상태로 설정합니다.", "yellow")
                    
            except Exception as retry_e:
                utils.print_with_color(f"재요청도 실패: {retry_e}", "red")
                # 최종 fallback: 기본값으로 설정
                self.status = self._agent_status_manager.FINISH.value
                utils.print_with_color("최종 fallback으로 FINISH 상태로 설정합니다.", "yellow")

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

    def _get_previous_page_info(self) -> Dict[str, Any]:
        """
        Get previous page information from blackboard to accumulate.
        :return: Dictionary containing previous page information.
        """
        try:
            if self.host_agent and self.host_agent.blackboard and not self.host_agent.blackboard.is_empty():
                blackboard_prompt = self.host_agent.blackboard.blackboard_to_prompt()
                
                # Find the most recent web_automation_feedback
                for item in reversed(blackboard_prompt):
                    if isinstance(item, dict) and item.get('type') == 'web_automation_feedback':
                        page_info = item.get('page_info', {})
                        if page_info:
                            return page_info
                
            return {
                'previous_pages': [],
                'all_llm_analyses': []
            }
            
        except Exception as e:
            utils.print_with_color(f"이전 페이지 정보 가져오기 실패: {e}", "yellow")
            return {
                'previous_pages': [],
                'all_llm_analyses': []
            }

    def _get_current_page_info(self) -> Dict[str, Any]:
        """
        Get current page information for plan modification.
        :return: Dictionary containing current page information.
        """
        try:
            # Wait for page to fully load
            utils.print_with_color("페이지 로딩을 기다립니다...", "cyan")
            
            current_url = self._selenium_receiver.driver.current_url
            page_title = self._selenium_receiver.get_page_title()
            
            utils.print_with_color(f"현재 페이지: {page_title}", "cyan")
            utils.print_with_color(f"현재 URL: {current_url}", "cyan")
            
            # Capture screenshot using existing method
            screenshot_url = ""
            try:
                if hasattr(self, 'photographer'):
                    # Use existing screenshot if available
                    if hasattr(self, '_desktop_screen_url') and self._desktop_screen_url:
                        screenshot_url = self._desktop_screen_url
                        utils.print_with_color("기존 스크린샷 사용", "cyan")
                    else:
                        # Capture new screenshot using existing method
                        desktop_save_path = self.log_path + f"web_action_step{self.session_step}.png"
                        self.photographer.capture_desktop_screen_screenshot(
                            all_screens=True, save_path=desktop_save_path
                        )
                        screenshot_url = self.photographer.encode_image_from_path(desktop_save_path)
                        utils.print_with_color("새 스크린샷 캡처 완료", "cyan")
            except Exception as e:
                utils.print_with_color(f"스크린샷 캡처 실패: {e}", "yellow")
            
            # Get search result summary using new function
            search_summary = self._get_search_result_summary(current_url, page_title, screenshot_url)
            
            # Get previous page info from blackboard to accumulate
            previous_page_info = self._get_previous_page_info()
            
            # Accumulate information
            accumulated_info = {
                'current_page': {
                'title': page_title,
                'url': current_url,
                    'screenshot_url': screenshot_url,
                    'search_summary': search_summary,
                    'timestamp': time.time()
                },
                'previous_pages': previous_page_info.get('previous_pages', []),
                'all_search_summaries': previous_page_info.get('all_search_summaries', []) + [search_summary],
                'total_pages_visited': previous_page_info.get('total_pages_visited', 0) + 1
            }
            
            return accumulated_info
            
        except Exception as e:
            utils.print_with_color(f"페이지 정보 수집 실패: {e}", "red")
            return {
                'current_page': {
                'title': 'Unknown',
                'url': 'Unknown',
                    'screenshot_url': '',
                    'search_summary': {'summary': '분석 실패', 'extracted_info': []},
                    'timestamp': time.time()
                },
                'previous_pages': [],
                'all_search_summaries': [],
                'total_pages_visited': 0,
                'error': str(e)
            }

    def _get_search_result_summary(self, current_url: str, page_title: str, screenshot_url: str) -> Dict[str, Any]:
        """
        Get search result summary from the current page.
        :param current_url: The current URL.
        :param page_title: The current page title.
        :param screenshot_url: The screenshot URL.
        :return: Dictionary containing search result summary.
        """
        try:
            # Check if this is a search result page
            is_search_page = any(keyword in current_url.lower() or keyword in page_title.lower() 
                               for keyword in ['search', '검색', 'google', 'naver', 'bing'])
            
            if not is_search_page:
                return {
                    'summary': 'Not a search result page',
                    'extracted_info': [],
                    'is_search_page': False
                }
            
            # Get page text content for analysis
            page_text = ""
            try:
                page_text = self._selenium_receiver.driver.find_element("tag name", "body").text
                utils.print_with_color(f"페이지 텍스트 길이: {len(page_text)} 문자", "cyan")
            except Exception as e:
                utils.print_with_color(f"페이지 텍스트 가져오기 실패: {e}", "yellow")
                page_text = ""
            
            # Extract search results using LLM
            prompt = f"""Please summarize the search results from the current page:

URL: {current_url}
Title: {page_title}
Page text: {page_text[:1000]}...

Please summarize the main information or search results that can be found on this page.
For example:
- If there are movie titles, extract the exact title
- If there are showtime information, extract it
- Extract other relevant information

Response format:
- Summary: "Page summary"
- Extracted information: ["Info1", "Info2", ...]

Please respond in simple text only."""

            llm_response, _ = self.host_agent.get_response(
                [{"role": "user", "content": prompt}], "HOSTAGENT", use_backup_engine=True
            )
            
            # Simple text-based parsing
            response_text = llm_response.strip()
            
            # Extract summary and information
            summary = "Search result analysis completed"
            extracted_info = []
            
            # Try to extract information from response
            if "Summary:" in response_text:
                summary_part = response_text.split("Summary:")[1].split("Extracted information:")[0].strip()
                summary = summary_part
                
            if "Extracted information:" in response_text:
                info_part = response_text.split("Extracted information:")[1].strip()
                # Simple extraction of list items
                if "[" in info_part and "]" in info_part:
                    info_content = info_part[info_part.find("[")+1:info_part.find("]")]
                    extracted_info = [item.strip().strip('"\'') for item in info_content.split(",") if item.strip()]
            
            return {
                'summary': summary,
                'extracted_info': extracted_info,
                'is_search_page': True,
                'page_title': page_title,
                'url': current_url
            }
            
        except Exception as e:
            utils.print_with_color(f"Search result summary failed: {e}", "red")
            return {
                'summary': 'Search result summary failed',
                'extracted_info': [],
                'is_search_page': False,
                'page_title': page_title,
                'url': current_url,
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
            utils.print_with_color("Requesting plan modification based on execution results...", "yellow")
            
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
                utils.print_with_color("Execution results stored in blackboard.", "cyan")
            
            # Create a new prompt for plan modification
            modification_prompt = self._create_modification_prompt(failed_step, page_info)
            
            # Get new plan from LLM
            utils.print_with_color("Requesting new plan from LLM...", "cyan")
            new_response, cost = self.host_agent.get_response(
                modification_prompt, "HOSTAGENT", use_backup_engine=True
            )
            
            # Debug: Print raw response
            utils.print_with_color(f"Raw LLM response: {new_response[:1000]}...", "yellow")
            
            # Parse the new response with error handling
            max_retries = 5
            retry_count = 0
            success = False
            
            # Get original request for retry prompts
            original_request = self.context.get(ContextNames.REQUEST)
            
            while retry_count < max_retries and not success:
                parse_error = None  # Initialize parse_error variable
                try:
                    if retry_count == 0:
                        # First attempt
                        response_to_parse = new_response
                    else:
                        # Retry attempts
                        utils.print_with_color(f"Retry attempt {retry_count} with correct format...", "yellow")
                        retry_prompt = [
                            {"role": "system", "content": f"""Your previous response failed to parse because it used incorrect format.

**PARSING ERROR:** {parse_error}

**PREVIOUS FAILED RESPONSE:**
{response_to_parse[:1000]}...

**FAILED EXECUTION DETAILS:**
**Failed Function:** {failed_step.get('function', '')}
**Failed Arguments:** {failed_step.get('args', {})}
**Execution Error:** {failed_step.get('error', '')}

**PROBLEM:** You used incorrect function names and argument formats.

**CORRECT FORMAT REQUIRED:**
You must respond in EXACT JSON format with these fields:
- "Observation": Brief analysis of current situation
- "Thought": Your reasoning process
- "WebPlan": Array of function calls in this format:
  [{{"function": "function_name", "args": {{"arg1": "value1", "arg2": "value2"}}}}]
- "Comment": Brief explanation

**CORRECT FUNCTION NAMES AND ARGUMENTS:**
- `navigate_to_url`: {{"url": "https://example.com"}}
- `input_text`: {{"text": "text to input", "selector": "#search-field", "press_enter": true}}
- `click_element`: {{"text": "element text", "element_type": "button"}}

**EXAMPLE OF CORRECT FORMAT:**
```json
{{
  "Observation": "Current page shows search results",
  "Thought": "Need to click on first video result",
  "WebPlan": [
    {{"function": "input_text", "args": {{"text": "조재민 피아노", "selector": "#search-field", "press_enter": true}}}},
    {{"function": "click_element", "args": {{"text": "Video Title", "element_type": "link"}}}}
  ],
  "Comment": "Clicking first video to play"
}}
```

**CRITICAL:** Convert your previous response to this exact format. Use ONLY the correct function names and argument formats above."""},
                            {"role": "user", "content": f"Create a new WebPlan for the failed step. Function: {failed_step.get('function', '')}, Arguments: {failed_step.get('args', {})}, Error: {failed_step.get('error', '')}. Original request: {original_request}. Convert your previous response to the correct format."}
                        ]
                        
                        retry_response, _ = self.host_agent.get_response(retry_prompt, "HOSTAGENT", use_backup_engine=True)
                        utils.print_with_color(f"Retry response: {retry_response[:500]}...", "yellow")
                        response_to_parse = retry_response
                    
                    # Try to parse the response
                    response_json = self.host_agent.response_to_dict(response_to_parse)
                    web_plan = response_json.get("WebPlan", [])
                    
                    if web_plan and isinstance(web_plan, list) and len(web_plan) > 0:
                        utils.print_with_color(f"Successfully generated plan on attempt {retry_count + 1}!", "green")
                        
                        # Print full LLM response including Observation, Thought, etc.
                        observation = response_json.get("Observation", "")
                        thought = response_json.get("Thought", "")
                        comment = response_json.get("Comment", "")
                        
                        if observation:
                            utils.print_with_color(f"Observation: {observation}", "blue")
                        if thought:
                            utils.print_with_color(f"Thought: {thought}", "magenta")
                        if comment:
                            utils.print_with_color(f"Comment: {comment}", "yellow")
                        
                        utils.print_with_color(f"New plan: {web_plan}", "cyan")
                        
                        # Store the modified plan and use it
                        self._modified_plan = web_plan
                        self._web_plan = web_plan
                        success = True
                    else:
                        utils.print_with_color(f"Attempt {retry_count + 1} failed - WebPlan invalid", "red")
                        utils.print_with_color(f"WebPlan value: {web_plan}", "red")
                        utils.print_with_color(f"WebPlan type: {type(web_plan)}", "red")
                        retry_count += 1
                        
                except Exception as parse_error:
                    utils.print_with_color(f"Attempt {retry_count + 1} parsing failed: {parse_error}", "red")
                    if retry_count == 0:
                        utils.print_with_color(f"Original response: {new_response[:500]}...", "yellow")
                    retry_count += 1
            
            if not success:
                utils.print_with_color(f"Failed to generate plan after {max_retries} attempts.", "red")
                
        except Exception as e:
            utils.print_with_color(f"Error during plan modification request: {e}", "red")

    def _summarize_execution_results(self, execution_results: list) -> str:
        """
        Summarize execution results for prompt brevity.
        :param execution_results: List of execution result dicts.
        :return: Summary string (immediate previous step only).
        """
        if not execution_results:
            return "(No previous execution results)"
        
        # 모든 실행 결과를 상세히 요약
        summary_parts = []
        for i, step in enumerate(execution_results):
            func = step.get('function', '')
            success = step.get('success', False)
            error = step.get('error', '')
            
            if success:
                summary_parts.append(f"Step {i+1}: {func} - SUCCESS")
        else:
                summary_parts.append(f"Step {i+1}: {func} - FAILED: {error}")
        
        return "\n".join(summary_parts)

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
                # Use interactive elements instead of full HTML source
                html_source = self._extract_interactive_elements()
        except Exception as e:
            html_source = f"Failed to get interactive elements: {e}"
        
        # Capture current screenshot for better analysis
        screenshot_url = ""
        try:
            if hasattr(self, 'photographer'):
                screenshot_path = self.photographer.capture_desktop_screen_screenshot(all_screens=True)
                screenshot_url = self.photographer.encode_image_from_path(screenshot_path)
        except Exception as e:
            screenshot_url = f"Failed to capture screenshot: {e}"
        
        # Get blackboard information for context
        blackboard_context = "Blackboard information removed to reduce context size."
        
        # Summarize execution results
        execution_summary = self._summarize_execution_results(execution_results)
        
        system_message = """You are a web automation expert. 
You need to analyze failed web automation steps and create new plans based on the current page's HTML structure and clickable elements.

**Important principles:**
When you need to click an element on a web page:
1. Analyze the HTML in detail to find the exact attributes of elements that actually exist
2. Use CSS selectors or XPath when possible to specify elements accurately
3. Prioritize id, class, name attributes over text-based search

For searches, prioritize using Enter key

When modifying plans, thoroughly analyze the failure cause based on html source, screenshots, blackboard information, etc.
Use screenshots to understand what elements are visible on the current screen and what state it's in.
Refer to previous execution records in the blackboard to avoid repeating failure patterns and create better plans.
You may need to partially modify the plan or create a completely new plan.
If you determine that the user's needs cannot be met on the current page, you can
include a process to search for the information you want on Naver to obtain necessary information.
If you determine that necessary information has been obtained, you must create a plan to complete the user's request.

**Failed step analysis:**
- Function: {function}
- Arguments: {args}
- Error: {error}

**Current page information:**
- Title: {current_title}
- URL: {current_url}
- Screenshot: {screenshot_url}
- Search result summary: {search_summary}

**Accumulated information:**
- Total pages visited: {total_pages}
- All search result summaries: {all_search_summaries}
- Previous pages: {previous_pages}

**Blackboard information (previous execution records):**
{blackboard_context}

**Current page interactive elements:**
{html_source}

**Original request:** {request}

**Previous step execution summary:**
{execution_summary}

**Important: Utilize search result summaries**
Check and utilize all previously collected search result summaries.
For example, if you searched for "Conan movie" on Naver, extract the exact movie title from the results and use it for Megabox search.

Based on the above information, create a new WebPlan that can replace the failed step.

**WebPlan writing guidelines:**
1. **Search input**: Prioritize using `press_enter: true` in `input_text` function
2. **Accurate selectors**: Use CSS selectors (`#id`, `.class`) or XPath when possible
3. **Element types**: Specify element_type that matches actual HTML tags
4. **Remove duplicates**: Don't include steps that have already been completed
5. **Information gathering**: If necessary information is lacking, definitely include Naver search steps
   - Use `navigate_to_url` to move to search engine
   - Use `input_text` to search for related keywords
   - Check search results for necessary information and return to original site

**Supported functions:**
- `navigate_to_url`: Navigate to URL
- `input_text`: Input text (includes press_enter option)
- `click_element`: Click element (recommend using accurate selector)

**Response format:**
```json
{{
    "Observation": "Current situation analysis (HTML structure based)",
    "Thought": "New plan creation process",
    "WebPlan": [
        {{"function": "function_name", "args": {{"argument": "value"}}}},
        ...
    ],
    "Comment": "Reason for plan modification"
}}
```""".format(
            function=failed_step.get('function', ''),
            args=failed_step.get('args', {}),
            error=failed_step.get('error', ''),
            current_title=page_info.get('title', ''),
            current_url=page_info.get('url', ''),
            screenshot_url=screenshot_url,
            search_summary=page_info.get('search_summary', {}),
            total_pages=page_info.get('total_pages_visited', 0),
            all_search_summaries=page_info.get('all_search_summaries', []),
            previous_pages=page_info.get('previous_pages', []),
            blackboard_context=blackboard_context,
            html_source=html_source,
            request=original_request,
            execution_summary=execution_summary
        )
        
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Modify the failed step to create a new plan that can complete the original request '{original_request}'. Go beyond simply finding HTML elements to click or input, and include steps to collect additional information if needed to complete the user's request. For example, if a movie title is ambiguous, include steps to search for the exact title, or if showtime information is needed, include steps to find showtimes, etc., to create a complete plan. **Important**: If information gathering is needed, definitely include steps to navigate to Naver using `navigate_to_url` and search in the WebPlan."}
        ]

    def _extract_interactive_elements(self) -> str:
        """
        Extract clickable and input elements from the current page.
        :return: String containing interactive elements information.
        """
        try:
            if not self._selenium_receiver or not self._selenium_receiver.driver:
                return "Selenium driver not available"
            
            elements_info = []
            
            # Get clickable elements
            try:
                clickable_elements = self._selenium_receiver.get_all_clickable_elements()
                if clickable_elements:
                    elements_info.append("**Clickable Elements:**")
                    for i, elem in enumerate(clickable_elements):
                        elements_info.append(f"  {i+1}. {elem.get('text', 'No text')} (tag: {elem.get('tag_name', 'unknown')})")
            except Exception as e:
                elements_info.append(f"Failed to get clickable elements: {e}")
            
            # Get input elements
            try:
                input_elements = self._selenium_receiver.driver.find_elements("tag name", "input")
                if input_elements:
                    elements_info.append("\n**Input Elements:**")
                    for i, elem in enumerate(input_elements):
                        input_type = elem.get_attribute("type") or "text"
                        input_id = elem.get_attribute("id") or "no-id"
                        input_name = elem.get_attribute("name") or "no-name"
                        input_placeholder = elem.get_attribute("placeholder") or "no-placeholder"
                        elements_info.append(f"  {i+1}. type={input_type}, id={input_id}, name={input_name}, placeholder={input_placeholder}")
            except Exception as e:
                elements_info.append(f"Failed to get input elements: {e}")
            
            # Get current page title and URL
            try:
                title = self._selenium_receiver.get_page_title()
                url = self._selenium_receiver.driver.current_url
                elements_info.insert(0, f"**Current Page:** {title}")
                elements_info.insert(1, f"**URL:** {url}")
            except Exception as e:
                elements_info.insert(0, f"Failed to get page info: {e}")
            
            # Get page text content (limited to reduce context)
            try:
                page_text = self._selenium_receiver.driver.find_element("tag name", "body").text
                utils.print_with_color(f"인터랙티브 요소용 페이지 텍스트 길이: {len(page_text)} 문자", "cyan")
                elements_info.append(f"\n**Page Text:**\n{page_text}")
            except Exception as e:
                elements_info.append(f"\n**Page Text:** Failed to get page text: {e}")
            
            return "\n".join(elements_info)
            
        except Exception as e:
            return f"Failed to extract interactive elements: {e}"

    def _check_if_request_completed(self) -> bool:
        """
        Check if the user's request has already been completed.
        :return: True if the request is completed, False otherwise.
        """
        # Implement your logic to check if the request has already been completed
        # This could involve checking the blackboard, previous actions, etc.
        return False

    def _check_completion_status(self) -> bool:
        """
        Check if the user's request has already been completed using existing completion logic.
        :return: True if the request is completed, False otherwise.
        """
        try:
            # Get current page information
            current_page_info = self._get_current_page_info()
            
            # Get interactive elements information
            interactive_elements = self._extract_interactive_elements()
            
            # Get original request
            original_request = self.context.get(ContextNames.REQUEST)
            
            # Use the same completion prompt logic as in execute_action
            completion_prompt = [
                {"role": "system", "content": f"""You are an expert in determining whether a user's request has been actually completed.

Original user request: '{original_request}'

**CRITICAL: You MUST analyze the page information below to determine completion status.**

**COMPLETION CRITERIA:**
**CRITICAL: You must determine if the user's original request has been ACTUALLY COMPLETED.**

- **If the user's request is fully satisfied** → FINISH
- **If the user's request is NOT fully satisfied** → CONTINUE

**Current page information:**
{interactive_elements}

**MANDATORY ANALYSIS:**
You MUST examine the page information above and determine if the user's request is completely fulfilled.

**DECISION RULE:**
- **If user's request is completely fulfilled** → FINISH
- **If user's request is partially fulfilled or not fulfilled** → CONTINUE

Based on the above information, determine whether the user's request has been **actually completed**.

**CRITICAL: You must respond with EXACTLY one of these two status values:**
- **If completed**: Status: "FINISH", WebPlan: []
- **If still incomplete**: Status: "CONTINUE", include remaining steps in WebPlan

**Valid status values ONLY: "FINISH" or "CONTINUE"**
**Do NOT use "COMPLETED", "DONE", or any other status values.**"""},
                {"role": "user", "content": f"Determine whether the user's request '{original_request}' has been actually completed and respond with correct Status. Use ONLY 'FINISH' or 'CONTINUE' as Status value."}
            ]
            
            # Get LLM's completion status
            llm_response, _ = self.host_agent.get_response(completion_prompt, "HOSTAGENT", use_backup_engine=True)
            llm_response_json = self.host_agent.response_to_dict(llm_response)
            status_from_llm = llm_response_json.get("Status", "").upper()
            
            if status_from_llm == "FINISH":
                utils.print_with_color("완수 상태 확인: 사용자 요청이 완료되었습니다.", "green")
                return True
            else:
                utils.print_with_color("완수 상태 확인: 사용자 요청이 아직 완료되지 않았습니다.", "yellow")
                return False
                
        except Exception as e:
            utils.print_with_color(f"완수 상태 확인 중 오류: {e}", "red")
            return False
