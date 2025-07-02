# components/tab_export.py

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta 
import json
import shutil
import pandas as pd
import json
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from dotenv import load_dotenv
import os
from functools import lru_cache
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
import io
import pytz

load_dotenv()

# 캐시된 프로젝트 로딩
@st.cache_data(ttl=300)  # 5분 TTL
def _load_all_histories():
    """모든 대화 기록을 캐시와 함께 로드"""
    try:
        if not os.path.exists("chat_histories.json"):
            return {}
        with open("chat_histories.json", 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"파일 로드 실패: {e}")
        return {}

def show_export_helper():
    """수출 제안서 도우미 메인 함수 - 최적화 버전"""

    # 안내 메시지
    st.info("""
    **사용 방법:**
    미국 시장 수출용 상품 기획 단계에서 활용할 수 있는 문서 작성 도우미입니다.

    1. 챗봇과 질의응답 시 설정한 프로젝트명을 선택하세요.
    2. 좌측 빈 칸에 제품 정보 및 제안 의도를 입력하면 문서로 자동 저장됩니다.
    3. 우측 하단 버튼을 클릭하면 정리된 문서로 출력이 가능합니다.
    """)
    
    # 세션 상태 초기화 - 조건부
    init_session_state()

    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("**1️⃣ 정보 입력**")
        show_basic_info_form()
    
    with col2:
        st.markdown("**2️⃣ 분석 리포트 예시사진**")
        render_guide_section()

