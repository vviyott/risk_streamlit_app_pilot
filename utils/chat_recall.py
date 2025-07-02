# utils/chat_recall.py - 실시간 데이터 연동 버전

# sqlite 오류 우회용 (ChromaDB + Streamlit Cloud)
import sys
import pysqlite3

sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

import json
import os
from typing import TypedDict, List, Dict, Any, Optional
from functools import wraps
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_community.tools import DuckDuckGoSearchRun 
from langchain.tools import Tool
from langgraph.graph import StateGraph, START, END
from langchain_teddynote import logging # LangSmith 추적 활성화

load_dotenv() # 환경 변수 로드
logging.langsmith("LLMPROJECT") # LangSmith 추적 설정

class RecallState(TypedDict):
    """리콜 검색 시스템 상태"""
    question: str
    question_en: str
    recall_context: str
    recall_documents: List[Document]
    web_search_results: str
    final_answer: str
    search_method: str  # "recall_only", "web_only", "hybrid"
    needs_web_search: bool
    chat_history: List[HumanMessage | AIMessage]

def translate_to_english(korean_text: str) -> str:
    """한국어 텍스트를 영어로 번역"""
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
        prompt = f"Translate the following Korean text to English. Only return the translation:\n\n{korean_text}"
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        print(f"번역 오류: {e}")
        return korean_text

def load_recall_documents():
    """FDA 리콜 데이터 로드 - JSON 구조에 맞게 수정"""
    recall_file = "fda_recall.json"
    documents = []
    
    try:
        with open(recall_file, "r", encoding="utf-8") as f:
            recall_data = json.load(f)
            
            for item in recall_data:
                if isinstance(item, dict) and item.get("document_type") == "recall":
                    
                    # chunks를 개별 문서로 처리
                    chunks = item.get("chunks", [])
                    for i, chunk_content in enumerate(chunks):
                        
                        # 빈 내용 건너뛰기
                        if not chunk_content or len(chunk_content.strip()) < 30:
                            continue
                        
                        # 구조화된 컨텐츠 생성
                        structured_content = f"""
제목: {item.get('title', '')}
카테고리: {item.get('category', '')}
등급: {item.get('class', 'Unclassified')}
발효일: {item.get('effective_date', '')}
최종 업데이트: {item.get('last_updated', '')}

리콜 내용:
{chunk_content}
                        """.strip()
                        
                        # 메타데이터 생성 - 🆕 class 필드 추가
                        metadata = {
                            "document_type": item.get("document_type", ""),
                            "category": item.get("category", ""),
                            "class": item.get("class", "Unclassified"),  # 🆕 추가
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "effective_date": item.get("effective_date", ""),
                            "last_updated": item.get("last_updated", ""),
                            "chunk_index": str(i),
                            "source": "fda_recall_database"  # 🆕 출처 표시
                        }
                        
                        doc = Document(page_content=structured_content, metadata=metadata)
                        documents.append(doc)
        
        print(f"리콜 데이터 로드 완료: {len(documents)}개 청크")
        return documents
        
    except FileNotFoundError:
        print(f"리콜 파일을 찾을 수 없습니다: {recall_file}")
        return []
    except Exception as e:
        print(f"리콜 데이터 로드 오류: {e}")
        return []
    
# 웹 검색 래퍼 초기화 (더 안정적)
search_wrapper = DuckDuckGoSearchAPIWrapper(
    region="us-en",  # 미국 영어로 검색
    time="y",        # 최근 1년 결과 우선
    max_results=3    # 결과 개수 제한
)

def web_search_tool(query: str) -> str:
    """안정적인 웹 검색 함수"""
    try:
        results = search_wrapper.run(query)
        return results
    except Exception as e:
        print(f"웹 검색 오류: {e}")
        return f"웹 검색 중 오류가 발생했습니다: {e}"

