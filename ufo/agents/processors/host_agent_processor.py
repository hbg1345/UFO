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


@dataclass
class AccumulatedInfo:
    """
    Accumulated information from search results and other sources.
    """
    search_results: List[Dict[str, Any]] = None
    extracted_info: List[Dict[str, Any]] = None
    total_searches: int = 0
    last_updated: float = 0
    
    def __post_init__(self):
        if self.search_results is None:
            self.search_results = []
        if self.extracted_info is None:
            self.extracted_info = []
    
    def add_search_result(self, search_info: Dict[str, Any]):
        """Add a new search result."""
        self.search_results.append(search_info)
        self.total_searches += 1
        self.last_updated = time.time()
    
    def add_extracted_info(self, extracted_info: Dict[str, Any]):
        """Add extracted information from search results."""
        self.extracted_info.append(extracted_info)
        self.last_updated = time.time()
    
    def get_summary(self) -> str:
        """Get a summary of all accumulated information."""
        summary_parts = []
        
        if self.search_results:
            summary_parts.append(f"**Total searches performed: {self.total_searches}**")
            for i, result in enumerate(self.search_results[-3:], 1):  # Last 3 searches
                summary_parts.append(f"Search {i}: {result.get('query', 'Unknown')} → {result.get('summary', 'No summary')}")
        
        if self.extracted_info:
            summary_parts.append(f"**Extracted key information: {len(self.extracted_info)} items**")
            for i, info in enumerate(self.extracted_info[-5:], 1):  # Last 5 items
                summary_parts.append(f"Info {i}: {info.get('key', 'Unknown')} = {info.get('value', 'No value')}")
        
        return "\n".join(summary_parts) if summary_parts else "No accumulated information yet."


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
        
        # Accumulated information manager
        self._accumulated_info = AccumulatedInfo()

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
        
        # Get continue intention from previous round if available
        continue_intention = self.context.get(ContextNames.CONTINUE_INTENTION)
        
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
            continue_intention=continue_intention,  # Add continue intention to prompt
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
                # Store continue intention in context for next round
                self.context.set(ContextNames.CONTINUE_INTENTION, comment_from_llm)
                utils.print_with_color("CONTINUE 의도를 다음 라운드에 전달하기 위해 context에 저장했습니다.", "green")
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
        # If not a web request, just finish without executing any action
        if not self._is_web_request:
            utils.print_with_color("웹 요청이 아니므로 액션 실행을 건너뛰고 세션을 종료합니다.", "cyan")
            self.status = self._agent_status_manager.FINISH.value
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
                    utils.print_with_color(f"단계 {i+1} 실행 전 검토 중...", "cyan")
                    
                    if isinstance(step, dict) and 'function' in step and 'args' in step:
                        function = step['function']
                        args = step['args']
                        
                        # Add step number to step dict
                        step['step'] = i + 1
                        
                        # Request step review before execution
                        review_result = self._request_step_review(step, execution_results)
                        action = review_result.get("action", "EXECUTE")
                        
                        if action == "SKIP":
                            utils.print_with_color(f"단계 {i+1} 건너뛰기: {review_result.get('reason', '')}", "yellow")
                            continue
                        elif action == "REPLAN":
                            utils.print_with_color(f"전체 플랜 재구성 필요: {review_result.get('reason', '')}", "yellow")
                            
                            # Get current page information
                            current_page_info = self._get_current_page_info()
                            
                            # Create step result for replanning
                            replan_step = {
                                'step': i + 1,
                                'function': function,
                                'args': args,
                                'success': False,
                                'error': 'Replanning requested',
                                'page_info': current_page_info
                            }
                            
                            # Request new plan based on accumulated information
                            self._request_new_plan_with_accumulated_info(replan_step, current_page_info, execution_results)
                            break  # Stop execution and wait for new plan
                        elif action == "MODIFY":
                            modified_step = review_result.get("modified_step")
                            if modified_step:
                                utils.print_with_color(f"단계 {i+1} 수정됨: {modified_step}", "yellow")
                                function = modified_step.get("function", function)
                                args = modified_step.get("args", args)
                                step = {"function": function, "args": args, "step": i + 1}
                        
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
                                    self._request_new_plan_with_accumulated_info(failed_step, current_page_info, execution_results)
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
                                    self._request_new_plan_with_accumulated_info(failed_step, current_page_info, execution_results)
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
                                
                                # Let LLM analyze the successful step and update accumulated information if needed
                                current_page_info = self._get_current_page_info()
                                
                                # Create step result for analysis
                                successful_step = {
                                    'step': i + 1,
                                    'function': function,
                                    'args': args,
                                    'success': True,
                                    'result': result,
                                    'page_info': current_page_info
                                }
                                
                                # Ask LLM to analyze the step and update accumulated information
                                analysis_result = self._analyze_step_and_update_info(successful_step, current_page_info)
                                
                                # If LLM suggests updating accumulated info, do so
                                if analysis_result.get('should_update_info', False):
                                    utils.print_with_color("LLM이 새로운 정보를 발견하여 누적 정보를 업데이트합니다.", "yellow")
                                    self._update_accumulated_info_from_analysis(analysis_result)
                                
                                # If LLM suggests replanning, request new plan
                                if analysis_result.get('should_replan', False):
                                    utils.print_with_color("LLM이 새로운 정보를 바탕으로 계획 수정을 제안합니다.", "yellow")
                                    self._request_new_plan_with_accumulated_info(successful_step, current_page_info, execution_results)
                                    break  # Stop execution and wait for new plan
                        
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
                            self._request_new_plan_with_accumulated_info(failed_step, current_page_info, execution_results)
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

**URL Analysis Guidelines:**
- If URL contains "search_query=" or "q=" → Search has already been performed
- If URL contains "results" → You are on search results page
- If URL contains "watch?v=" → You are on a video page
- If URL is a homepage (e.g., youtube.com, naver.com) → You need to search
- If URL contains specific content → You may already be on the target page

**Page Title Analysis:**
- If title contains search terms → Search has likely been completed
- If title shows "Results" or "검색결과" → You are on search results page
- If title shows specific content → You may already be on target content

