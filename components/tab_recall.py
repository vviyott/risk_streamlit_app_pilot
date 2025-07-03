import streamlit as st
import plotly.express as px
import pandas as pd
from utils.chat_recall import ask_recall_question, recall_vectorstore
from utils.chat_common_functions import (
    save_chat_history, get_session_keys, initialize_session_state,
    clear_session_state, handle_project_change, display_chat_history,
    update_chat_history, handle_example_question, handle_user_input,
    reset_processing_state
)
from utils.fda_realtime_crawler import create_recall_visualizations
from functools import lru_cache
from datetime import datetime

# 리콜 관련 예시 질문
@lru_cache(maxsize=1)
def get_recall_questions():
    return [
        "미국에서 리콜된 한국 식품이 있나요?",
        "최근 리콜 사례의 주요 원인은?",
        "리콜을 피하려면 어떻게 해야 하나요?",
        "FDA 리콜 등급별 차이점은?",
        "자발적 리콜과 강제 리콜의 차이는?"
    ]

def init_recall_session_state(session_keys):
    """리콜 특화 세션 상태 초기화"""
    initialize_session_state(session_keys)
    
    if "recall_processing_start_time" not in st.session_state:
        st.session_state.recall_processing_start_time = None
    if "viz_data" not in st.session_state:
        st.session_state.viz_data = None
    if "show_charts" not in st.session_state:
        st.session_state.show_charts = False
    if st.session_state.viz_data is None:
        update_visualization_data()

def render_fixed_visualizations():
    """상단 고정 시각화 섹션"""
    if not st.session_state.show_charts or not st.session_state.viz_data:
        return
    
    # 고정 영역 컨테이너
    viz_container = st.container()
    
    with viz_container:
        st.markdown("### 📊 리콜 데이터 분석 대시보드")
        
        # 통계 요약 카드
        stats = st.session_state.viz_data.get('stats', {})
        if stats:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("총 리콜 건수", stats.get('total_recalls', 0))
            with col2:
                st.metric("월평균", f"{stats.get('avg_monthly', 0)}건")
            with col3:
                st.metric("실시간 데이터", f"{stats.get('realtime_data', 0)}건")
            with col4:
                st.metric("피크 월", stats.get('peak_month', 'N/A'))
        
        # 차트 섹션
        col1, col2 = st.columns(2)
        
        with col1:
            if 'reason_chart' in st.session_state.viz_data and st.session_state.viz_data['reason_chart']:
                st.plotly_chart(st.session_state.viz_data['reason_chart'], use_container_width=True)
            else:
                st.info("리콜 원인 데이터를 분석 중입니다...")
        
        with col2:
            if 'heatmap_chart' in st.session_state.viz_data and st.session_state.viz_data['heatmap_chart']:
                st.plotly_chart(st.session_state.viz_data['heatmap_chart'], use_container_width=True)
            else:
                st.info("히트맵 생성을 위한 데이터가 부족합니다.")
        
        st.markdown("---")  # 구분선

def update_visualization_data():
    """시각화 데이터 업데이트"""
    if recall_vectorstore is None:
        return
    
    try:
        viz_data = create_recall_visualizations(recall_vectorstore)
        if viz_data:
            st.session_state.viz_data = viz_data
            st.session_state.show_charts = True
    except Exception as e:
        st.error(f"시각화 데이터 업데이트 오류: {e}")

def render_sidebar_controls(project_name, chat_mode, session_keys):
    """사이드바 컨트롤 패널 렌더링"""
    # 프로젝트 변경 처리
    project_changed = handle_project_change(project_name, chat_mode, session_keys)
    if project_changed:
        st.rerun()
    elif project_name:
        st.success(f"✅ '{project_name}' 진행 중")
    
    st.markdown("---")
    
    # 기존 버튼들
    has_project_name = bool(project_name and project_name.strip())
    has_chat_history = bool(st.session_state[session_keys["chat_history"]])
    is_processing = st.session_state[session_keys["is_processing"]]
    
    # 저장 버튼
    save_disabled = not (has_project_name and has_chat_history) or is_processing
    if st.button("💾 대화 저장", disabled=save_disabled, use_container_width=True):
        if has_project_name and has_chat_history:
            with st.spinner("저장 중..."):
                success = save_chat_history(
                    project_name.strip(),
                    st.session_state[session_keys["chat_history"]],
                    st.session_state[session_keys["langchain_history"]],
                    chat_mode
                )
                if success:
                    st.success("✅ 저장 완료!")
                else:
                    st.error("❌ 저장 실패")
    
    # 초기화 버튼
    clear_disabled = not (has_project_name and has_chat_history) or is_processing
    if st.button("🗑️ 대화 초기화", disabled=clear_disabled, use_container_width=True):
        clear_session_state(session_keys)
        st.success("초기화 완료")
        st.rerun()
    
    return has_project_name, has_chat_history, is_processing