def initialize_recall_vectorstore():
    """리콜 전용 벡터스토어 초기화 - 🆕 실시간 데이터 지원"""
    persist_dir = "./data/chroma_db_recall"
    
    # 기존 벡터스토어 확인
    if os.path.exists(persist_dir) and os.listdir(persist_dir):
        try:
            print("기존 리콜 벡터스토어를 로드합니다...")
            embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
            
            vectorstore = Chroma(
                persist_directory=persist_dir,
                embedding_function=embeddings,
                collection_name="FDA_recalls"
            )
            
            collection = vectorstore._collection
            if collection.count() > 0:
                print(f"리콜 벡터스토어 로드 완료 ({collection.count()}개 문서)")
                
                # 🆕 실시간 데이터 비율 체크
                try:
                    all_data = vectorstore.get()
                    metadatas = all_data.get('metadatas', [])
                    realtime_count = sum(1 for m in metadatas if m and m.get('source') == 'realtime_crawl')
                    total_count = len(metadatas)
                    print(f"실시간 데이터: {realtime_count}/{total_count}건")
                except:
                    pass
                
                return vectorstore
                
        except Exception as e:
            print(f"기존 리콜 벡터스토어 로드 실패: {e}")
    
    # 새 벡터스토어 생성
    try:
        print("새 리콜 벡터스토어를 생성합니다...")
        documents = load_recall_documents()
        
        if not documents:
            raise ValueError("로드된 리콜 문서가 없습니다.")
        
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            collection_name="FDA_recalls",
            persist_directory=persist_dir
        )
        
        print(f"리콜 벡터스토어 생성 완료 ({len(documents)}개 문서)")
        return vectorstore
        
    except Exception as e:
        print(f"리콜 벡터스토어 초기화 오류: {e}")
        raise

# 전역 벡터스토어 초기화
try:
    recall_vectorstore = initialize_recall_vectorstore()
except Exception as e:
    print(f"벡터스토어 초기화 실패: {e}")
    recall_vectorstore = None

# 웹 검색 도구 초기화
web_search = DuckDuckGoSearchRun()

def translation_node(state: RecallState) -> RecallState:
    """번역 노드"""
    question_en = translate_to_english(state["question"])
    
    return {
        **state,
        "question_en": question_en
    }

def recall_search_node(state: RecallState) -> RecallState:
    """리콜 데이터베이스 검색 + 최적화된 실시간 크롤링"""
    if recall_vectorstore is None:
        print("리콜 벡터스토어가 초기화되지 않았습니다.")
        return {
            **state,
            "recall_context": "",
            "recall_documents": [],
            "needs_web_search": True
        }
    
    try:
        # 🆕 최적화된 실시간 크롤링 수행 (벡터스토어 전달)
        from utils.fda_realtime_crawler import get_crawler, update_vectorstore_with_new_data
        
        print("🔍 벡터DB 기반 최적화된 실시간 수집 중...")
        crawler = get_crawler()
        
        # 벡터스토어를 전달하여 중복 체크 후 크롤링
        new_recalls = crawler.crawl_latest_recalls(days_back=15, vectorstore=recall_vectorstore)
        
        if new_recalls:
            added_count = update_vectorstore_with_new_data(new_recalls, recall_vectorstore)
            print(f"✅ 새 데이터 {len(new_recalls)}건 크롤링, {added_count}건 추가됨")
        else:
            print("💡 새로운 Food & Beverages 리콜 없음")
        
        # 기존 검색 로직 수행
        retriever = recall_vectorstore.as_retriever(search_kwargs={"k": 8})
        
        korean_docs = retriever.invoke(state["question"])
        english_docs = retriever.invoke(state["question_en"])
        
        all_docs = korean_docs + english_docs
        unique_docs = []
        seen_content = set()
        
        for doc in all_docs:
            content_key = doc.page_content[:100]
            if content_key not in seen_content:
                unique_docs.append(doc)
                seen_content.add(content_key)
        
        # 실시간 데이터 우선 정렬
        def prioritize_docs(doc):
            priority_score = 0
            # 실시간 데이터 우선
            if doc.metadata.get("source") == "realtime_crawl":
                priority_score += 1000
            # 날짜 기준 우선순위
            try:
                date_str = doc.metadata.get("effective_date", "1900-01-01")
                if len(date_str) >= 10:
                    year = int(date_str[:4])
                    month = int(date_str[5:7])
                    priority_score += year * 100 + month
            except:
                pass
            return priority_score
        
        unique_docs.sort(key=prioritize_docs, reverse=True)
        selected_docs = unique_docs[:6]  # 문서 수 증가
        context = "\n\n".join([doc.page_content for doc in selected_docs])
        
        # 실시간 데이터가 있으면 웹 검색 최소화
        realtime_docs_selected = [doc for doc in selected_docs if doc.metadata.get("source") == "realtime_crawl"]
        
        # 컨텍스트가 충분하거나 실시간 데이터가 2개 이상이면 웹 검색 생략
        needs_web_search = len(selected_docs) < 3 or len(context) < 300
        if len(realtime_docs_selected) >= 2:
            needs_web_search = False
        elif len(realtime_docs_selected) >= 1 and len(context) > 500:
            needs_web_search = False
        
        print(f"📊 검색 완료: 총 {len(selected_docs)}건 (⚡실시간: {len(realtime_docs_selected)}건, 📚기존: {len(selected_docs) - len(realtime_docs_selected)}건)")
        print(f"🌐 웹 검색 필요: {needs_web_search}")
        
        return {
            **state,
            "recall_context": context,
            "recall_documents": selected_docs,
            "needs_web_search": needs_web_search
        }
        
    except Exception as e:
        print(f"❌ 자동 크롤링 + 검색 오류: {e}")
        return {
            **state,
            "recall_context": "",
            "recall_documents": [],
            "needs_web_search": True
        }

