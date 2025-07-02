# components/tab_regulation.py

import streamlit as st
import glob
import json
from utils.chat_regulation import ask_question
from utils.chat_common_functions import (
    save_chat_history, get_session_keys, initialize_session_state,
    clear_session_state, handle_project_change, display_chat_history,
    update_chat_history, handle_example_question, handle_user_input,
    reset_processing_state
)
from utils import c
from functools import lru_cache
import os
from datetime import datetime
import asyncio

# 캐시된 규제 데이터 로딩
@st.cache_data(ttl=300)  # 5분 TTL
def load_recent_regulation_data():
    """최신 크롤링 결과 파일 로드 - 캐시 적용"""
    try:
        # glob 패턴을 더 효율적으로 처리
        pattern = "./risk_federal_changes_*.json"
        json_files = glob.glob(pattern)
        
        if not json_files:
            return None
        
        # 파일 수정 시간 기준으로 정렬 (더 빠름)
        latest_file = max(json_files, key=os.path.getmtime)
        
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # 데이터 전처리를 여기서 수행
        for item in data:
            # HTML 변환을 미리 처리
            if 'summary_korean' in item:
                item['summary_html'] = item['summary_korean'].replace('\n', '<br>')
                
        return data
        
    except Exception as e:
        st.error(f"규제 데이터 로드 실패: {e}")
        return None

# 규제 데이터 필터링 및 페이지네이션
@st.cache_data(ttl=300)
def get_filtered_regulations(regulation_data, page_size=5, page_num=0):
    """규제 데이터 필터링 및 페이지네이션"""
    if not regulation_data:
        return []
    
    start_idx = page_num * page_size
    end_idx = start_idx + page_size
    return regulation_data[start_idx:end_idx]

def display_recent_regulations(regulation_data, max_items=5):
    """최근 규제 변경 내용을 카드 형태로 표시 - 최적화"""
    if not regulation_data:
        st.info("📋 표시할 규제 변경 내용이 없습니다.")
        return
        
    st.subheader("📋 최근 규제 변경")
    
    # 페이지네이션 적용
    items_to_show = get_filtered_regulations(regulation_data, max_items, 0)
    
    # 컨테이너를 사용해 한 번에 렌더링
    regulation_container = st.container()
    
    with regulation_container:
        for i, item in enumerate(items_to_show):
            # 미리 처리된 HTML 사용
            summary_html = item.get('summary_html', item.get('summary_korean', '').replace('\n', '<br>'))
            
            # 고유 키로 각 카드 식별
            with st.expander(f"📘 {item.get('title_korean', '제목 없음')}", expanded=(i == 0)):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**변경일:** {item.get('change_date', 'N/A')}")
                    
                with col2:
                    if item.get('url'):
                        st.link_button("🔗 원문 보기", item['url'])
                
                if summary_html:
                    st.markdown(f"""
                    <div style="margin-top:15px; padding:12px; background-color:#F0F2F5; border-radius:6px;">
                        <b>내용 요약:</b><br>
                        {summary_html}
                    </div>
                    """, unsafe_allow_html=True)
    
    st.markdown("---")

# 예시 질문 캐싱
@lru_cache(maxsize=1)
def get_regulation_questions():
    """규제 예시 질문 목록 - 캐시 적용"""
    return [
        "FDA 등록은 어떻게 하나요?", 
        "식품 첨가물 규정이 궁금해요.", 
        "미국 수출 시 필요한 서류는?",
        "의료기기 FDA 승인 절차는?",
        "화장품 성분 규제 사항은?"
    ]

# 모니터링 상태 관리
def init_monitoring_state():
    """모니터링 관련 세션 상태 초기화"""
    if "monitoring_in_progress" not in st.session_state:
        st.session_state.monitoring_in_progress = False
    if "last_monitoring_time" not in st.session_state:
        st.session_state.last_monitoring_time = None

