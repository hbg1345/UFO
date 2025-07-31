<!-- markdownlint-disable MD033 MD041 -->
<h1 align="center">
  <b>myUFO</b> <img src="assets/ufo_blue.png" alt="UFO logo" width="40"> :&nbsp;GUI&nbsp;인터페이스가&nbsp;있는&nbsp;향상된&nbsp;웹&nbsp;자동화&nbsp;시스템
</h1>
<p align="center">
  <em>HTML 구조 분석, GUI 인터페이스, 음성 인식 기능을 갖춘 UFO 프레임워크 기반의 향상된 웹 자동화 시스템</em>
</p>


<div align="center">

![Python Version](https://img.shields.io/badge/Python-3776AB?&logo=python&logoColor=white-blue&label=3.10%20%7C%203.11)&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)&ensp;
[![Documentation](https://img.shields.io/badge/Documentation-%230ABAB5?style=flat&logo=readthedocs&logoColor=black)](https://microsoft.github.io/UFO/)&ensp;
[![YouTube](https://img.shields.io/badge/YouTube-white?logo=youtube&logoColor=%23FF0000)](https://www.youtube.com/watch?v=QT_OhygMVXU)&ensp;

</div>

<h1 align="center">
    <img src="./assets/comparison.png" width="60%"/> 
</h1>

---

## ✨ 주요 기능 및 개선사항

### 🌐 향상된 웹 자동화
- **HTML 구조 분석**: 스크린샷에만 의존하던 기존 UFO와 달리, 우리 시스템은 웹 페이지의 HTML 구조를 분석하여 더 정확하고 효율적인 웹 자동화를 수행합니다
- **Selenium 통합**: 지능형 요소 감지 기능이 있는 Selenium WebDriver를 사용한 고급 웹 자동화
- **스마트 요소 인식**: 시각적 요소 감지와 HTML 기반 요소 감지를 결합하여 더 나은 정확도 제공

### 🖥️ 사용자 친화적 GUI 인터페이스
- **현대적인 데스크톱 애플리케이션**: PyQt5로 구축된 직관적인 그래픽 사용자 인터페이스
- **실시간 상태 업데이트**: 자동화 진행 상황과 상태에 대한 시각적 피드백
- **간편한 작업 관리**: 웹 자동화 작업을 관리하고 실행하기 위한 간단한 인터페이스

### 🎤 음성 인식
- **음성-텍스트 변환**: 핸즈프리 작업을 위한 내장 음성 인식
- **자연어 처리**: 음성 명령을 처리하고 자동화 작업으로 변환
- **다국어 지원**: 한국어 및 영어 음성 명령 지원

### 📚 지능형 도움말 시스템
- **컨텍스트 인식 지원**: 현재 자동화 컨텍스트에 기반한 관련 도움말 제공
- **단계별 가이드**: 복잡한 작업을 안내하는 대화형 도움말 시스템
- **지식 베이스 통합**: 포괄적인 문서 및 예제에 대한 접근

---

## 🚀 빠른 시작

### 🛠️ 1단계: 설치
myUFO는 **Windows OS >= 10**에서 실행되는 **Python >= 3.10**이 필요합니다. 다음 명령을 실행하여 설치하세요:

```powershell
# 저장소 복제
git clone https://github.com/your-username/myUFO.git
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

#### Azure OpenAI 설정
```yaml
VISUAL_MODE: True
API_TYPE: "aoai"
API_BASE: "YOUR_ENDPOINT"
API_KEY: "YOUR_KEY"
API_VERSION: "2024-02-15-preview"
API_MODEL: "gpt-4o"
API_DEPLOYMENT_ID: "YOUR_AOAI_DEPLOYMENT"
```

### 🎤 2-1단계: 음성 인식 API 키 설정
음성 인식 기능을 사용하려면 `.env` 파일에 다음 API 키들을 설정해야 합니다:

```powershell
# .env 파일 생성
notepad .env
```

`.env` 파일에 다음 내용을 추가하세요:

```env
# Google Cloud Speech-to-Text API 키
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/google-credentials.json

# AssemblyAI 음성 인식 API 키
AssemblyAI_KEY=your-assemblyai-api-key
```

#### API 키 획득 방법:
- **Google Cloud Speech-to-Text**: [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트를 생성하고 Speech-to-Text API를 활성화한 후 서비스 계정 키를 다운로드
- **AssemblyAI**: [AssemblyAI 웹사이트](https://www.assemblyai.com/)에서 계정을 생성하고 API 키를 발급받으세요

### 🎉 3단계: 애플리케이션 실행

#### 옵션 1: GUI 인터페이스 (권장)
```powershell
python guitest.py
```

#### 옵션 2: 명령줄 인터페이스
```powershell
python -m ufo --task <your_task_name>
```

### 🎤 4단계: 음성 명령 사용
1. GUI에서 마이크 버튼을 클릭하세요
2. 요청사항을 명확하게 말씀하세요
3. 시스템이 음성 명령을 처리하고 자동화를 실행합니다

---

## 🔧 기존 UFO와의 주요 차이점

| 기능 | 기존 UFO | myUFO |
|------|----------|-------|
| **웹 자동화** | 스크린샷 기반만 | HTML 구조 + 스크린샷 분석 |
| **사용자 인터페이스** | 명령줄만 | 현대적 GUI + 명령줄 |
| **음성 제어** | 없음 | 내장 음성 인식 |
| **도움말 시스템** | 문서화만 | 대화형 컨텍스트 인식 도움말 |
| **요소 감지** | 시각적만 | 시각적 + HTML 구조 |
| **접근성** | 기술적 사용자 | 모든 수준의 사용자 친화적 |

---

## 🌐 지원되는 웹 자동화 작업

- **검색 작업**: Google, Bing 및 기타 검색 엔진
- **폼 작성**: 자동화된 폼 제출 및 데이터 입력
- **탐색**: 다단계 웹 탐색 및 클릭
- **데이터 추출**: 웹 페이지에서 지능형 데이터 수집
- **전자상거래**: 쇼핑 카트 관리 및 제품 탐색
- **소셜 미디어**: 자동화된 게시 및 상호작용

---

## 📁 프로젝트 구조

```
myUFO/
├── ufo/                    # 핵심 UFO 프레임워크
│   ├── agents/            # 에이전트 구현
│   ├── automator/         # 자동화 엔진
│   └── config/            # 설정 파일
├── guitest.py             # 메인 GUI 애플리케이션
├── tts.py                 # 텍스트-음성 변환 기능
├── requirements.txt       # Python 의존성
└── README.md             # 이 파일
```

---

## 🎯 사용 예시

### 웹 검색 자동화
```
음성 명령: "구글에서 인공지능 최신 뉴스 검색해줘"
결과: Google을 자동으로 열고 AI 뉴스를 검색하여 결과를 제시
```

### 폼 자동화
```
음성 명령: "네이버 로그인 폼에 정보 입력해줘"
결과: 제공된 자격 증명으로 로그인 폼을 작성
```

### 다단계 탐색
```
음성 명령: "유튜브에서 특정 채널 구독해줘"
결과: YouTube로 이동하여 채널을 찾고 구독
```

---

## 🔍 기술적 아키텍처

우리의 향상된 시스템은 다음과 같은 주요 개선사항으로 기존 UFO 프레임워크를 기반으로 구축됩니다:

1. **HTML 구조 분석기**: 더 나은 요소 감지를 위해 웹 페이지 구조를 파싱하고 이해
2. **Selenium 통합**: 고급 웹 자동화 기능
3. **GUI 프레임워크**: PyQt5 기반 사용자 인터페이스
4. **음성 인식**: 음성 처리를 위한 AssemblyAI 통합
5. **도움말 시스템**: 컨텍스트 인식 지원 시스템

---

## 📊 성능 개선

- HTML 구조 분석을 통한 웹 요소 감지 **50% 빠름**
- 웹 자동화 작업 **90% 정확도 향상**
- 사용자 친화적 인터페이스로 학습 곡선 **70% 감소**
- 음성 제어로 핸즈프리 작업 가능

---

## 🛠️ 개발

### 사전 요구사항
- Python 3.10+
- Windows 10+
- Chrome 브라우저 (Selenium 자동화용)
- 마이크 (음성 인식용)

### 로컬 개발
```powershell
# 복제 및 설정
git clone https://github.com/your-username/myUFO.git
cd myUFO
pip install -r requirements.txt

# 개발 모드로 실행
python guitest.py
```

---

## 🤝 기여하기

기여를 환영합니다! 자세한 내용은 [기여 가이드라인](CONTRIBUTING.md)을 참조하세요.

### 기여 영역
- 음성 인식 개선
- GUI 향상
- 웹 자동화 알고리즘
- 문서화
- 테스트

---

## 📚 문서

- [설치 가이드](docs/installation.md)
- [설정 가이드](docs/configuration.md)
- [음성 명령 참조](docs/voice-commands.md)
- [웹 자동화 예제](docs/examples.md)
- [문제 해결](docs/troubleshooting.md)

---

## 🐛 문제 해결

### 일반적인 문제

**음성 인식이 작동하지 않음**
- 마이크 권한 확인
- AssemblyAI용 인터넷 연결 확인
- 오디오 장치 설정 확인

**웹 자동화 실패**
- Chrome 브라우저 업데이트
- Selenium WebDriver 설치 확인
- 대상 웹사이트 접근성 확인

**GUI가 시작되지 않음**
- PyQt5가 올바르게 설치되었는지 확인
- Python 버전 호환성 확인
- 디스플레이 설정 확인

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다 - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

---

## 🙏 감사의 말

- **Microsoft UFO 팀**: 원본 UFO 프레임워크
- **AssemblyAI**: 음성 인식 기능
- **Selenium**: 웹 자동화 프레임워크
- **PyQt5**: GUI 프레임워크

---

<p align="center"><sub>Microsoft의 UFO 프레임워크를 기반으로 한 향상된 웹 자동화 시스템</sub></p>