def web_search_node(state: RecallState) -> RecallState:
    """개선된 웹 검색 노드 - 🆕 실시간 데이터 있을 때 제한적 검색"""
    if not state["needs_web_search"]:
        return {
            **state,
            "web_search_results": "",
            "search_method": "recall_only"
        }
    
    try:
        # 🆕 실시간 데이터가 있으면 간단한 검색만 수행
        realtime_docs = [doc for doc in state["recall_documents"] 
                        if doc.metadata.get("source") == "realtime_crawl"]
        
        if realtime_docs:
            # 실시간 데이터가 있으면 제한적 웹 검색
            search_queries = [f"FDA recall {state['question_en']}"]
            print("실시간 데이터 존재 - 제한적 웹 검색 수행")
        else:
            # 실시간 데이터가 없으면 전체 웹 검색
            search_queries = [
                f"FDA recall {state['question_en']}",
                f"food safety recall {state['question_en']}",
                f"{state['question_en']} recall 2024 2025"
            ]
            print("실시간 데이터 없음 - 전체 웹 검색 수행")
        
        all_results = []
        
        # 검색 수행
        for query in search_queries:
            try:
                result = web_search_tool(query)
                if result and "오류" not in result:
                    all_results.append(f"[검색어: {query}]\n{result}")
                    if realtime_docs:  # 실시간 데이터 있으면 첫 번째 결과만
                        break
            except Exception as e:
                print(f"검색어 '{query}' 실패: {e}")
                continue
        
        # 결과 결합
        web_results = "\n\n".join(all_results) if all_results else "검색 결과를 가져올 수 없습니다."
        
        # 검색 방법 결정
        if not state["recall_context"]:
            search_method = "web_only"
        else:
            search_method = "hybrid"
        
        print(f"웹 검색 완료: {len(web_results)}자")
        
        return {
            **state,
            "web_search_results": web_results,
            "search_method": search_method
        }
        
    except Exception as e:
        print(f"웹 검색 전체 실패: {e}")
        search_method = "recall_only" if state["recall_context"] else "error"
        
        return {
            **state,
            "web_search_results": f"웹 검색 실패: {e}",
            "search_method": search_method
        }

# ============= 프롬프트 템플릿 상수들 - 🆕 실시간 데이터 우선 반영 =============

