# main.py

import streamlit as st
import streamlit.components.v1 as components
from components.tab_tableau import create_market_dashboard
from components.tab_news import show_news
from components.tab_regulation import show_regulation_chat
from components.tab_recall import show_recall_chat
from components.tab_export import show_export_helper
from utils.data_loader import download_and_unzip_data

# 앱 시작 시 압축 해제 및 데이터 준비
download_and_unzip_data()


# 페이지 기본 설정
st.set_page_config(page_title="Risk Killer", page_icon="🔪", layout="wide")

# CSS 스타일
st.markdown("""
<style>
@keyframes glitterSweep {
  0% {background-position: -200% 0;}
  100% {background-position: 200% 0;}
}
            
/* 탭 내부 글자 크기 설정 */
[data-baseweb="tab-list"] button p {
    font-size: 20px !important;
}
            
/* 탭 여백 조절 */
[data-baseweb="tab"] {
    padding: 1rem 2rem !important;
}
            
/* 활성화된 탭 제목 강조 (선택사항) */
[data-baseweb="tab"][aria-selected="true"] p {
    font-size: 24px !important;
    font-weight: bold !important;
}

/* 기본 텍스트 크기 설정 */
html, body, [class*="css"] {
  font-size: 22px !important;
}

/* 제목 태그 (h1 ~ h4) 크기/굵기 설정 */
h1, h2, h3, h4 {a
  font-size: 26px !important;
  font-weight: bold !important;
}

/* 입력/버튼/라디오 글자 크기 설정 */
.stTextInput > div > input,
.stChatInput > div > textarea,
.stButton > button,
.stRadio > div {
  font-size: 17px !important;
}
            
/* st.alert 계열의 스타일을 커스터마이징 */
.stAlert > div {
    background-color: #E5E5E5;  /* 배경색 */
    color: #1F1F1F;  /* 텍스트 색상 */
}            

.main-header {
  text-align: center;
  padding: 2rem 0;
  border-radius: 10px;
  margin-bottom: 2rem;
  background: linear-gradient(60deg,
    transparent 0%,
    rgba(255,255,255,0.3) 20%,
    transparent 40%),
    #764ba2;
  background-size: 200% 100%;
  animation: glitterSweep 8s linear infinite;
  color: #FFFFFF;
}
.main-title {
  font-size: 3.5rem;
  font-weight: 800;
  margin-bottom: 0.5rem;
}
            
/* 선택된 탭 스타일 */
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    border-bottom: 3px solid #845AC0 !important;
    color: #845AC0 !important;
    font-weight: bold;
}

/* 탭 호버 효과 */
.stTabs [data-baseweb="tab-list"] button:hover {
    color: #333333 !important;
    background-color: #f8f9fa !important;
}

/* 움직이는 강조 바 색상 탭 색상과 통일 */
[data-baseweb="tab-highlight"] {
    background-color: #845AC0 !important;
}
</style>
""", unsafe_allow_html=True)

# 헤더 표시
st.markdown("""
<div class="main-header">
    <div class="main-title">Risk Killer</div>
</div>
""", unsafe_allow_html=True)

# 탭 구성
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📢 시장 동향", "🌏 해외 식품 뉴스","🤖 AI Q&A 챗봇","🔎 리콜사례 검토","📝 분석 리포트 도우미"])

with tab1:
  create_market_dashboard()

with tab2:
  show_news()

with tab3:
  show_regulation_chat()

with tab4:
  show_recall_chat()

with tab5:
  show_export_helper()