def show_regulation_chat():
    """규제 전용 챗봇 - 최적화 버전"""
    st.info("""
    🤖 **AI 챗봇을 활용한 FDA 규제 관련 정보 분석 시스템**
    - 질문 시 관련 FDA 규제 가이드 정보 및 출처 URL 제공
    - 공식 사이트 데이터만을 활용한 신뢰성 높은 정보 
    - “대화 기록 저장” 버튼을 활용한 “분석 리포트 도우미” 탭에서의 자동 요약 완성 시스템
    """)
    
    chat_mode = "규제"
    session_keys = get_session_keys(chat_mode)
    
    # 세션 상태 초기화
    initialize_session_state(session_keys)
    init_monitoring_state()
    
    # 규제 전용 세션 상태 - 조건부 초기화
    if "recent_regulation_data" not in st.session_state:
        st.session_state.recent_regulation_data = load_recent_regulation_data()

    # 레이아웃 최적화 - 더 효율적인 컬럼 구성
    col_left, col_center, col_right = st.columns([1, 3, 1])
   
    with col_left:
        # 프로젝트 이름 입력
        project_name = st.text_input(
            "프로젝트 이름", 
            placeholder="규제 프로젝트명", 
            key="regulation_project_input",
            help="규제 모드 전용 프로젝트별 대화 기록"
        )
        
        # 프로젝트 변경 처리 최적화
        project_changed = handle_project_change(project_name, chat_mode, session_keys)
        if project_changed:
            st.rerun()
        elif project_name:
            st.success(f"✅ '{project_name}' 진행 중")
        
        # 버튼 상태 체크 최적화
        has_project_name = bool(project_name and project_name.strip())
        has_chat_history = bool(st.session_state[session_keys["chat_history"]])
        is_processing = st.session_state[session_keys["is_processing"]]
        
        # 저장 버튼
        save_disabled = not (has_project_name and has_chat_history) or is_processing
        if st.button("💾 대화 저장", key="regulation_save", 
                    use_container_width=True, disabled=save_disabled):
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
            elif not has_project_name:
                st.warning("⚠️ 프로젝트 이름을 입력해주세요.")
            else:
                st.warning("⚠️ 저장할 대화가 없습니다.")

        # 초기화 버튼
        clear_disabled = not (has_project_name and has_chat_history) or is_processing
        if st.button("🗑️ 대화 초기화", key="regulation_clear", 
                    disabled=clear_disabled, use_container_width=True):
            clear_session_state(session_keys)
            st.success("초기화 완료")
            st.rerun()
        
        # 모니터링 섹션
        st.markdown("규제 변경 모니터링")
        
        # 마지막 모니터링 시간 표시
        if st.session_state.last_monitoring_time:
            st.caption(f"마지막 업데이트: {st.session_state.last_monitoring_time}")
        
        # 모니터링 버튼 - 중복 실행 방지
        monitoring_disabled = st.session_state.monitoring_in_progress or is_processing
        if st.button("📡 모니터링 시작", key="regulation_monitoring", 
                    use_container_width=True, disabled=monitoring_disabled):
            
            st.session_state.monitoring_in_progress = True
            
            with st.spinner("FDA 최신 규제 정보 수집 중..."):
                try:
                    # 캐시 클리어 후 새로운 데이터 수집
                    st.cache_data.clear()
                    
                    # 모니터링 실행
                    c.main()
                    
                    # 결과 로드
                    regulation_data = load_recent_regulation_data()
                    if regulation_data:
                        st.session_state.recent_regulation_data = regulation_data
                        st.session_state.last_monitoring_time = datetime.now().strftime("%H:%M:%S")
                        st.success(f"📡 완료! {len(regulation_data)}건 수집")
                    else:
                        st.warning("수집된 데이터가 없습니다.")
                        
                except Exception as e:
                    st.error(f"❌ 모니터링 오류: {str(e)[:50]}...")
                finally:
                    st.session_state.monitoring_in_progress = False
                    st.rerun()

    with col_center:
        # 최근 규제 변경 내용 표시 - 조건부 렌더링
        if st.session_state.recent_regulation_data:
            with st.expander("📋 최근 규제 변경 내용", expanded=False):
                display_recent_regulations(st.session_state.recent_regulation_data)

        # 예시 질문 섹션 - 캐시된 데이터 사용
        with st.expander("💡 예시 질문", expanded=False):
            regulation_questions = get_regulation_questions()
            
            # 2열로 배치하여 공간 활용도 개선
            cols = st.columns(2)
            for i, question in enumerate(regulation_questions[:4]):  # 4개만 표시
                col_idx = i % 2
                with cols[col_idx]:
                    if st.button(
                        question, 
                        key=f"regulation_example_{i}", 
                        use_container_width=True, 
                        disabled=is_processing
                    ):
                        handle_example_question(question, session_keys)
                        st.rerun()

        # 대화 기록 표시
        chat_container = st.container()
        with chat_container:
            display_chat_history(session_keys)

        # 질문 처리 - 비동기 처리 시뮬레이션
        if st.session_state[session_keys["selected_question"]]:
            with st.chat_message("assistant"):
                with st.spinner("🏛️ 규제 데이터 분석 중..."):
                    try:
                        result = ask_question(
                            st.session_state[session_keys["selected_question"]], 
                            st.session_state[session_keys["langchain_history"]]
                        )
                        
                        answer = result.get("answer", "답변을 생성할 수 없습니다.")
                        
                        # 답변 출력
                        st.markdown(answer)
                        
                        # 히스토리 업데이트
                        update_chat_history(
                            st.session_state[session_keys["selected_question"]], 
                            answer, 
                            session_keys, 
                            result.get("chat_history", [])
                        )
                        
                        # 상태 리셋
                        reset_processing_state(session_keys)
                        
                        st.info("🏛️ 규제 AI 답변 완료")
                        
                    except Exception as e:
                        st.error(f"답변 생성 중 오류: {str(e)[:100]}...")
                        reset_processing_state(session_keys)
                    
                    st.rerun()

        # 사용자 입력 - 조건부 활성화
        if not is_processing:
            user_input = st.chat_input(
                "규제 관련 질문을 입력하세요...", 
                key="regulation_chat_input"
            )
            if user_input and user_input.strip():
                handle_user_input(user_input.strip(), session_keys)
                st.rerun()
        else:
            st.info("🔄 처리 중입니다. 잠시만 기다려주세요...")

    with col_right:
        pass

# 추가 최적화 함수들
@st.cache_data(ttl=3600)  # 1시간 캐시
def get_regulation_statistics():
    """규제 데이터 통계 정보"""
    data = load_recent_regulation_data()
    if not data:
        return {}
    
    return {
        "total_count": len(data),
        "latest_date": max(item.get('change_date', '') for item in data),
        "categories": len(set(item.get('category', 'unknown') for item in data))
    }

def preload_regulation_data():
    """앱 시작 시 규제 데이터 미리 로드"""
    if "regulation_preloaded" not in st.session_state:
        st.session_state.recent_regulation_data = load_recent_regulation_data()
        st.session_state.regulation_preloaded = True