def init_session_state():
    """세션 상태 초기화 - 최적화"""
    defaults = {
        "export_data": {},
        "report_generated": False,
        "selected_template_data": "기본 제안서",
        "show_summary_area": False,
        "summary_content": "",
        "ai_processing": False  # AI 처리 상태 추가
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def render_guide_section():
    """가이드 이미지 및 엑셀 버튼 섹션"""
    try:
        st.image('./가이드.png')
    except FileNotFoundError:
        st.warning("이미지 파일을 찾을 수 없습니다.")
    except Exception as e:
        st.error(f"이미지 로드 오류: {e}")
    
    st.markdown("---")
    add_excel_export_button()

def get_available_projects():
    """저장된 프로젝트 목록을 가져오는 함수 - 프로젝트명만 추출"""
    try:
        all_histories = _load_all_histories()
        
        # 프로젝트명만 추출 (모드 부분 제거)
        project_names = set()
        for project_key in all_histories.keys():
            # 마지막 언더스코어로 구분하여 프로젝트명 추출
            if '_' in project_key:
                # 마지막 '_'를 기준으로 분리
                parts = project_key.rsplit('_', 1)
                if len(parts) == 2 and parts[1] in ['규제', '리콜사례']:
                    project_names.add(parts[0])
            else:
                # 언더스코어가 없는 경우 전체를 프로젝트명으로 간주
                project_names.add(project_key)
        
        return sorted(list(project_names))
    except Exception as e:
        st.error(f"프로젝트 목록 불러오기 실패: {e}")
        return []

def load_project_chat_history(project_name):
    """특정 프로젝트의 통합 채팅 히스토리 불러오기"""
    try:
        all_histories = _load_all_histories()
        
        # 해당 프로젝트의 모든 모드 데이터 수집
        regulation_history = []
        recall_history = []
        
        # 규제 모드 데이터
        regulation_key = f"{project_name}_규제"
        if regulation_key in all_histories:
            regulation_data = all_histories[regulation_key]
            regulation_history = regulation_data.get("chat_history", [])
        
        # 리콜사례 모드 데이터
        recall_key = f"{project_name}_리콜사례"
        if recall_key in all_histories:
            recall_data = all_histories[recall_key]
            recall_history = recall_data.get("chat_history", [])
        
        # 두 히스토리를 합쳐서 반환 (시간순 정렬 가능)
        combined_history = regulation_history + recall_history
        
        return combined_history
        
    except Exception as e:
        st.error(f"프로젝트 히스토리 불러오기 실패: {e}")
        return []

def get_project_summary_info(project_name):
    """프로젝트의 요약 정보 반환"""
    try:
        all_histories = _load_all_histories()
        
        regulation_key = f"{project_name}_규제"
        recall_key = f"{project_name}_리콜사례"
        
        info = {
            "regulation_chats": 0,
            "recall_chats": 0,
            "last_updated": None,
            "modes": []
        }
        
        if regulation_key in all_histories:
            reg_data = all_histories[regulation_key]
            info["regulation_chats"] = len(reg_data.get("chat_history", [])) // 2
            info["modes"].append("규제")
            if reg_data.get("last_updated"):
                info["last_updated"] = reg_data["last_updated"]
        
        if recall_key in all_histories:
            recall_data = all_histories[recall_key]
            info["recall_chats"] = len(recall_data.get("chat_history", [])) // 2
            info["modes"].append("리콜사례")
            # 더 최근 업데이트 시간 선택
            if recall_data.get("last_updated"):
                if not info["last_updated"] or recall_data["last_updated"] > info["last_updated"]:
                    info["last_updated"] = recall_data["last_updated"]
        
        return info
        
    except Exception as e:
        return {"regulation_chats": 0, "recall_chats": 0, "last_updated": None, "modes": []}

def show_basic_info_form():
    """기본 정보 입력 폼 - 최적화"""
    narrow_col, _ = st.columns([0.8, 0.2])

    with narrow_col:
        render_project_selector()
        st.markdown("---")
        render_product_info_section()
        render_background_section()
        render_risk_summary_section()

def render_project_selector():
    """프로젝트 선택 섹션"""
    st.markdown("**프로젝트 선택**")
    
    available_projects = get_available_projects()
    
    if available_projects:
        selected_project = st.selectbox(
            "저장된 프로젝트에서 선택",
            ["새 프로젝트"] + available_projects,
            key="project_selector",
            help="기존 프로젝트를 선택하여 규제/리콜사례 모든 Q&A 기록을 통합하여 불러옵니다."
        )
        
        if selected_project != "새 프로젝트":
            # 프로젝트 정보 표시 - 컬럼 중첩 방지
            project_info = get_project_summary_info(selected_project)
            
            # 세로로 배치하여 컬럼 중첩 방지
            # st.write(f"**규제 대화:** {project_info['regulation_chats']}건")
            # st.write(f"**리콜 대화:** {project_info['recall_chats']}건")
            # total_chats = project_info['regulation_chats'] + project_info['recall_chats']
            # st.write(f"**총 대화:** {total_chats}건")
            
            # if project_info['modes']:
            #     st.info(f"**선택된 프로젝트:** {selected_project}  \n**포함 모드:** {', '.join(project_info['modes'])}")
    else:
        st.info("저장된 프로젝트가 없습니다. 채팅 탭에서 대화 후 저장해주세요.")
        selected_project = "새 프로젝트"

def render_product_info_section():
    """제품 정보 입력 섹션"""
    st.markdown("**제품 정보**")
    
    # 컬럼 중첩 방지 - 세로로 배치
    product_name = st.text_input(
        "제품명", 
        placeholder="단백질 에너지바", 
        key="product_name"
    )
    
    target_market = st.text_input(
        "타겟층", 
        placeholder="30대 여성", 
        key="target_name"
    )

def render_background_section():
    """추진배경 입력 섹션"""
    st.markdown("**추진배경**")
    
    # 플레이스홀더 텍스트 단축
    placeholder_text = """시장 분석, 경쟁사 내용을 입력하세요.

예시) 미국 내 30대 여성을 중심으로 고단백 식품에 대한 수요가 크게 늘고 있으며, 2022년부터 2024년까지 단백질 간식은 연평균 9%의 성장률을 기록하고 있습니다...

(상세한 시장 분석 및 경쟁사 정보 입력)"""
    
    background = st.text_area(
        "제안 의도",
        placeholder=placeholder_text,
        height=350,  # 높이 조정
        key="background"
    )

def render_risk_summary_section():
    """규제 리스크 요약 섹션"""
    st.markdown("**규제 리스크 요약**")
    
    selected_project = st.session_state.get("project_selector", "새 프로젝트")
    
    # 버튼 텍스트 동적 생성
    if selected_project != "새 프로젝트":
        project_info = get_project_summary_info(selected_project)
        total_chats = project_info['regulation_chats'] + project_info['recall_chats']
        button_text = f"'{selected_project}' 프로젝트 Q&A 분석"
    else:
        button_text = "현재 세션 Q&A 내용 불러오기"

    # AI 처리 상태에 따른 버튼 비활성화
    button_disabled = st.session_state.get("ai_processing", False)
    
    if st.button(button_text, disabled=button_disabled):
        process_qa_analysis(selected_project)

def process_qa_analysis(selected_project):
    """Q&A 분석 처리 - 분리된 함수"""
    st.session_state.ai_processing = True
    st.session_state.show_summary_area = True
    
    try:
        # 프로젝트 데이터 로드
        if selected_project != "새 프로젝트":
            chat_history = load_project_chat_history(selected_project)
            if not chat_history:
                st.warning(f"'{selected_project}' 프로젝트에 대화 기록이 없습니다.")
                return
        else:
            chat_history = st.session_state.get("chat_history", [])
        
        if not chat_history:
            st.warning("⚠️ 불러올 대화 기록이 없습니다. 먼저 채팅 탭에서 대화를 진행해주세요.")
            return
        
        # Q&A 텍스트 생성
        qa_text = generate_qa_text(chat_history)
        
        if qa_text:
            # AI 분석 수행
            perform_ai_analysis(qa_text, selected_project)
        
    except Exception as e:
        st.error(f"❌ 분석 처리 중 오류: {e}")
    finally:
        st.session_state.ai_processing = False
        st.rerun()

def generate_qa_text(chat_history):
    """채팅 히스토리에서 Q&A 텍스트 생성"""
    qa_text = ""
    for i in range(0, len(chat_history), 2):
        if i + 1 < len(chat_history):
            question = chat_history[i]["content"]
            answer = chat_history[i + 1]["content"]
            qa_text += f"질문: {question}\n답변: {answer}\n\n"
    return qa_text

@st.cache_data(ttl=1800)  # 30분 캐시
def perform_ai_analysis_cached(qa_text, openai_api_key):
    """AI 분석 수행 - 캐시 적용"""
    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini", 
            temperature=0.3,
            openai_api_key=openai_api_key
        )
        
        # 통합 분석 프롬프트 (단일 요청으로 최적화)
        analysis_prompt = f"""
다음 Q&A 대화들을 분석하여 규제 및 리콜사례 관련 내용을 요약해주세요.

분석 요구사항:
1. 규제 관련 내용 (FDA 규정, 법령, 허가, 등록, 라벨링 등)
2. 리콜사례 관련 내용 (제품 리콜, 회수, 안전 경고 등)

각 카테고리별로 3-4문장으로 핵심 내용을 요약하고, 해당 내용이 없는 경우 "관련 내용 없음"으로 표시해주세요.

응답 형식:
📋 **규제 관련 요약**
[규제 관련 요약 내용]

🚨 **리콜사례 요약**
[리콜사례 관련 요약 내용]

Q&A 내용:
{qa_text}
"""
        
        response = llm.invoke([HumanMessage(content=analysis_prompt)])
        final_summary = response.content.strip()
        
        # URL 및 불필요한 내용 제거
        import re
        final_summary = re.sub(r'https?://[^\s]+', '', final_summary)
        final_summary = re.sub(r'📎.*?출처:.*', '', final_summary, flags=re.DOTALL)
        
        return final_summary
        
    except Exception as e:
        return f"AI 분석 실패: {str(e)}"

