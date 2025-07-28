# UFO 웹 자동화 가이드

## 개요

UFO에 Selenium을 활용한 웹 자동화 기능이 추가되었습니다. 이제 **LLM이 사용자의 요청을 분석하여 웹 관련 작업인지 판단**하고, 웹 자동화가 필요한 경우 자동으로 Selenium을 활용하여 웹 자동화를 수행할 수 있습니다.

## 시스템 구조

```
사용자 요청 → HostAgent (LLM이 웹 요청 판단) → Selenium 인스턴스 생성 → AppAgent (웹 액션 실행)
```

### 1. HostAgent의 역할
- **LLM이 사용자 요청을 분석하여 웹 관련 작업인지 판단**
- Selenium WebDriver 인스턴스 생성
- 웹페이지 정보 수집 (제목, URL, 클릭 가능한 요소들)
- 웹 자동화 계획 수립

### 2. AppAgent의 역할
- Selenium 명령 실행 (클릭, 텍스트 입력, 네비게이션 등)
- 웹 액션 결과 처리

## LLM 기반 웹 요청 판단

### 판단 방식
- **하드코딩된 키워드 기반이 아닌 LLM의 지능적 판단**
- LLM이 사용자 요청의 맥락을 이해하여 웹 자동화가 필요한지 결정
- 더 유연하고 정확한 웹 요청 감지

### LLM 판단 기준
LLM은 다음을 고려하여 웹 관련 요청인지 판단합니다:
- 사용자 요청의 맥락과 의도
- 웹 관련 작업의 필요성
- 데스크톱 UI 조작 vs 웹 자동화의 적합성

### 웹 자동화 활성화 조건
LLM이 Response 필드에서 다음 키워드들을 포함할 때 웹 자동화가 활성화됩니다:
- "웹 자동화", "웹 브라우저", "웹사이트", "브라우저"
- "웹 검색", "웹 폼", "웹 버튼"
- 기타 웹 관련 키워드들

## 지원하는 웹 액션

### 1. 네비게이션
```python
navigate_to_url(url="https://www.google.com")
```

### 2. 요소 클릭
```python
click_element(text="검색", element_type="button")
click_element(text="로그인", element_type="link")
```

### 3. 텍스트 입력
```python
input_text(text="검색어", selector="#search")
input_text(text="사용자명", selector="//input[@name='username']")
```

### 4. 페이지 정보 가져오기
```python
get_page_source()  # HTML 소스
get_clickable_elements()  # 클릭 가능한 요소들
```

## 사용 방법

### 1. 기본 사용법

UFO를 실행하고 웹 관련 요청을 하면 LLM이 자동으로 판단하여 Selenium을 활성화합니다:

```bash
python -m ufo.main
```

### 2. 예시 요청들

#### 웹사이트 방문
```
"구글에 가서 검색해줘"
```

#### 검색 기능
```
"구글에서 'UFO 프로젝트'를 검색해줘"
```

#### 폼 입력
```
"로그인 폼에 사용자명과 이메일을 입력해줘"
```

#### 버튼 클릭
```
"저장 버튼을 클릭해줘"
```

### 3. LLM 판단 예시

**웹 관련 요청 (자동화 활성화)**:
- "구글에서 검색해줘" → LLM이 "웹 자동화가 필요합니다"로 판단
- "웹사이트에 로그인해줘" → LLM이 "브라우저를 열고 웹 자동화를 수행해야 합니다"로 판단

**일반 데스크톱 요청 (자동화 비활성화)**:
- "파일 탐색기를 열어줘" → LLM이 데스크톱 UI 조작으로 판단
- "설정을 변경해줘" → LLM이 시스템 설정 조작으로 판단

## 테스트 방법

### 1. 로컬 HTML 파일 테스트

생성된 `test_web_automation.html` 파일을 브라우저에서 열고 UFO로 테스트해보세요:

```
"test_web_automation.html 파일을 열어서 검색 기능을 테스트해줘"
```

### 2. 실제 웹사이트 테스트

```
"구글에 가서 'UFO 프로젝트'를 검색해줘"
```

## 설정 파일

### config_dev.yaml 설정

```yaml
APP_API_PROMPT_ADDRESS: {
    "selenium_web": "ufo/prompts/apps/web/selenium_api.yaml",
    "web_automation": "ufo/prompts/apps/web/selenium_api.yaml",
    "chrome_selenium": "ufo/prompts/apps/web/selenium_api.yaml",
    "edge_selenium": "ufo/prompts/apps/web/selenium_api.yaml"
}
```

## 의존성

Selenium이 추가되었습니다:

```bash
pip install selenium==4.18.1
```

## 주의사항

1. **Chrome WebDriver**: Chrome 브라우저가 설치되어 있어야 합니다.
2. **헤드리스 모드**: 기본적으로 브라우저가 보이는 모드로 실행됩니다. 헤드리스 모드를 원하면 `selenium_webclient.py`에서 주석을 해제하세요.
3. **타임아웃**: 페이지 로딩 대기 시간은 10초로 설정되어 있습니다.
4. **에러 처리**: 웹 자동화 중 오류가 발생하면 적절한 에러 메시지가 표시됩니다.
5. **LLM 판단**: 웹 자동화 활성화는 LLM의 판단에 의존하므로, 명확한 웹 관련 요청을 해주세요.

## 확장 가능성

이 시스템은 다음과 같이 확장할 수 있습니다:

1. **더 많은 웹 액션**: 스크롤, 드래그 앤 드롭, 파일 업로드 등
2. **다중 브라우저 지원**: Firefox, Safari 등
3. **고급 선택자**: CSS 선택자, XPath 등
4. **대기 조건**: 명시적/암시적 대기 조건 추가
5. **스크린샷 기능**: 웹페이지 스크린샷 캡처
6. **LLM 판단 개선**: 더 정확한 웹 요청 감지를 위한 프롬프트 최적화

## 문제 해결

### Chrome WebDriver 오류
```
WebDriverManager를 사용하여 자동으로 드라이버를 다운로드하도록 수정할 수 있습니다.
```

### 요소를 찾을 수 없는 경우
```
더 정확한 선택자나 대기 시간을 조정해보세요.
```

### 페이지 로딩이 느린 경우
```
타임아웃 시간을 늘리거나 명시적 대기 조건을 추가하세요.
```

### 웹 자동화가 활성화되지 않는 경우
```
LLM이 웹 관련 요청으로 인식하지 못했을 수 있습니다. 더 명확한 웹 관련 키워드를 사용해보세요.
예: "웹사이트에 접속해서", "브라우저에서", "인터넷에서" 등
``` 