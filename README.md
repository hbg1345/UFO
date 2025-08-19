<h1 align="center">
  <b>INO</b>
</h1>

<br/>
🧑🏻‍🦱 손 하나 까딱하기 싫은 사람,<br/>
👵🏻 컴퓨터 사용이 익숙하지 않은 사람<br/>
을 위한 AI 컴퓨터 사용 도우미 **INO**를 소개합니다!
<br/>

<img width="1500" alt="main" src="https://github.com/user-attachments/assets/55e82c58-31c4-4dd5-9e26-268d348eaa9e" />
- 데스크탑 화면 오른쪽 아래에 있는 INO에게 도움을 요청해 보세요. <br/>
- INO의 위치를 옮기고 싶으면 캐릭터를 잡고 드래그하세요. <br/>
- INO는 웹 브라우저를 직접 조작하거나, 컴퓨터 사용 방법을 알려줄 수 있어요. <br/>

---

## ✨ 주요 기능 및 개선사항

### 🌐 향상된 웹 자동화
- **HTML 구조 분석**: 스크린샷에만 의존하던 기존 UFO와 달리, 웹 페이지의 HTML 구조를 분석하여 더 정확하고 효율적인 웹 자동화
- **Selenium 통합**: 지능형 요소 감지 기능이 있는 Selenium WebDriver를 사용한 고급 웹 자동화
- **스마트 요소 인식**: 시각적 요소 감지와 HTML 기반 요소 감지를 결합하여 더 나은 정확도 제공

### 🖥️ 사용자 친화적 GUI 인터페이스
- **현대적인 데스크톱 애플리케이션**: PyQt5로 구축된 직관적인 그래픽 사용자 인터페이스
- **실시간 상태 업데이트**: 자동화 진행 상황과 상태에 대한 시각적 피드백

### 🎤 음성 인식 및 음성 안내
- **음성-텍스트 변환**: 핸즈프리 작업을 위한 내장 음성 인식
- **자연어 처리**: 음성 명령을 처리하고 자동화 작업으로 변환

### 📚 컴퓨터 도움말
- **단계별 가이드**: 복잡한 컴퓨터 사용 방법을 안내하는 대화형 도움말 시스템
- **상호 작용**: 맥락을 인식하여 사용자의 질문에 답변

---

## 🚀 빠른 시작

### 🛠️ 1단계: 설치
myUFO는 **Windows OS >= 10**에서 실행되는 **Python >= 3.10**이 필요합니다. 다음 명령을 실행하여 설치하세요:

```powershell
# 저장소 복제
git clone https://github.com/hbg1345/UFO.git
cd myUFO

# 요구사항 설치
pip install -r requirements.txt
```

### ⚙️ 2단계: LLM 설정
템플릿을 복사하여 설정 파일을 생성하세요:

```powershell
copy ufo\config\config.yaml.template ufo\config\config.yaml
notepad ufo\config\config.yaml
```

HOST_AGENT와 APP_AGENT 모두에 대한 LLM 설정을 구성하세요:

#### OpenAI 설정
```yaml
VISUAL_MODE: True
API_TYPE: "openai"
API_BASE: "https://api.openai.com/v1/chat/completions"
API_KEY: "sk-your-api-key"
API_VERSION: "2024-02-15-preview"
API_MODEL: "gpt-4o"
```

### 🔐 2-1단계: API 키 설정
`.env` 파일에 다음 API 키들을 설정해야 합니다:

```powershell
# .env 파일 생성
notepad .env
```

`.env` 파일에 다음 내용을 추가하세요:

```env
# Google Cloud Speech-to-Text API 키
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google-credentials.json

# OpenAI API 키
OPENAI_API_KEY=your-openai-api-key
```

#### API 키 획득 방법:
- **Google Cloud Speech-to-Text**: [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성하고 Speech-to-Text API를 활성화한 후 서비스 계정 키를 다운로드
- **AssemblyAI**: [OpenAI 웹사이트](https://platform.openai.com/)에서 계정을 생성하고 API 키 발급

### 🎉 3단계: 애플리케이션 실행

#### 옵션 1: GUI 인터페이스 (권장)
```powershell
python ufo/guitest.py
```

#### 옵션 2: 명령줄 인터페이스
```powershell
python -m ufo --task <your_task_name>
```

---

## 🔧 기존 UFO와의 주요 차이점

| 기능 | 기존 UFO | myUFO |
|------|----------|-------|
| **웹 자동화** | 스크린샷 기반만 | HTML 구조 + 스크린샷 분석 |
| **사용자 인터페이스** | 명령줄만 | 현대적 GUI |
| **음성 제어** | 없음 | 내장 음성 인식 |
| **도움말 시스템** | 없음 | 대화형 컨텍스트 인식 도움말 |
| **접근성** | 기술적 사용자 | 모든 수준의 사용자 친화적 |

---

## 📁 프로젝트 구조

```
UFO/
├── ufo/                    # 핵심 UFO 프레임워크
│   ├── agents/            # 에이전트 구현
│   ├── automator/         # 자동화 엔진
│   ├── config/            # 설정 파일
│   ├── guitest.py         # 메인 GUI 애플리케이션
│   ├── tts.py             # 텍스트-음성 변환 기능
│   ├── stt.py             # 음성-텍스트 변환 기능
│   ├── helper.py          # 도움말 시스템
│   ├── ufo.py             # UFO 메인 모듈
│   └── __main__.py        # UFO 실행 진입점
├── requirements.txt       # Python 의존성
├── WEB_AUTOMATION_GUIDE.md # 웹 자동화 가이드
├── README.md             # 이 파일
└── .env                  # 환경 변수 (API 키 등)
```

---

## 🎯 사용 예시

### 인터넷 사용

<img height="400" alt="ex1-1" src="https://github.com/user-attachments/assets/ababa9fd-7726-4e39-86d6-2cddcb646d17" />
<img height="400" alt="ex1-2" src="https://github.com/user-attachments/assets/3423b38d-2625-4424-990a-23b97c02501a" />

### 컴퓨터 도움말

<img height="400" alt="ex2-1" src="https://github.com/user-attachments/assets/2d097006-4645-498e-9c86-2da62142d6be" />
<img height="400" alt="ex2-2" src="https://github.com/user-attachments/assets/a5064a39-8421-4311-a07e-793fb0d4a6d4" />
<img height="400" alt="ex2-3" src="https://github.com/user-attachments/assets/e8f50415-1018-48bc-9acd-1b94ff9681cf" />
<img height="400" alt="ex2-4" src="https://github.com/user-attachments/assets/e14cbdbb-e41b-46ba-972e-4aa9af81da4c" />
<img height="400" alt="ex2-5" src="https://github.com/user-attachments/assets/fa65a4f5-7960-4747-a914-8482739b20a3" />

---

## 🛠️ 개발

### 사전 요구사항
- Python 3.10+
- Windows 10+
- Chrome 브라우저 (Selenium 자동화용)
- 마이크 (음성 인식용)

---

<p align="center"><sub>Microsoft의 UFO 프레임워크를 기반으로 한 향상된 AI 컴퓨터 사용 도우미</sub></p>