def perform_ai_analysis(qa_text, selected_project):
    """AI 분석 수행"""
    with st.spinner("🤖 AI가 대화 내용을 통합 분석하고 있습니다..."):
        try:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                st.error("OpenAI API 키가 설정되지 않았습니다.")
                return
            
            # 캐시된 AI 분석 수행
            final_summary = perform_ai_analysis_cached(qa_text, openai_api_key)
            st.session_state.summary_content = final_summary
            
            # 성공 메시지
            if selected_project != "새 프로젝트":
                project_info = get_project_summary_info(selected_project)
                total_chats = project_info['regulation_chats'] + project_info['recall_chats']
                st.success(f"✅ '{selected_project}' 프로젝트의 {total_chats}건 Q&A를 성공적으로 분석했습니다!")
            else:
                st.success("✅ 현재 세션의 Q&A를 성공적으로 분석했습니다!")
                
        except Exception as e:
            st.error(f"❌ AI 분석 중 오류: {e}")
            st.session_state.summary_content = f"분석 실패: {e}"

# 요약 내용 표시 섹션을 show_basic_info_form() 끝에 추가
def render_summary_display():
    """요약 내용 표시"""
    if st.session_state.get("show_summary_area", False):
        st.markdown("### 📊 통합 대화 분석 결과")
        
        edited_summary = st.text_area(
            "📝 규제/리콜 통합 분석 요약 (편집 가능)", 
            value=st.session_state.get("summary_content", ""), 
            placeholder="Q&A 내용을 불러오면 규제/리콜사례를 통합하여 분석 요약됩니다.",
            height=400,
            key="summary_editor",
            help="AI가 규제/리콜사례 모든 대화를 통합 분석한 요약입니다. 필요시 직접 편집 가능합니다."
        )
        
        # 편집된 내용 자동 저장
        if edited_summary != st.session_state.get("summary_content", ""):
            st.session_state.summary_content = edited_summary