**HTML ELEMENTS ANALYSIS GUIDE:**

**1. CLICKABLE ELEMENTS:**
- Look for buttons, links, and interactive elements
- Use the exact text content for clicking
- Prefer elements with specific IDs or classes
- For navigation: look for menu items, navigation links
- For actions: look for buttons like "Search", "Submit", "Play", etc.

**2. INPUT ELEMENTS:**
- Identify search boxes, form fields, text inputs
- Use the ID, name, or placeholder text as selector
- For search: look for input with type="search" or placeholder containing "search"
- For forms: identify required fields and submit buttons

**3. IMPORTANT TEXT CONTENT:**
- Check headings (H1, H2, H3) for page context
- Look for error messages, success messages, or status text
- Identify page descriptions and meta information
- Use this to understand what page you're on and what's available

**4. FORM ELEMENTS:**
- Identify forms and their submission methods
- Look for form actions and methods
- Understand what data needs to be submitted

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

**Response format:**
```json
{{
    "Status": "FINISH|CONTINUE",
    "WebPlan": [],
    "Comment": "Detailed reasoning with numbered analysis: 1) Current page state assessment, 2) User request completion check, 3) Remaining tasks identification (if any)"
}}
```

**Important**: You must respond in valid JSON format with Status and WebPlan fields."""},
            {"role": "user", "content": f"Determine whether the user's request '{original_request}' has been actually completed and respond with correct Status. Use ONLY 'FINISH' or 'CONTINUE' as Status value."}
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
                    # Store continue intention in context for next round
                    self.context.set(ContextNames.CONTINUE_INTENTION, comment_from_llm)
                    utils.print_with_color("CONTINUE 의도를 다음 라운드에 전달하기 위해 context에 저장했습니다.", "green")
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
                    {"role": "user", "content": f"Determine whether the user's request '{original_request}' has been actually completed and respond with correct Status. Use ONLY 'FINISH' or 'CONTINUE' as Status value."}
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
                        # Store continue intention in context for next round
                        self.context.set(ContextNames.CONTINUE_INTENTION, retry_comment)
                        utils.print_with_color("CONTINUE 의도를 다음 라운드에 전달하기 위해 context에 저장했습니다.", "green")
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
                    {"role": "user", "content": f"Determine whether the user's request '{original_request}' has been actually completed and respond with correct Status. Use ONLY 'FINISH' or 'CONTINUE' as Status value."}
                ]
                
                retry_response, _ = self.host_agent.get_response(retry_prompt, "HOSTAGENT", use_backup_engine=True)
                retry_response_json = self.host_agent.response_to_dict(retry_response)
                retry_status = retry_response_json.get("Status", "").upper()
                
                if retry_status == "FINISH":
                    utils.print_with_color("재요청 후 LLM이 FINISH 상태를 반환했습니다. 세션을 종료합니다.", "yellow")
                    self.status = self._agent_status_manager.FINISH.value
                elif retry_status == "CONTINUE":
                    utils.print_with_color("재요청 후 LLM이 CONTINUE 상태를 반환했습니다. 남은 계획을 실행합니다.", "yellow")
                    if retry_comment:
                        utils.print_with_color(f"LLM Comment (CONTINUE 이유): {retry_comment}", "red")
                        # Store continue intention in context for next round
                        self.context.set(ContextNames.CONTINUE_INTENTION, retry_comment)
                        utils.print_with_color("CONTINUE 의도를 다음 라운드에 전달하기 위해 context에 저장했습니다.", "green")
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
Page text: {page_text}...

Please summarize the main information or search results that can be found on this page.
For example:
- If there are movie titles, extract the exact title
- If there are showtime information, extract it
- Extract other relevant information

**Response format:**
```json
{{
    "summary": "Page summary",
    "extracted_info": ["Info1", "Info2", "Info3"]
}}
```

Please respond in valid JSON format as specified above."""

            llm_response, _ = self.host_agent.get_response(
                [{"role": "user", "content": prompt}], "HOSTAGENT", use_backup_engine=True
            )
            
            # Parse JSON response
            try:
                response_json = self.host_agent.response_to_dict(llm_response)
                summary = response_json.get("summary", "Search result analysis completed")
                extracted_info = response_json.get("extracted_info", [])
            except Exception as parse_error:
                utils.print_with_color(f"JSON parsing failed for search summary: {parse_error}", "yellow")
                # Fallback to simple text parsing
                response_text = llm_response.strip()
                summary = "Search result analysis completed"
                extracted_info = []
                
                # Try to extract information from response
                if "summary" in response_text.lower():
                    summary_part = response_text.split("summary")[1].split("extracted_info")[0].strip()
                    summary = summary_part.strip('":,')
                    
                if "extracted_info" in response_text.lower():
                    info_part = response_text.split("extracted_info")[1].strip()
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

    def _request_plan_modification(self, execution_results: List[Dict], current_step: Dict, page_info: Dict[str, Any]) -> None:
        """
        Request plan modification from HostAgent based on execution results.
        :param execution_results: List of all execution results.
        :param current_step: The current step (failed or successful).
        :param page_info: Current page information.
        """
        try:
            step_status = "failed" if not current_step.get('success', False) else "successful"
            utils.print_with_color(f"Requesting plan modification based on {step_status} execution results...", "yellow")
            
            # Create feedback message for HostAgent
            feedback_message = {
                'type': 'web_automation_feedback',
                'execution_results': execution_results,
                'current_step': current_step,
                'page_info': page_info,
                'request': self.context.get(ContextNames.REQUEST),
                'timestamp': time.time()
            }
            
            # Store in blackboard for HostAgent to access
            if self.host_agent and self.host_agent.blackboard:
                self.host_agent.blackboard.add_trajectories(feedback_message)
                utils.print_with_color("Execution results stored in blackboard.", "cyan")
            
            # Create a new prompt for plan modification
            modification_prompt = self._create_modification_prompt(current_step, page_info)
            
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
**Failed Function:** {current_step.get('function', '')}
**Failed Arguments:** {current_step.get('args', {})}
**Execution Error:** {current_step.get('error', '')}

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