# 1) FDA 리콜 DB만으로 답변
PROMPT_RECALL_ONLY = """
당신은 **FDA 리콜·회수(Recalls, Market Withdrawals, Safety Alerts) 전문 분석가**입니다.
아래 정보를 사용해 한국어로 명확하고 실무적인 리콜 브리핑을 작성하세요.  

📌 작성 규칙  
1. 반드시 제공된 "FDA Recall Database Information"만 근거로 삼습니다.  
2. **🆕 실시간 데이터(realtime_crawl)가 포함된 경우 우선 참고**하여 최신성을 강조합니다.
3. **리콜 사례가 1건 이상**이면 표 형식으로 정리합니다.  
   | 날짜 | 브랜드 | 제품 | 리콜 사유 | 등급 | 종료 여부 | 출처 |  
4. **출처 링크**가 있으면 셀에 하이퍼링크 형태로 넣습니다.  
5. **전혀 관련 없는 결과만 있거나 검색 결과가 없는 경우에만** "현재 데이터 기준 해당 사례 확인 불가"라고 명시하세요. 조금이라도 관련된 리콜 정보가 있다면 표로 정리해주세요.
6. 모든 표 아래에 3–5문장 규모로 **종합 요약**(기업 관점에서 위험도·예방조치·준수사항 등) 을 서술형으로 작성합니다.
7. **🆕 실시간 업데이트된 데이터가 포함된 경우 "⚡ 최신 업데이트 포함" 표시**를 추가합니다.

📝 질문:  
{question}

📒 FDA Recall Database Information:  
{recall_context}

🔽 위 규칙에 따라 답변을 작성하세요:
"""

# 2) 웹 검색 결과만으로 답변 (기존과 동일)
PROMPT_WEB_ONLY = """
역할: FDA 리콜 분석가  
조건: 아래 "Web Search Results"만 근거로 한국어 브리핑 작성  
규칙·형식은 PROMPT_RECALL_ONLY와 동일하게 적용  

📌 작성 규칙  
1. 반드시 제공된 "Web Search Results"만 근거로 삼습니다.  
2. **리콜 사례가 1건 이상**이면 표 형식으로 정리합니다.  
   | 날짜 | 브랜드 | 제품 | 리콜 사유 | 등급 | 종료 여부 | 원문 링크 |  
3. **출처 링크**가 있으면 셀에 하이퍼링크 형태로 넣습니다.  
4. **전혀 관련 없는 결과만 있거나 검색 결과가 없는 경우에만** "현재 데이터 기준 해당 사례 확인 불가"라고 명시하세요. 조금이라도 관련된 리콜 정보가 있다면 표로 정리해주세요.
5. 모든 표 아래에 3–5문장 규모로 **종합 요약**(기업 관점에서 위험도·예방조치·준수사항 등) 을 서술형으로 작성합니다.

📝 질문:  
{question}

🌐 Web Search Results:  
{web_results}

🔽 위 규칙에 따라 답변을 작성하세요:
"""

# 3) DB + 웹을 함께 활용 - 🆕 실시간 데이터 우선 강조
PROMPT_HYBRID = """
역할: FDA 리콜 분석가  
자료: "FDA Recall Database Information" 우선 → 부족하면 "Additional Web Search Results" 참고  
🆕 **실시간 크롤링 데이터(realtime_crawl)가 있으면 최우선 반영**  

📌 작성 규칙  
1. "FDA Recall Database Information"을 우선 근거로 사용하고, 부족한 정보는 "Additional Web Search Results"로 보완합니다.  
2. **🆕 실시간 데이터가 포함된 경우 해당 정보를 최우선으로 반영**하고 표에서 구분 표시합니다.
3. **리콜 사례가 1건 이상**이면 표 형식으로 정리합니다.  
   | 날짜 | 브랜드 | 제품 | 리콜 사유 | 등급 | 종료 여부 | 출처 | 🆕업데이트 |  
4. **실시간 데이터는 "⚡최신" 마크**를 추가하여 구분합니다.
5. **출처 링크**가 있으면 셀에 하이퍼링크 형태로 넣습니다.  
6. **전혀 관련 없는 결과만 있거나 검색 결과가 없는 경우에만** "현재 데이터 기준 해당 사례 확인 불가"라고 명시하세요. 조금이라도 관련된 리콜 정보가 있다면 표로 정리해주세요.
7. 모든 표 아래에 3–5문장 규모로 **종합 요약**(기업 관점에서 위험도·예방조치·준수사항 등) 을 서술형으로 작성합니다.
8. **실시간 업데이트 데이터가 포함된 경우 "⚡ 실시간 업데이트 포함" 안내**를 추가합니다.

📝 질문:  
{question}

📒 FDA Recall Database Information:  
{recall_context}

🌐 Additional Web Search Results:  
{web_results}

🔽 위 규칙에 따라 답변을 작성하세요:
"""