# show_basic_info_form 함수 끝에 추가
def show_basic_info_form():
    """기본 정보 입력 폼 - 최적화"""
    narrow_col, _ = st.columns([0.8, 0.2])

    with narrow_col:
        render_project_selector()
        st.markdown("---")
        render_product_info_section()
        render_background_section()
        render_risk_summary_section()
        render_summary_display()  # 요약 표시 추가

def get_korean_datetime():
    """한국 시간대 기준 현재 날짜/시간 반환"""
    try:
        # 한국 시간대 설정
        korean_tz = pytz.timezone('Asia/Seoul')
        
        # UTC 현재 시간을 한국 시간으로 변환
        utc_now = datetime.utcnow()
        utc_now = pytz.utc.localize(utc_now)
        korean_now = utc_now.astimezone(korean_tz)
        
        return korean_now
    except:
        # pytz가 없거나 오류 시 UTC+9 수동 계산
        utc_now = datetime.utcnow()
        korean_now = utc_now + timedelta(hours=9)
        return korean_now

def create_excel_report():
    """openpyxl을 사용한 엑셀 리포트 생성"""
    try:
        template_path = './components/genai_rpa.xlsx'
        
        # 한국 시간 기준으로 날짜 생성
        korean_now = get_korean_datetime()
        timestamp = korean_now.strftime('%Y%m%d_%H%M%S')
        current_date = korean_now.strftime('%Y년 %m월 %d일')
        
        # 템플릿 파일이 없는 경우 새로 생성
        if not os.path.exists(template_path):
            return create_excel_report_from_scratch(timestamp, current_date)

        output_filename = f"분석리포트_{timestamp}.xlsx"

        # 파일 복사
        shutil.copy(template_path, output_filename)

        # openpyxl로 엑셀 처리
        wb = load_workbook(output_filename)
        ws = wb.active  # 첫 번째 워크시트 선택
        
        # 데이터 입력 (셀 주소는 템플릿에 맞게 조정)
        ws['E8'] = st.session_state.get("product_name", "")
        ws['E10'] = st.session_state.get("target_name", "")
        ws['E12'] = st.session_state.get("background", "")
        ws['E19'] = st.session_state.get("summary_content", "")
        ws['J6'] = current_date  # 한국 시간 기준 날짜
        ws['C4'] = f"{st.session_state.get('product_name', '')} 요약 리포트"

        # 파일 저장
        wb.save(output_filename)
        wb.close()
        
        return True, output_filename

    except Exception as e:
        return False, f"엑셀 파일 생성 중 오류: {str(e)}"