def render_example_questions(session_keys, is_processing):
    """예시 질문 섹션 렌더링"""
    with st.expander("💡 예시 질문", expanded=False):
        recall_questions = get_recall_questions()
        
        cols = st.columns(2)
        for i, question in enumerate(recall_questions[:4]):
            col_idx = i % 2
            with cols[col_idx]:
                short_question = question[:25] + "..." if len(question) > 25 else question
                
                if st.button(
                    short_question, 
                    key=f"recall_example_{i}", 
                    use_container_width=True, 
                    disabled=is_processing,
                    help=question
                ):
                    handle_example_question(question, session_keys)
                    st.rerun()

def render_chat_area(session_keys, is_processing):
    """메인 채팅 영역 렌더링"""
    # 상단 고정 시각화
    render_fixed_visualizations()
    
    # 예시 질문 섹션
    render_example_questions(session_keys, is_processing)
    
    # 대화 기록 표시
    chat_container = st.container()
    with chat_container:
        display_chat_history(session_keys)
    
    # 질문 처리
    if st.session_state[session_keys["selected_question"]]:
        if not st.session_state.recall_processing_start_time:
            st.session_state.recall_processing_start_time = datetime.now()
        
        with st.chat_message("assistant"):
            with st.spinner("🔍 실시간 데이터 수집 및 분석 중..."):
                try:
                    current_question = st.session_state[session_keys["selected_question"]]
                    
                    # 자동 크롤링이 포함된 질문 처리
                    result = ask_recall_question(
                        current_question, 
                        st.session_state[session_keys["langchain_history"]]
                    )
                    
                    # 챗봇 답변 표시
                    answer = result.get("answer", "답변을 생성할 수 없습니다.")
                    st.markdown(answer)
                    
                    # 처리 시간 표시
                    if st.session_state.recall_processing_start_time:
                        processing_time = (datetime.now() - st.session_state.recall_processing_start_time).total_seconds()
                        st.caption(f"⏱️ 처리 시간: {processing_time:.1f}초")
                    
                    # 실시간 데이터 정보 표시
                    if result.get("has_realtime_data"):
                        st.info(f"⚡ 실시간 데이터 {result.get('realtime_count', 0)}건 포함됨")
                    
                    # 시각화 데이터 업데이트 (고정 영역에 표시됨)
                    update_visualization_data()
                    
                    update_chat_history(
                        current_question, 
                        answer, 
                        session_keys, 
                        result.get("chat_history", [])
                    )
                    
                    reset_processing_state(session_keys)
                    st.session_state.recall_processing_start_time = None
                    
                    # 새 데이터가 추가되었으면 시각화 캐시 클리어
                    if result.get("realtime_count", 0) > 0:
                        st.cache_data.clear()
                    
                except Exception as e:
                    st.error(f"답변 생성 중 오류: {str(e)[:100]}...")
                    reset_processing_state(session_keys)
                    st.session_state.recall_processing_start_time = None
                    
                st.rerun()

def show_recall_chat():
    """리콜 전용 챗봇 - 자동 시각화 + 동향 분석 버전"""
    st.info("""
    🔎 **자동 실시간 리콜 분석 시스템** 
    - 질문 시 자동으로 최신 리콜 데이터 수집
    - 실시간 데이터 + 기존 DB 통합 분석
    - 자동 시각화 및 동향 분석 제공
    """)
    
    chat_mode = "리콜사례"
    session_keys = get_session_keys(chat_mode)
    
    # 세션 상태 초기화
    init_recall_session_state(session_keys)

    # 레이아웃
    col_left, col_center, col_right = st.columns([1, 3, 1])
   
    with col_left:
        # 프로젝트 이름 입력
        project_name = st.text_input(
            "프로젝트 이름", 
            placeholder="리콜 프로젝트명", 
            key="recall_project_input"
        )
        
        # 사이드바 컨트롤 렌더링
        has_project_name, has_chat_history, is_processing = render_sidebar_controls(
            project_name, chat_mode, session_keys
        )

    with col_center:
        # 메인 채팅 영역
        render_chat_area(session_keys, is_processing)
        
        # 사용자 입력
        if not is_processing:
            user_input = st.chat_input(
                "리콜 관련 질문을 입력하세요 (자동으로 최신 데이터 수집 및 분석)", 
                key="recall_chat_input"
            )
            if user_input and user_input.strip():
                if len(user_input.strip()) < 3:
                    st.warning("⚠️ 질문이 너무 짧습니다.")
                else:
                    handle_user_input(user_input.strip(), session_keys)
                    st.rerun()
        else:
            st.info("🔄 실시간 데이터 수집 및 분석 중입니다...")

    with col_right:
        pass