**CRITICAL:** Convert your previous response to this exact format. Use ONLY the correct function names and argument formats above."""},
                            {"role": "user", "content": f"Create a new WebPlan for the failed step. Function: {current_step.get('function', '')}, Arguments: {current_step.get('args', {})}, Error: {current_step.get('error', '')}. Original request: {original_request}. Convert your previous response to the correct format."}
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

    def _create_modification_prompt(self, current_step: Dict, page_info: Dict[str, Any], execution_results: list = None) -> List[Dict[str, Any]]:
        """
        Create a prompt for plan modification based on current step and page info.
        :param current_step: The current step (failed or successful).
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
        
        # Get accumulated information from LLM analysis
        accumulated_summary = self._accumulated_info.get_summary()
        
        # Summarize execution results
        execution_summary = self._summarize_execution_results(execution_results)
        
        # Determine if this is a failed step or successful step
        is_failed = not current_step.get('success', False)
        step_status = "failed" if is_failed else "successful"
        
        system_message = f"""You are a web automation expert. 
You need to analyze {step_status} web automation steps and create new plans based on the current page's HTML structure and clickable elements.

**CRITICAL: Always analyze the current URL and page title first to understand the current state.**

**URL Analysis Guidelines:**
- If URL contains "search_query=" or "q=" → Search has already been performed
- If URL contains "results" → You are on search results page
- If URL contains "watch?v=" → You are on a video page
- If URL is a homepage (e.g., youtube.com, naver.com) → You need to search
- If URL contains specific content → You may already be on the target page

**Page Title Analysis:**
- If title contains search terms → Search has likely been completed
- If title shows "Results" or "검색결과" → You are on search results page
- If title shows specific content → You may already be on target content

**HTML ELEMENTS ANALYSIS GUIDE:**

**1. CLICKABLE ELEMENTS:**
- Look for buttons, links, and interactive elements
- Use the exact text content for clicking
- Prefer elements with specific IDs or classes
- For navigation: look for menu items, navigation links
- For actions: look for buttons like "Search", "Submit", "Play", etc.

**2. INPUT ELEMENTS:**
- Identify search boxes, form fields, text inputs
- Use the ID, name, or placeholder text as selector
- For search: look for input with type="search" or placeholder containing "search"
- For forms: identify required fields and submit buttons

**3. IMPORTANT TEXT CONTENT:**
- Check headings (H1, H2, H3) for page context
- Look for error messages, success messages, or status text
- Identify page descriptions and meta information
- Use this to understand what page you're on and what's available

**4. FORM ELEMENTS:**
- Identify forms and their submission methods
- Look for form actions and methods
- Understand what data needs to be submitted

**Accumulated information from previous LLM analyses:**
{accumulated_summary}

**Important principles:**
When you need to click an element on a web page:
1. Analyze the HTML in detail to find the exact attributes of elements that actually exist
2. Use CSS selectors or XPath when possible to specify elements accurately
3. Prioritize id, class, name attributes over text-based search

For searches, prioritize using Enter key

When modifying plans, thoroughly analyze the {step_status} step based on html source, screenshots, blackboard information, and accumulated information from LLM analysis.
Use screenshots to understand what elements are visible on the current screen and what state it's in.
Refer to previous execution records in the blackboard to avoid repeating failure patterns and create better plans.
Use accumulated information from previous LLM analyses to make informed decisions.
You may need to partially modify the plan or create a completely new plan.
If you determine that the user's needs cannot be met on the current page, you can
include a process to search for the information you want on appropriate search sites to obtain necessary information.
If you determine that necessary information has been obtained, you must create a plan to complete the user's request.

**Current step analysis:**
- Function: {{function}}
- Arguments: {{args}}
- Status: {step_status}
- Result: {{result}}
- Error: {{error}}

**Current page information:**
- Title: {{current_title}}
- URL: {{current_url}}
- Screenshot: {{screenshot_url}}
- Search result summary: {{search_summary}}

**Accumulated information:**
- Total pages visited: {{total_pages}}
- All search result summaries: {{all_search_summaries}}
- Previous pages: {{previous_pages}}

**Blackboard information (previous execution records):**
{{blackboard_context}}

**Current page interactive elements:**
{{html_source}}

**Original request:** {{request}}

**Previous step execution summary:**
{{execution_summary}}

**Important: Utilize search result summaries**
Check and utilize all previously collected search result summaries.
For example, if you searched for "Conan movie" on Naver, extract the exact movie title from the results and use it for Megabox search.

Based on the above information, create a new WebPlan that can continue from the current step.

**PLANNING REQUIREMENTS:**
1. **Step-by-step planning**: First, write your plan as numbered steps in the Thought section
2. **Consistency check**: Ensure your WebPlan exactly matches your numbered steps
3. **Clear reasoning**: Explain why each step is necessary and how it contributes to the goal
4. **Avoid redundancy**: Don't include steps that have already been completed

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
    "Thought": "Step-by-step planning process with numbered steps: 1) First step reason, 2) Second step reason, 3) Third step reason...",
    "WebPlan": [
        {{"function": "function_name", "args": {{"argument": "value"}}}},
        ...
    ],
    "Comment": "Reason for plan modification and consistency confirmation"
}}
```

**CRITICAL: Your WebPlan must exactly match the numbered steps in your Thought section.**""".format(
            function=current_step.get('function', ''),
            args=current_step.get('args', {}),
            result=current_step.get('result', ''),
            error=current_step.get('error', ''),
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
            
            # Get current page title and URL first
            page_info = []
            try:
                title = self._selenium_receiver.get_page_title()
                url = self._selenium_receiver.driver.current_url
                page_info.append(f"**Current Page:** {title}")
                page_info.append(f"**URL:** {url}")
            except Exception as e:
                page_info.append(f"Failed to get page info: {e}")
            
            # 1. CLICKABLE ELEMENTS
            clickable_section = ["\n**CLICKABLE ELEMENTS:**"]
            try:
                clickable_elements = self._selenium_receiver.get_all_clickable_elements()
                if clickable_elements:
                    for i, elem in enumerate(clickable_elements):
                        text = elem.get('text', 'No text').strip()
                        tag_name = elem.get('tag_name', 'unknown')
                        element_id = elem.get('id', 'no-id')
                        element_class = elem.get('class', 'no-class')
                        
                        if text and len(text) > 0:  # Only include elements with actual text
                            clickable_section.append(f"  {i+1}. Text: '{text}' | Tag: {tag_name} | ID: {element_id} | Class: {element_class}")
                else:
                    clickable_section.append("  No clickable elements found")
            except Exception as e:
                clickable_section.append(f"  Failed to get clickable elements: {e}")
            
            # 2. INPUT ELEMENTS
            input_section = ["\n**INPUT ELEMENTS:**"]
            try:
                input_elements = self._selenium_receiver.driver.find_elements("tag name", "input")
                if input_elements:
                    for i, elem in enumerate(input_elements):
                        input_type = elem.get_attribute("type") or "text"
                        input_id = elem.get_attribute("id") or "no-id"
                        input_name = elem.get_attribute("name") or "no-name"
                        input_placeholder = elem.get_attribute("placeholder") or "no-placeholder"
                        input_value = elem.get_attribute("value") or ""
                        
                        # Only include relevant input elements
                        if input_type in ["text", "search", "email", "password", "number"] or input_placeholder != "no-placeholder":
                            input_section.append(f"  {i+1}. Type: {input_type} | ID: {input_id} | Name: {input_name} | Placeholder: '{input_placeholder}' | Value: '{input_value}'")
                else:
                    input_section.append("  No input elements found")
            except Exception as e:
                input_section.append(f"  Failed to get input elements: {e}")
            
            # 3. TEXT CONTENT (Main headings and important text)
            text_section = ["\n**IMPORTANT TEXT CONTENT:**"]
            try:
                # Get main headings (h1, h2, h3)
                headings = []
                for tag in ["h1", "h2", "h3"]:
                    try:
                        heading_elements = self._selenium_receiver.driver.find_elements("tag name", tag)
                        for elem in heading_elements:
                            heading_text = elem.text.strip()
                            if heading_text and len(heading_text) > 0:
                                headings.append(f"  {tag.upper()}: '{heading_text}'")
                    except Exception:
                        continue
                
                if headings:
                    text_section.extend(headings)
                else:
                    text_section.append("  No main headings found")
                
                # Get page description or meta description
                try:
                    meta_desc = self._selenium_receiver.driver.find_element("css selector", "meta[name='description']")
                    if meta_desc:
                        desc_text = meta_desc.get_attribute("content")
                        if desc_text:
                            text_section.append(f"  Description: '{desc_text[:100]}...'")
                except Exception:
                    pass
                
            except Exception as e:
                text_section.append(f"  Failed to get text content: {e}")
            
            # 4. FORM ELEMENTS (if any)
            form_section = ["\n**FORM ELEMENTS:**"]
            try:
                forms = self._selenium_receiver.driver.find_elements("tag name", "form")
                if forms:
                    for i, form in enumerate(forms):
                        form_action = form.get_attribute("action") or "no-action"
                        form_method = form.get_attribute("method") or "no-method"
                        form_section.append(f"  {i+1}. Action: {form_action} | Method: {form_method}")
                else:
                    form_section.append("  No forms found")
            except Exception as e:
                form_section.append(f"  Failed to get form elements: {e}")
            
            # Combine all sections
            all_sections = page_info + clickable_section + input_section + text_section + form_section
            
            return "\n".join(all_sections)
            
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

**URL Analysis Guidelines:**
- If URL contains "search_query=" or "q=" → Search has already been performed
- If URL contains "results" → You are on search results page
- If URL contains "watch?v=" → You are on a video page
- If URL is a homepage (e.g., youtube.com, naver.com) → You need to search
- If URL contains specific content → You may already be on the target page

**Page Title Analysis:**
- If title contains search terms → Search has likely been completed
- If title shows "Results" or "검색결과" → You are on search results page
- If title shows specific content → You may already be on target content

**HTML ELEMENTS ANALYSIS GUIDE:**

**1. CLICKABLE ELEMENTS:**
- Look for buttons, links, and interactive elements
- Use the exact text content for clicking
- Prefer elements with specific IDs or classes
- For navigation: look for menu items, navigation links
- For actions: look for buttons like "Search", "Submit", "Play", etc.

**2. INPUT ELEMENTS:**
- Identify search boxes, form fields, text inputs
- Use the ID, name, or placeholder text as selector
- For search: look for input with type="search" or placeholder containing "search"
- For forms: identify required fields and submit buttons

**3. IMPORTANT TEXT CONTENT:**
- Check headings (H1, H2, H3) for page context
- Look for error messages, success messages, or status text
- Identify page descriptions and meta information
- Use this to understand what page you're on and what's available

**4. FORM ELEMENTS:**
- Identify forms and their submission methods
- Look for form actions and methods
- Understand what data needs to be submitted

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

**Response format:**
```json
{{
    "Status": "FINISH|CONTINUE",
    "WebPlan": [],
    "Comment": "Detailed reasoning with numbered analysis: 1) Current page state assessment, 2) User request completion check, 3) Remaining tasks identification (if any)"
}}
```

**Important**: You must respond in valid JSON format with Status and WebPlan fields."""},
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

    def _request_step_review(self, step: Dict, execution_results: List[Dict]) -> Dict:
        """
        Request review of a step before execution.
        :param step: The step to be reviewed.
        :param execution_results: List of previous execution results.
        :return: Review result with action (execute/modify/skip).
        """
        try:
            utils.print_with_color(f"단계 {step.get('step', 'unknown')} 실행 전 검토를 요청합니다.", "yellow")
            
            # Get current page information
            current_page_info = self._get_current_page_info()
            html_source = self._extract_interactive_elements()
            accumulated_summary = self._accumulated_info.get_summary()
            
            # Get the full web plan for context
            full_plan = self._web_plan
            current_step_index = step.get('step', 1) - 1
            
            # Create review prompt
            review_prompt = [
                {"role": "system", "content": f"""You are a web automation expert reviewing a step before execution.

**CRITICAL: Always analyze the current URL and page title first to understand the current state.**

**URL Analysis Guidelines:**
- If URL contains "search_query=" or "q=" → Search has already been performed
- If URL contains "results" → You are on search results page
- If URL contains "watch?v=" → You are on a video page
- If URL is a homepage (e.g., youtube.com, naver.com) → You need to search
- If URL contains specific content → You may already be on the target page

**Page Title Analysis:**
- If title contains search terms → Search has likely been completed
- If title shows "Results" or "검색결과" → You are on search results page
- If title shows specific content → You may already be on target content

**CLICK ELEMENT ANALYSIS GUIDE (CRITICAL FOR CLICK OPERATIONS):**

**1. CLICKABLE ELEMENTS ANALYSIS:**
- **Exact Text Matching**: Find elements with EXACT text content that matches the target
- **ID/Class Priority**: Prefer elements with specific IDs or classes over generic text
- **Element Type Verification**: Verify the element type (button, link, div, etc.) matches the intended action
- **Multiple Elements**: If multiple elements have similar text, choose the most specific one
- **Context Relevance**: Ensure the element is in the right context (e.g., search results vs navigation)

**2. CLICK ARGUMENT OPTIMIZATION:**
- **text**: Use the EXACT text content from the HTML element
- **element_type**: Match the actual HTML tag (button, link, div, span, etc.)
- **selector**: Use CSS selector (#id, .class) when available, otherwise use XPath
- **Priority Order**: ID > Class > Text > XPath

**3. CLICK ELEMENT SELECTION STRATEGY:**
- **Search Results**: Look for elements with video titles, product names, or specific content
- **Navigation**: Look for menu items, breadcrumbs, or navigation links
- **Actions**: Look for buttons with action text (Play, Buy, Subscribe, etc.)
- **Forms**: Look for submit buttons, input fields, or form controls

**INPUT TEXT ANALYSIS GUIDE (CRITICAL FOR INPUT OPERATIONS):**

**1. INPUT ELEMENTS ANALYSIS:**
- **Input Type Identification**: Look for input elements with type="text", type="search", type="email", etc.
- **ID/Name Priority**: Prefer elements with specific IDs or name attributes over generic selectors
- **Placeholder Text**: Use placeholder text to identify the correct input field
- **Form Context**: Ensure the input is in the right form context (search form, login form, etc.)
- **Multiple Inputs**: If multiple inputs exist, choose the most specific one based on context

**2. INPUT ARGUMENT OPTIMIZATION:**
- **text**: The text to be entered (keep as is)
- **selector**: Use the most specific selector available:
  * **Priority 1**: ID selector (#search, #query, #email)
  * **Priority 2**: Name attribute ([name="search"], [name="q"])
  * **Priority 3**: Class selector (.search-input, .form-control)
  * **Priority 4**: XPath with specific attributes
- **press_enter**: Set to true for search operations, false for form filling
- **clear_first**: Set to true if you want to clear existing text before input

**3. INPUT ELEMENT SELECTION STRATEGY:**
- **Search Boxes**: Look for inputs with type="search" or placeholder containing "search"
- **Form Fields**: Identify required fields by required attribute or form validation
- **Login Forms**: Look for username/email and password fields
- **Contact Forms**: Identify name, email, phone, message fields
- **Search Forms**: Look for search inputs with appropriate submit buttons

**4. INPUT VALIDATION:**
- **Field Type**: Ensure the input type matches the expected data (text, email, number, etc.)
- **Required Fields**: Check if the field is required and has proper validation
- **Character Limits**: Consider maxlength attributes for text inputs
- **Pattern Matching**: Check for pattern attributes that define input format

**5. FORM SUBMISSION:**
- **Submit Method**: Determine if form uses GET or POST method
- **Submit Button**: Identify the correct submit button or use press_enter
- **Form Action**: Check the form action URL for proper submission
- **Validation**: Ensure all required fields are filled before submission

**6. IMPORTANT TEXT CONTENT:**
- Check headings (H1, H2, H3) for page context
- Look for error messages, success messages, or status text
- Identify page descriptions and meta information
- Use this to understand what page you're on and what's available

**7. FORM ELEMENTS:**
- Identify forms and their submission methods
- Look for form actions and methods
- Understand what data needs to be submitted

**Original user request:**
{self.context.get(ContextNames.REQUEST)}

**Full web automation plan:**
{json.dumps(full_plan, indent=2, ensure_ascii=False)}

**Current step to review (step {step.get('step', 'unknown')}):**
- Function: {step.get('function', '')}
- Arguments: {step.get('args', {})}

**Current page information:**
- Title: {current_page_info.get('current_page', {}).get('title', '')}
- URL: {current_page_info.get('current_page', {}).get('url', '')}

**Current page interactive elements:**
{html_source}

**Accumulated information from previous searches:**
{accumulated_summary}

**Previous execution results:**
{self._summarize_execution_results(execution_results)}

**REVIEW REQUIREMENTS:**
1. **Analyze current step**: Check if the step is appropriate for the current page state
2. **Check element availability**: Verify if the required elements exist on the page
3. **Consider overall plan**: Ensure the step contributes to completing the user's request
4. **Avoid redundancy**: Check if this step has already been completed or is unnecessary
5. **For CLICK operations**: Carefully analyze available clickable elements and optimize arguments

**Review criteria:**
1. **EXECUTE**: If the step is appropriate for the current page, fits the overall plan, and likely to succeed
2. **MODIFY**: If the step needs modification (wrong selector, missing element, better approach available, etc.)
3. **SKIP**: If the step is unnecessary, already completed, or should be replaced with a better approach
4. **REPLAN**: If the entire plan needs to be reconsidered based on accumulated information

**Consider the overall context:**
- Does this step contribute to completing the user's request?
- Is there a better approach based on accumulated information?
- Should the entire plan be restructured?
- If information is missing, should we include Naver search steps to gather it?
- **CRITICAL**: Is the current step redundant given the current page state?
- **ANALYZE HTML ELEMENTS**: Check if the required elements (clickable/input) actually exist on the page
- **FOR CLICK OPERATIONS**: Verify the exact text, element type, and selector match available elements

**Response format:**
```json
{{
    "action": "EXECUTE|MODIFY|SKIP|REPLAN",
    "reason": "Detailed explanation with numbered reasoning: 1) Current page state analysis, 2) Step appropriateness check, 3) Element availability verification, 4) Overall plan contribution assessment, 5) For clicks: element matching analysis",
    "modified_step": {{"function": "...", "args": {{...}}}} // Only if action is MODIFY
}}
```"""},
                {"role": "user", "content": f"Review step {step.get('step', 'unknown')} in the context of the full plan and user request: {self.context.get(ContextNames.REQUEST)}. Should I execute, modify, skip, or replan?"}
            ]
            
            # Get LLM's review
            review_response, _ = self.host_agent.get_response(review_prompt, "HOSTAGENT", use_backup_engine=True)
            review_json = self.host_agent.response_to_dict(review_response)
            
            action = review_json.get("action", "EXECUTE")
            reason = review_json.get("reason", "")
            modified_step = review_json.get("modified_step", None)
            
            utils.print_with_color(f"단계 검토 결과: {action} - {reason}", "cyan")
            
            if action == "REPLAN":
                utils.print_with_color("전체 플랜 재구성이 필요합니다.", "yellow")
                return {
                    "action": "REPLAN",
                    "reason": reason
                }
            elif action == "SKIP":
                utils.print_with_color("단계가 건너뛰어집니다.", "yellow")
                return {
                    "action": "SKIP",
                    "reason": reason
                }
            elif action == "MODIFY" and modified_step:
                utils.print_with_color(f"단계가 수정되었습니다: {modified_step}", "yellow")
                return {
                    "action": "MODIFY",
                    "reason": reason,
                    "modified_step": modified_step
                }
            else:
                utils.print_with_color("단계를 실행합니다.", "green")
                return {
                    "action": "EXECUTE",
                    "reason": reason
                }
                
        except Exception as e:
            utils.print_with_color(f"단계 검토 중 오류: {e}", "red")
            # 오류 발생 시 기본적으로 실행
            return {
                "action": "EXECUTE",
                "reason": f"Review failed, executing by default: {e}"
            }

    def _extract_key_information_from_search(self, search_query: str, page_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract key information from search results using LLM.
        :param search_query: The search query that was performed.
        :param page_info: Current page information including search results.
        :return: Extracted key information.
        """
        try:
            utils.print_with_color(f"검색 결과에서 핵심 정보를 추출합니다: {search_query}", "yellow")
            
            # Get current page information
            html_source = self._extract_interactive_elements()
            accumulated_summary = self._accumulated_info.get_summary()
            
            # Create extraction prompt
            extraction_prompt = [
                {"role": "system", "content": f"""You are an expert at extracting key information from search results.

**Current search query:** {search_query}

**Current page information:**
- Title: {page_info.get('current_page', {}).get('title', '')}
- URL: {page_info.get('current_page', {}).get('url', '')}

**Current page interactive elements:**
{html_source}

**Previously accumulated information:**
{accumulated_summary}

**Original user request:**
{self.context.get(ContextNames.REQUEST)}

**Extraction guidelines:**
1. **Movie titles**: Extract exact movie titles, release dates, ratings
2. **Showtimes**: Extract theater names, times, dates, prices
3. **Product info**: Extract product names, prices, availability
4. **General info**: Extract any relevant facts, dates, names, locations
5. **Links/URLs**: Extract important links or URLs

**Response format:**
```json
{{
    "extracted_info": [
        {{"key": "movie_title", "value": "Exact movie title", "confidence": "high|medium|low"}},
        {{"key": "release_date", "value": "2024-01-15", "confidence": "high|medium|low"}},
        {{"key": "theater", "value": "Megabox", "confidence": "high|medium|low"}}
    ],
    "search_summary": "Brief summary of what was found",
    "next_action_suggestion": "What should be done next based on this information"
}}
```"""},
                {"role": "user", "content": f"Extract key information from the search results for '{search_query}'. Focus on information that will help complete the user's request: {self.context.get(ContextNames.REQUEST)}"}
            ]
            
            # Get LLM's extraction
            extraction_response, _ = self.host_agent.get_response(extraction_prompt, "HOSTAGENT", use_backup_engine=True)
            extraction_json = self.host_agent.response_to_dict(extraction_response)
            
            extracted_info = extraction_json.get("extracted_info", [])
            search_summary = extraction_json.get("search_summary", "")
            next_action = extraction_json.get("next_action_suggestion", "")
            
            # Add to accumulated info
            search_info = {
                "query": search_query,
                "summary": search_summary,
                "timestamp": time.time(),
                "url": page_info.get('current_page', {}).get('url', '')
            }
            self._accumulated_info.add_search_result(search_info)
            
            for info in extracted_info:
                self._accumulated_info.add_extracted_info(info)
            
            utils.print_with_color(f"핵심 정보 추출 완료: {len(extracted_info)}개 항목", "green")
            utils.print_with_color(f"검색 요약: {search_summary}", "cyan")
            utils.print_with_color(f"다음 액션 제안: {next_action}", "yellow")
            
            return {
                "extracted_info": extracted_info,
                "search_summary": search_summary,
                "next_action_suggestion": next_action,
                "accumulated_summary": self._accumulated_info.get_summary()
            }
            
        except Exception as e:
            utils.print_with_color(f"핵심 정보 추출 실패: {e}", "red")
            return {
                "extracted_info": [],
                "search_summary": "Extraction failed",
                "next_action_suggestion": "Continue with current plan",
                "accumulated_summary": self._accumulated_info.get_summary()
            }

    def _request_new_plan_with_accumulated_info(self, current_step: Dict, page_info: Dict[str, Any], execution_results: List[Dict]) -> None:
        """
        Request a new plan based on accumulated information.
        :param current_step: The current step (failed or successful).
        :param page_info: Current page information.
        :param execution_results: List of previous execution results.
        """
        try:
            utils.print_with_color("누적된 정보를 바탕으로 새로운 플랜을 요청합니다.", "yellow")
            
            # Get current page information
            html_source = self._extract_interactive_elements()
            accumulated_summary = self._accumulated_info.get_summary()
            
            # Create new plan prompt
            new_plan_prompt = [
                {"role": "system", "content": f"""You are a web automation expert creating a new plan based on accumulated information.

**CRITICAL: Always analyze the current URL and page title first to understand the current state.**

**URL Analysis Guidelines:**
- If URL contains "search_query=" or "q=" → Search has already been performed
- If URL contains "results" → You are on search results page
- If URL contains "watch?v=" → You are on a video page
- If URL is a homepage (e.g., youtube.com, naver.com) → You need to search
- If URL contains specific content → You may already be on the target page

**Page Title Analysis:**
- If title contains search terms → Search has likely been completed
- If title shows "Results" or "검색결과" → You are on search results page
- If title shows specific content → You may already be on target content

**HTML ELEMENTS ANALYSIS GUIDE:**

**1. CLICKABLE ELEMENTS:**
- Look for buttons, links, and interactive elements
- Use the exact text content for clicking
- Prefer elements with specific IDs or classes
- For navigation: look for menu items, navigation links
- For actions: look for buttons like "Search", "Submit", "Play", etc.

**2. INPUT ELEMENTS:**
- Identify search boxes, form fields, text inputs
- Use the ID, name, or placeholder text as selector
- For search: look for input with type="search" or placeholder containing "search"
- For forms: identify required fields and submit buttons

**3. IMPORTANT TEXT CONTENT:**
- Check headings (H1, H2, H3) for page context
- Look for error messages, success messages, or status text
- Identify page descriptions and meta information
- Use this to understand what page you're on and what's available

**4. FORM ELEMENTS:**
- Identify forms and their submission methods
- Look for form actions and methods
- Understand what data needs to be submitted

**Current step analysis:**
- Function: {current_step.get('function', '')}
- Arguments: {current_step.get('args', {})}
- Status: {"successful" if current_step.get('success', False) else "failed"}
- Result: {current_step.get('result', '')}
- Error: {current_step.get('error', '')}

**Current page information:**
- Title: {page_info.get('current_page', {}).get('title', '')}
- URL: {page_info.get('current_page', {}).get('url', '')}

**Current page interactive elements:**
{html_source}

**Accumulated information from previous analyses:**
{accumulated_summary}

**Previous execution results:**
{self._summarize_execution_results(execution_results)}

**Original user request:**
{self.context.get(ContextNames.REQUEST)}

**PLANNING REQUIREMENTS:**
1. **Step-by-step planning**: First, write your plan as numbered steps in the Thought section
2. **Consistency check**: Ensure your WebPlan exactly matches your numbered steps
3. **Clear reasoning**: Explain why each step is necessary and how it contributes to the goal
4. **Use accumulated info**: Incorporate all previously extracted information from LLM analysis
5. **Build on success**: If current step was successful, continue from there
6. **Learn from failures**: If current step failed, create a better approach
7. **Avoid redundancy**: Don't include steps that have already been completed

**Planning guidelines:**
1. **Use accumulated information**: Incorporate all previously extracted information from LLM analysis
2. **Build on success**: If current step was successful, continue from there
3. **Learn from failures**: If current step failed, create a better approach
4. **Be specific**: Use exact information from accumulated data
5. **Complete the task**: Ensure the plan will fulfill the user's request
6. **Information gathering**: If any required information is missing or unclear, include search steps to gather it
   - Use `navigate_to_url` to go to appropriate search site
   - Use `input_text` with appropriate search terms
   - Let the LLM analyze search results and extract key information
7. **Search strategy**: When searching, use specific and relevant keywords that will yield useful information
8. **Avoid redundant steps**: Don't include steps that have already been completed based on current page state
9. **Analyze HTML elements**: Check if the required elements (clickable/input) actually exist on the page before planning

**Response format:**
```json
{{
    "Observation": "Analysis of current situation and accumulated information",
    "Thought": "Step-by-step planning process with numbered steps: 1) First step reason and method, 2) Second step reason and method, 3) Third step reason and method...",
    "WebPlan": [
        {{"function": "function_name", "args": {{"argument": "value"}}}},
        ...
    ],
    "Comment": "Explanation of how the new plan uses accumulated information and consistency confirmation"
}}
```

**CRITICAL: Your WebPlan must exactly match the numbered steps in your Thought section.**

**Important**: You must respond in valid JSON format as specified above."""},
                {"role": "user", "content": f"Create a new WebPlan that uses the accumulated information to complete the user's request: {self.context.get(ContextNames.REQUEST)}"}
            ]
            
            # Get new plan from LLM
            new_response, _ = self.host_agent.get_response(new_plan_prompt, "HOSTAGENT", use_backup_engine=True)
            
            # Parse the new response with error handling
            max_retries = 5
            retry_count = 0
            success = False
            
            while retry_count < max_retries and not success:
                try:
                    if retry_count == 0:
                        response_to_parse = new_response
                    else:
                        utils.print_with_color(f"새 플랜 파싱 재시도 {retry_count}...", "yellow")
                        retry_prompt = [
                            {"role": "system", "content": f"""Your previous response failed to parse. Please provide a new plan in the correct JSON format.

**Accumulated information:**
{accumulated_summary}

**Original request:**
{self.context.get(ContextNames.REQUEST)}

**Response format:**
```json
{{
    "Observation": "Brief analysis",
    "Thought": "Reasoning",
    "WebPlan": [
        {{"function": "navigate_to_url", "args": {{"url": "https://example.com"}}}},
        {{"function": "input_text", "args": {{"text": "search term", "selector": "#search", "press_enter": true}}}}
    ],
    "Comment": "Explanation"
}}
```"""},
                            {"role": "user", "content": f"Create a new WebPlan using accumulated information: {self.context.get(ContextNames.REQUEST)}"}
                        ]
                        retry_response, _ = self.host_agent.get_response(retry_prompt, "HOSTAGENT", use_backup_engine=True)
                        response_to_parse = retry_response
                    
                    response_json = self.host_agent.response_to_dict(response_to_parse)
                    web_plan = response_json.get("WebPlan", [])
                    
                    if web_plan and isinstance(web_plan, list) and len(web_plan) > 0:
                        utils.print_with_color(f"새 플랜 생성 성공! (시도 {retry_count + 1})", "green")
                        
                        observation = response_json.get("Observation", "")
                        thought = response_json.get("Thought", "")
                        comment = response_json.get("Comment", "")
                        
                        if observation:
                            utils.print_with_color(f"Observation: {observation}", "blue")
                        if thought:
                            utils.print_with_color(f"Thought: {thought}", "magenta")
                        if comment:
                            utils.print_with_color(f"Comment: {comment}", "yellow")
                        
                        utils.print_with_color(f"새 플랜: {web_plan}", "cyan")
                        
                        # Store the new plan
                        self._modified_plan = web_plan
                        self._web_plan = web_plan
                        success = True
                    else:
                        utils.print_with_color(f"시도 {retry_count + 1} 실패 - WebPlan이 유효하지 않음", "red")
                        retry_count += 1
                        
                except Exception as parse_error:
                    utils.print_with_color(f"시도 {retry_count + 1} 파싱 실패: {parse_error}", "red")
                    retry_count += 1
            
            if not success:
                utils.print_with_color(f"{max_retries}번 시도 후에도 새 플랜 생성 실패", "red")
                
        except Exception as e:
            utils.print_with_color(f"새 플랜 요청 중 오류: {e}", "red")

    def _analyze_step_and_update_info(self, step: Dict, page_info: Dict[str, Any]) -> Dict:
        """
        Let LLM analyze the step and decide whether to update accumulated information.
        :param step: The step to be analyzed.
        :param page_info: Current page information.
        :return: Analysis result with update recommendations.
        """
        try:
            utils.print_with_color(f"단계 {step.get('step', 'unknown')} 분석 중...", "yellow")
            
            # Get current page information
            html_source = self._extract_interactive_elements()
            accumulated_summary = self._accumulated_info.get_summary()
            
            # Create analysis prompt
            analysis_prompt = [
                {"role": "system", "content": f"""You are an expert at analyzing web automation steps and determining when to update accumulated information.

**Current step to analyze:**
- Function: {step.get('function', '')}
- Arguments: {step.get('args', {})}
- Success: {step.get('success', False)}
- Result: {step.get('result', '')}

**Current page information:**
- Title: {page_info.get('current_page', {}).get('title', '')}
- URL: {page_info.get('current_page', {}).get('url', '')}

**Current page interactive elements:**
{html_source}

**Previously accumulated information:**
{accumulated_summary}

**Original user request:**
{self.context.get(ContextNames.REQUEST)}

**Analysis guidelines:**
1. **Search Results**: If this step produced search results (Naver, Google, etc.), extract key information
2. **New Information**: If new relevant information was found (movie titles, prices, dates, etc.)
3. **Page Changes**: If the page content changed significantly and contains useful information
4. **Task Progress**: If this step brought us closer to completing the user's request

**Decision criteria:**
- **should_update_info**: Set to true if new useful information was found
- **should_replan**: Set to true if the new information suggests a different approach
- **extracted_info**: Key information found (titles, prices, dates, locations, etc.)
- **search_summary**: Brief summary of what was found (if applicable)

**Response format:**
```json
{{
    "should_update_info": true|false,
    "should_replan": true|false,
    "extracted_info": [
        {{"key": "movie_title", "value": "Exact title", "confidence": "high|medium|low"}},
        {{"key": "price", "value": "10000", "confidence": "high|medium|low"}}
    ],
    "search_summary": "Brief summary of what was found",
    "explanation": "Why this information is important and how it helps complete the user's request"
}}
```"""},
                {"role": "user", "content": f"Analyze step {step.get('step', 'unknown')} and determine if new information should be accumulated. Focus on information that helps complete: {self.context.get(ContextNames.REQUEST)}"}
            ]
            
            # Get LLM's analysis
            analysis_response, _ = self.host_agent.get_response(analysis_prompt, "HOSTAGENT", use_backup_engine=True)
            analysis_json = self.host_agent.response_to_dict(analysis_response)
            
            should_update_info = analysis_json.get("should_update_info", False)
            should_replan = analysis_json.get("should_replan", False)
            extracted_info = analysis_json.get("extracted_info", [])
            search_summary = analysis_json.get("search_summary", "")
            explanation = analysis_json.get("explanation", "")
            
            utils.print_with_color(f"LLM 분석 결과: 정보 업데이트={should_update_info}, 계획 수정={should_replan}", "cyan")
            if explanation:
                utils.print_with_color(f"분석 설명: {explanation}", "cyan")
            
            return {
                "should_update_info": should_update_info,
                "should_replan": should_replan,
                "extracted_info": extracted_info,
                "search_summary": search_summary,
                "explanation": explanation
            }
            
        except Exception as e:
            utils.print_with_color(f"단계 분석 실패: {e}", "red")
            return {
                "should_update_info": False,
                "should_replan": False,
                "extracted_info": [],
                "search_summary": "",
                "explanation": f"Analysis failed: {e}"
            }

    def _update_accumulated_info_from_analysis(self, analysis_result: Dict):
        """
        Update accumulated information based on LLM analysis.
        :param analysis_result: The analysis result from the LLM.
        """
        try:
            # Add extracted information
            for info in analysis_result.get("extracted_info", []):
                self._accumulated_info.add_extracted_info(info)
                utils.print_with_color(f"추출된 정보 추가: {info.get('key', 'Unknown')} = {info.get('value', 'No value')}", "green")
            
            # Add search summary if available
            if analysis_result.get("search_summary"):
                search_info = {
                    "query": "LLM analyzed search",
                    "summary": analysis_result["search_summary"],
                    "timestamp": time.time(),
                    "url": self._selenium_receiver.driver.current_url if self._selenium_receiver else ""
                }
                self._accumulated_info.add_search_result(search_info)
                utils.print_with_color(f"검색 요약 추가: {analysis_result['search_summary']}", "green")
            
            utils.print_with_color("누적 정보 업데이트 완료", "green")
            
        except Exception as e:
            utils.print_with_color(f"누적 정보 업데이트 실패: {e}", "red")