def answer_generation_node(state: RecallState) -> RecallState:
    """답변 생성 노드 - 🆕 실시간 데이터 우선 처리"""
    
    # 🆕 실시간 데이터 포함 여부 확인
    realtime_docs = [doc for doc in state["recall_documents"] 
                    if doc.metadata.get("source") == "realtime_crawl"]
    has_realtime_data = len(realtime_docs) > 0
    
    # 프롬프트 템플릿 및 변수 선택
    if state["search_method"] == "recall_only":
        prompt_template = PROMPT_RECALL_ONLY
        prompt_vars = {
            "question": state["question"],
            "recall_context": state["recall_context"]
        }
        
    elif state["search_method"] == "web_only":
        prompt_template = PROMPT_WEB_ONLY
        prompt_vars = {
            "question": state["question"],
            "web_results": state["web_search_results"]
        }
        
    else:  # hybrid
        prompt_template = PROMPT_HYBRID
        prompt_vars = {
            "question": state["question"],
            "recall_context": state["recall_context"],
            "web_results": state["web_search_results"]
        }
    
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.1)
        prompt = PromptTemplate.from_template(prompt_template)
        chain = prompt | llm | StrOutputParser()
        
        answer = chain.invoke(prompt_vars)
        
        # 🆕 검색 정보 추가 - 실시간 데이터 정보 포함
        search_info = f"\n\n🔍 검색 방법: {state['search_method']}"
        
        if state["recall_documents"]:
            # 실시간 데이터와 기존 데이터 구분
            realtime_count = len(realtime_docs)
            total_count = len(state["recall_documents"])
            
            search_info += f"\n📋 참조 문서: 총 {total_count}건"
            if realtime_count > 0:
                search_info += f" (⚡실시간: {realtime_count}건, 📚기존: {total_count - realtime_count}건)"
            
            # 리콜 제목들 추출 (실시간 데이터 우선)
            if realtime_docs:
                realtime_titles = [doc.metadata.get("title", "")[:50] + "..." 
                                 for doc in realtime_docs[:2] if doc.metadata.get("title")]
                if realtime_titles:
                    search_info += f"\n⚡ 최신 리콜: {', '.join(realtime_titles)}"
            
            # 기존 데이터 제목
            existing_docs = [doc for doc in state["recall_documents"] 
                           if doc.metadata.get("source") != "realtime_crawl"]
            if existing_docs and not realtime_docs:  # 실시간 데이터가 없을 때만 표시
                existing_titles = [doc.metadata.get("title", "")[:50] + "..." 
                                 for doc in existing_docs[:2] if doc.metadata.get("title")]
                if existing_titles:
                    search_info += f"\n📚 기존 사례: {', '.join(existing_titles)}"
        
        # 🆕 데이터 신선도 표시
        if has_realtime_data:
            search_info += f"\n✨ 실시간 업데이트 데이터 포함"
        
        final_answer = f"{answer}{search_info}"
        
        return {
            **state,
            "final_answer": final_answer
        }
        
    except Exception as e:
        error_answer = f"답변 생성 중 오류가 발생했습니다: {e}"
        return {
            **state,
            "final_answer": error_answer
        }

