![image](https://github.com/user-attachments/assets/fa2511b4-ce8e-4274-ae7e-6b8d2910c6f4)```
risk_streamlit_app/
├── main.py
├── components/
│   ├── __init__.py
│   ├── tab_tableau.py
│   ├── tab_news.py
│   ├── tab_regulation.py
│   ├── tab_recall.py
│   └── tab_export.py
│   └── genai_rpa.xlsx
├── utils/
│   └── data_loader.py
│   └── chat_common_functions.py
│   └── chat_regulation.py
│   └── chat_recall.py
│   └── fda_realtime_crawler.py
│   └── google_crawler.py
│   └── c.py
└── requirements.txt
└── runtime.txt
└── packages.txt
└── 가이드.png
```


| 폴더명           | 설명                                                                                                                                                  |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `components/` | 탭 단위 Streamlit **UI를 구성**하는 각 탭의 코드를 담는 폴더.<br>각 `.py` 파일은 하나의 탭 역할을 하며, `risk.py`에서 <br>`from components.tab_dash import run_dash`처럼 해당 탭을 호출하여 실행합니다. |
| `utils/`      | Streamlit **UI와 분리된** 데이터 처리/로직/크롤링/GPT 응답생성 등의 **기능**이 들어가는 폴더.<br>Streamlit 화면에 직접 출력되지 않는 백엔드 기능들을 담당합니다.                                        |

| 파일명                        | 설명                                                                                            |
| -------------------------- | --------------------------------------------------------------------------------------------- |
| `main.py`                  | Streamlit **메인 실행 파일**. 모든 탭을 로딩하고 화면에 렌더링하는 진입점                                              |
|                            |                                                                                                                   |
| `__init__.py`              | `components` 폴더를 모듈로 인식시키는 역할.<br>공통 유틸 함수가 필요한 경우 이 파일에 작성해도 되지만, 비워두는 것을 추천                 |
| `tab_tableau.py`           | 시장 동향 시각화 (Tableau)                                                                           |
| `tab_news.py`              | 신문 기사 요약 & 신문 기사                                                                              |
| `tab_regulation.py`        | FDA 규제 모드 챗봇                                                                                  |
| `tab_recall.py`            | 리콜 사례 모드 챗봇                                                                                   |
| `tab_export.py`            | 분석 리포트 도우미                                                                                    |
| `genai_rpa.xlsx`           | 엑셀 템플릿                                                                                        |
|                            |                                                                                                   |
| `data_loader.py`           | Streamlit 앱 실행 시 필요한 데이터 파일(`data.zip`)을 자동으로 다운로드하고 압축 해제해주는 초기 설정 코드                        |
| `chat_common_functions.py` | 저장/로드 함수들, LangChain 히스토리 변환, 세션 상태 관리 유틸리티, 공통 검증 함수들                                        |
| `chat_regulation.py`       | 규제 모드 챗봇 기능                                                                                   |
| `chat_recall.py`           | 리콜 사례 챗봇 기능                                                                                   |
| `fda_realtime_crawler.py`  | 리콜 사례 추가 업데이트 내용 크롤링을 위한 함수                                                                   |
| `google_crawler.py`        | 구글 뉴스 RSS를 활용해 특정 키워드의 관련된 FDA 리콜 뉴스를 검색하고,<br>본문 내용을 추출한 뒤, 리콜 관련 여부를 판단해 포맷된 뉴스 정보를 반환하는 모듈 |
| `c.py`                     | eCFR 크롤링 + 번역 + 요약                                                                            |
|                            |                                                                                                     |
| `requirements.txt`         | pip으로 설치할 Python 패키지 설치 목록                                                                    |
| `runtime.txt`              | Python 버전 지정 (예: `python-3.10`)                                                               |
| `packages.txt`             | apt로 설치할 리눅스 시스템 패키지                                                                          |
| `가이드.png`                | `tab_export` 설명용 이미지                                                                          |