def create_excel_report_from_scratch(timestamp=None, current_date=None):
    """템플릿이 없을 때 처음부터 엑셀 리포트 생성 - 시간대 수정"""
    try:
        from openpyxl import Workbook
        
        # 한국 시간 기준으로 날짜 생성 (파라미터가 없을 경우)
        if not timestamp or not current_date:
            korean_now = get_korean_datetime()
            timestamp = korean_now.strftime('%Y%m%d_%H%M%S')
            current_date = korean_now.strftime('%Y년 %m월 %d일')
        
        output_filename = f"분석리포트_{timestamp}.xlsx"
        
        # 새 워크북 생성
        wb = Workbook()
        ws = wb.active
        ws.title = "수출 제안서 분석 리포트"
        
        # 스타일 정의
        header_font = Font(name='맑은 고딕', size=14, bold=True)
        title_font = Font(name='맑은 고딕', size=16, bold=True)
        normal_font = Font(name='맑은 고딕', size=10)
        
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        
        # 제목 및 헤더 설정
        ws['A1'] = "수출 제안서 분석 리포트"
        ws['A1'].font = title_font
        ws.merge_cells('A1:J1')
        
        ws['A2'] = f"생성일: {current_date}"  # 한국 시간 기준 날짜
        ws['A2'].font = normal_font
        
        # 제품 정보 섹션
        row = 4
        ws[f'A{row}'] = "📦 제품 정보"
        ws[f'A{row}'].font = header_font
        ws[f'A{row}'].fill = header_fill
        ws.merge_cells(f'A{row}:J{row}')
        
        row += 1
        ws[f'A{row}'] = "제품명:"
        ws[f'B{row}'] = st.session_state.get("product_name", "")
        
        row += 1
        ws[f'A{row}'] = "타겟층:"
        ws[f'B{row}'] = st.session_state.get("target_name", "")
        
        # 추진 배경 섹션
        row += 2
        ws[f'A{row}'] = "🎯 추진 배경"
        ws[f'A{row}'].font = header_font
        ws[f'A{row}'].fill = header_fill
        ws.merge_cells(f'A{row}:J{row}')
        
        row += 1
        background_text = st.session_state.get("background", "")
        ws[f'A{row}'] = background_text
        ws.merge_cells(f'A{row}:J{row+5}')  # 배경 설명을 위한 큰 셀
        ws[f'A{row}'].alignment = Alignment(wrap_text=True, vertical='top')
        
        # 규제 리스크 요약 섹션
        row += 7
        ws[f'A{row}'] = "⚠️ 규제 리스크 요약"
        ws[f'A{row}'].font = header_font
        ws[f'A{row}'].fill = header_fill
        ws.merge_cells(f'A{row}:J{row}')
        
        row += 1
        summary_text = st.session_state.get("summary_content", "")
        ws[f'A{row}'] = summary_text
        ws.merge_cells(f'A{row}:J{row+10}')  # 요약을 위한 큰 셀
        ws[f'A{row}'].alignment = Alignment(wrap_text=True, vertical='top')
        
        # 열 너비 조정
        ws.column_dimensions['A'].width = 15
        for col in ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']:
            ws.column_dimensions[col].width = 12
        
        # 파일 저장
        wb.save(output_filename)
        wb.close()
        
        return True, output_filename
        
    except Exception as e:
        return False, f"엑셀 파일 생성 중 오류: {str(e)}"

def add_excel_export_button():
    """엑셀 내보내기 버튼 - openpyxl 버전"""
    
    # 필수 데이터 체크
    required_fields = ["product_name", "target_name", "background"]
    has_required_data = all(st.session_state.get(field, "") for field in required_fields)
    
    # 처리 상태 체크
    is_processing = st.session_state.get("ai_processing", False)
    button_disabled = not has_required_data or is_processing
    
    if not has_required_data:
        st.warning("⚠️ 제품명, 타겟층, 추진배경을 모두 입력해주세요.")
    
    if is_processing:
        st.info("🔄 AI 분석 처리 중입니다...")
    
    # 엑셀 생성 버튼
    if st.button(
        "📊 통합 분석 리포트 생성 (Excel)", 
        use_container_width=True,
        disabled=button_disabled,
        help="입력된 정보와 통합 분석 결과를 바탕으로 엑셀 리포트를 생성합니다."
    ):
        with st.spinner("📝 엑셀 리포트 생성 중..."):
            success, result = create_excel_report()
            
            if success:
                st.success(f"✅ 리포트 생성 완료!")
                st.info(f"📁 파일명: {result}")
                
                # 다운로드 버튼
                try:
                    with open(result, "rb") as file:
                        st.download_button(
                            label="📥 엑셀 파일 다운로드",
                            data=file.read(),
                            file_name=result,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    
                    # 임시 파일 정리
                    try:
                        os.remove(result)
                    except:
                        pass
                        
                except Exception as e:
                    st.error(f"다운로드 준비 중 오류: {e}")
            else:
                st.error(f"❌ {result}")

# 기타 함수들은 기존 코드 유지하되 필요시 최적화
def show_product_analysis():
    """제품 분석 섹션 - 기존 코드 유지"""
    pass

def show_report_generation():
    """제안서 생성 섹션 - 기존 코드 유지"""
    pass

def show_results_section():
    """결과 표시 섹션 - 기존 코드 유지"""
    pass