def update_history_node(state: RecallState) -> RecallState:
    """채팅 히스토리 업데이트"""
    try:
        current_history = state.get("chat_history", [])
        
        updated_history = current_history.copy()
        updated_history.append(HumanMessage(content=state["question"]))
        updated_history.append(AIMessage(content=state["final_answer"]))
        
        # 히스토리 길이 제한 (최대 8개 메시지)
        if len(updated_history) > 8:
            updated_history = updated_history[-8:]
        
        return {
            **state,
            "chat_history": updated_history
        }
        
    except Exception as e:
        print(f"히스토리 업데이트 오류: {e}")
        return state

# 그래프 구성
recall_workflow = StateGraph(RecallState)

# 노드 추가
recall_workflow.add_node("translate", translation_node)
recall_workflow.add_node("recall_search", recall_search_node)
recall_workflow.add_node("web_search", web_search_node)
recall_workflow.add_node("generate_answer", answer_generation_node)
recall_workflow.add_node("update_history", update_history_node)

# 엣지 추가
recall_workflow.add_edge(START, "translate")
recall_workflow.add_edge("translate", "recall_search")
recall_workflow.add_edge("recall_search", "web_search")
recall_workflow.add_edge("web_search", "generate_answer")
recall_workflow.add_edge("generate_answer", "update_history")
recall_workflow.add_edge("update_history", END)

# 그래프 컴파일
recall_graph = recall_workflow.compile()

def ask_recall_question(question: str, chat_history: List = None) -> Dict[str, Any]:
    """리콜 질문 처리 메인 함수 - 🆕 실시간 데이터 지원"""
    if chat_history is None:
        chat_history = []
    
    try:
        result = recall_graph.invoke({
            "question": question,
            "question_en": "",
            "recall_context": "",
            "recall_documents": [],
            "web_search_results": "",
            "final_answer": "",
            "search_method": "",
            "needs_web_search": False,
            "chat_history": chat_history
        })
        
        # 🆕 실시간 데이터 포함 여부 정보 추가
        realtime_docs = [doc for doc in result["recall_documents"] 
                        if doc.metadata.get("source") == "realtime_crawl"]
        
        return {
            "answer": result["final_answer"],
            "search_method": result["search_method"],
            "recall_documents": result["recall_documents"],
            "chat_history": result["chat_history"],
            "has_realtime_data": len(realtime_docs) > 0,  # 🆕 추가
            "realtime_count": len(realtime_docs),  # 🆕 추가
            "total_documents": len(result["recall_documents"])  # 🆕 추가
        }
        
    except Exception as e:
        return {
            "answer": f"처리 중 오류가 발생했습니다: {e}",
            "search_method": "error",
            "recall_documents": [],
            "chat_history": chat_history,
            "has_realtime_data": False,  # 🆕 추가
            "realtime_count": 0,  # 🆕 추가
            "total_documents": 0  # 🆕 추가
        }

# 🆕 벡터스토어 상태 체크 함수
def get_vectorstore_status() -> Dict[str, Any]:
    """벡터스토어 상태 정보 반환"""
    if recall_vectorstore is None:
        return {
            "status": "disconnected",
            "total_documents": 0,
            "realtime_documents": 0,
            "error": "벡터스토어가 초기화되지 않았습니다"
        }
    
    try:
        collection_data = recall_vectorstore.get()
        metadatas = collection_data.get('metadatas', [])
        
        total_docs = len(metadatas)
        realtime_docs = sum(1 for m in metadatas if m and m.get('source') == 'realtime_crawl')
        
        return {
            "status": "connected",
            "total_documents": total_docs,
            "realtime_documents": realtime_docs,
            "realtime_ratio": (realtime_docs / total_docs * 100) if total_docs > 0 else 0,
            "categories": len(set(m.get('category', 'Other') for m in metadatas if m)),
            "last_updated": max([m.get('last_updated', '') for m in metadatas if m], default='Unknown')
        }
        
    except Exception as e:
        return {
            "status": "error",
            "total_documents": 0,
            "realtime_documents": 0,
            "error": str(e)
        }
