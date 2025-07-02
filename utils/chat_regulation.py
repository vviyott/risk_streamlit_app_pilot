# utils/chat_regulation.py

import json
import os
from functools import wraps
from dotenv import load_dotenv
from typing import TypedDict, List, Dict, Any 
from chromadb.config import Settings, DEFAULT_TENANT, DEFAULT_DATABASE, DEFAULT_COLLECTION
from langchain_openai import OpenAIEmbeddings, ChatOpenAI 
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate 
from langchain_core.messages import AIMessage, HumanMessage
from langchain_community.chat_message_histories import ChatMessageHistory
from langgraph.graph import StateGraph, START, END
from langchain_teddynote import logging   # LangSmith 추적 활성화

load_dotenv()                   # 환경변수 로드
logging.langsmith("LLMPROJECT") # LangSmith 추적 설정

# 계층적 구조를 위한 카테고리 그룹핑
CATEGORY_HIERARCHY = {
    "guidance": {
        "allergen": ["알러지", "allergen", "알레르기", "알러겐", "과민반응"],
        "additives": ["첨가물", "additive", "식품첨가물", "방부제", "감미료", "향료", "착색료"],
        "labeling": ["라벨링", "labeling", "라벨", "표시", "영양성분", "원재료", "성분표시"],
        "main": ["가이드라인", "guidance", "cpg", "가이드", "일반", "식품관련", "food"]
    },
    "regulation": {
        "ecfr": ["ecfr", "연방규정집", "전자연방규정", "cfr"],
        "usc": ["21usc", "법률", "조항", "규정", "regulation", "법령"]
    }
}

# 한국어-영어 번역 함수
def translate_korean_to_english(korean_text: str) -> str:
    """한국어 텍스트를 영어로 번역"""
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
        prompt = f"Translate the following Korean text to English. Only return the translation without any explanation:\n\n{korean_text}"
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        print(f"번역 중 오류 발생: {e}")
        return korean_text

def initialize_chromadb_collection():
    """DuckDB 기반으로 ChromaDB 연결"""
    try:
        persist_dir = "./data/chroma_db"

        # DuckDB를 쓰려면 Settings에 chroma_db_impl='duckdb' 명시
        client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_dir,
            anonymized_telemetry=False
        ))

        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vectorstore = Chroma(
            client=client,
            collection_name="chroma_regulations",
            embedding_function=embeddings,
            persist_directory=persist_dir
        )

        collection = vectorstore._collection
        document_count = collection.count()

        if document_count > 0:
            print(f"✅ DuckDB 기반 ChromaDB 연결 완료: {document_count}개 문서")
            return vectorstore
        else:
            raise ValueError("ChromaDB 컬렉션이 비어 있습니다.")

    except Exception as e:
        print(f"❌ DuckDB 연결 중 오류 발생: {e}")
        raise

# 상태 정의
class GraphState(TypedDict):
    question: str
    question_en: str
    document_type: str
    categories: List[str]
    chat_history: List[HumanMessage | AIMessage]
    context: str
    urls: List[str]
    answer: str
    need_synthesis: bool
    guidance_references: List[str]  # guidance에서 regulation 참조를 위한 필드

# 노드 정의
def router_node(state: GraphState) -> GraphState:
    """초기 라우팅: guidance vs regulation 결정 + 번역"""
    question = state["question"].lower()
    
    # 한국어 질문을 영어로 번역
    try:
        question_en = translate_korean_to_english(state["question"])
        print(f"번역된 질문: {question_en}")
    except Exception as e:
        print(f"번역 실패: {e}")
        question_en = state["question"]
    
    # regulation 키워드 체크
    regulation_keywords = ["법률","규제", "21usc", "규정", "regulation", "법령", "조항", "cfr", "code of federal"]
    guidance_keywords = ["가이드", "guidance", "cpg", "지침", "guideline"]
    
    combined_text = question + " " + question_en.lower()
    
    regulation_score = sum(1 for keyword in regulation_keywords if keyword in combined_text)
    guidance_score = sum(1 for keyword in guidance_keywords if keyword in combined_text)
    
    # 기본적으로 guidance 우선
    document_type = "regulation" if regulation_score > guidance_score else "guidance"
    
    return {
        **state,
        "question_en": question_en,
        "document_type": document_type,
        "guidance_references": []
    }

def category_node(state: GraphState) -> GraphState:
    """카테고리별 세부 분류 - 복합 질문 처리"""
    question = state["question"].lower()
    question_en = state["question_en"].lower()
    doc_type = state["document_type"]
    
    # 키워드 점수 계산
    category_scores = {}
    category_keywords = CATEGORY_HIERARCHY[doc_type]
    
    # 영어 키워드 매핑 확장
    english_keywords = {
        "allergen": ["allergen", "allergy", "allergenic", "hypersensitivity", "allergic reaction"],
        "additives": ["additive", "preservatives", "sweetener", "flavoring", "coloring", "food additive"],
        "labeling": ["labeling", "label", "nutrition", "ingredient", "declaration", "nutritional facts"],
        "main": ["guidance", "general", "main", "comprehensive", "cpg", "food related"],
        "ecfr": ["electronic code", "federal regulations", "cfr", "code of federal regulations"],
        "usc": ["united states code", "federal law", "statute", "21 usc", "federal statute"]
    }
    
    # 각 카테고리별 점수 계산
    for category, korean_keywords in category_keywords.items():
        score = 0
        
        # 한국어 키워드 매칭
        for keyword in korean_keywords:
            if keyword.lower() in question:
                score += 2
        
        # 영어 키워드 매칭
        for keyword in english_keywords.get(category, []):
            if keyword in question_en:
                score += 1.5
        
        category_scores[category] = score
    
    # 복합 질문 처리
    selected_categories = []
    
    # 특별 패턴 감지
    import re
    combined_text = question + " " + question_en.lower()
    
    complex_patterns = [
        (r'알러지.*규제|allergen.*regulation', 'allergen', 'guidance'),
        (r'첨가물.*규제|additive.*regulation', 'additives', 'guidance'), 
        (r'라벨링.*규제|labeling.*regulation', 'labeling', 'guidance'),
    ]
    
    pattern_matched = False
    for pattern, target_category, target_doc_type in complex_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            selected_categories = [target_category]
            state["document_type"] = target_doc_type
            pattern_matched = True
            print(f"복합 질문 감지: '{target_category}' 카테고리, '{target_doc_type}' 문서타입으로 변경")
            break
    
    if not pattern_matched:
        # 일반 로직: 가장 높은 점수를 가진 카테고리들 선택
        if category_scores:
            max_score = max(category_scores.values())
            if max_score > 0:
                threshold = max_score * 0.7
                selected_categories = [cat for cat, score in category_scores.items() 
                                     if score >= threshold]
    
    # 기본값 설정
    if not selected_categories:
        selected_categories = ["main"] if state["document_type"] == "guidance" else ["usc", "ecfr"]
    
    # 여러 카테고리가 선택되면 종합이 필요
    need_synthesis = len(selected_categories) > 1
    
    print(f"선택된 카테고리: {selected_categories}, 문서타입: {state['document_type']}, 점수: {category_scores}")
    
    return {
        **state,
        "categories": selected_categories,
        "need_synthesis": need_synthesis
    }

def document_retrieval_node(state: GraphState) -> GraphState:
    """ChromaDB에서 문서 검색 - guidance → regulation 참조 로직 포함"""
    all_documents = []
    guidance_references = []
    search_query = state["question_en"]
    
    for category in state["categories"]:
        docs_found = False
        
        # 1단계: 정확한 매칭으로 문서 검색 (ChromaDB에 category키의 값이 소문자로 저장되어 있음)
        try:
            filter_dict = {
                "$and": [
                    {"document_type": {"$eq": state["document_type"]}},
                    {"category": {"$eq": category.lower()}}  # 소문자로 통일
                ]
            }
            
            retriever = vectorstore.as_retriever(
                search_kwargs={"k": 3, "filter": filter_dict}
            )
            
            # 영어 질문으로 검색
            docs = retriever.invoke(search_query)
            
            if docs:
                all_documents.extend(docs)
                
                # guidance 문서에서 regulation 참조 정보 추출
                if state["document_type"] == "guidance":
                    for doc in docs:
                        metadata = doc.metadata
                        # CFR 참조 추출
                        cfr_refs = metadata.get("cfr_references", "")
                        if cfr_refs and cfr_refs.strip():
                            guidance_references.extend(cfr_refs.split(","))
                        
                        # USC 참조 추출  
                        usc_refs = metadata.get("usc_references", "")
                        if usc_refs and usc_refs.strip():
                            guidance_references.extend(usc_refs.split(","))
                
                print(f"카테고리 '{category.lower()}'에서 {len(docs)}개 문서 검색 완료")
                docs_found = True
                
        except Exception as e:
            print(f"카테고리 '{category}' 검색 실패: {e}")
            continue
    
    # 3단계: 문서타입만으로 검색
    if not all_documents:
        print(f"카테고리 검색 실패. 문서타입 '{state['document_type']}'으로만 검색합니다.")
        try:
            type_filter = {"document_type": {"$eq": state["document_type"]}}
            type_retriever = vectorstore.as_retriever(
                search_kwargs={"k": 5, "filter": type_filter}
            )
            all_documents = type_retriever.invoke(search_query)
            print(f"문서타입 검색에서 {len(all_documents)}개 문서 발견")
        except Exception as e:
            print(f"문서타입 검색도 실패: {e}")
    
    # 4단계: 전체 검색 (마지막 수단)
    if not all_documents:
        print("검색된 문서가 없습니다. 전체 검색을 시도합니다.")
        try:
            general_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
            all_documents = general_retriever.invoke(search_query)
            print(f"전체 검색에서 {len(all_documents)}개 문서 발견")
        except Exception as e:
            print(f"전체 검색도 실패: {e}")
    
    # 중복 제거 및 최종 선택
    unique_docs = []
    seen_content = set()
    for doc in all_documents:
        content_key = doc.page_content[:100]
        if content_key not in seen_content:
            unique_docs.append(doc)
            seen_content.add(content_key)
    
    selected_docs = unique_docs[:5]
    context = "\n\n".join([doc.page_content for doc in selected_docs])
    urls = list(set([doc.metadata.get("url", "") for doc in selected_docs if doc.metadata.get("url")]))
    
    # guidance_references 정리 (중복 제거 및 공백 제거)
    clean_references = []
    for ref in guidance_references:
        ref = ref.strip()
        if ref and ref not in clean_references:
            clean_references.append(ref)
    
    print(f"최종적으로 {len(selected_docs)}개 문서를 컨텍스트로 사용")
    if clean_references:
        print(f"추출된 regulation 참조: {clean_references}")
    
    return {
        **state,
        "context": context,
        "urls": urls,
        "guidance_references": clean_references
    }

def synthesis_node(state: GraphState) -> GraphState:
    """guidance → regulation 단방향 참조를 통한 답변 품질 향상"""
    additional_context = ""
    additional_urls = []
    
    # guidance 문서에서 regulation 참조가 있는 경우에만 실행
    if state["document_type"] == "guidance" and state["guidance_references"]:
        try:
            print(f"regulation 참조 검색 시작: {state['guidance_references']}")
            
            # 참조된 regulation 섹션들을 검색
            for reference in state["guidance_references"]:
                reference = reference.strip()
                if not reference:
                    continue
                
                # CFR 참조인지 USC 참조인지 판단
                ref_lower = reference.lower()
                if "cfr" in ref_lower or "21 cfr" in ref_lower:
                    target_category = "ecfr"
                elif "usc" in ref_lower or "21 u.s.c" in ref_lower:
                    target_category = "usc"
                else:
                    # 기본적으로 둘 다 검색
                    target_category = None
                
                # regulation 문서에서 해당 참조 검색
                try:
                    if target_category:
                        # 특정 카테고리로 검색
                        reg_filter = {
                            "$and": [
                                {"document_type": {"$eq": "regulation"}},
                                {"category": {"$eq": target_category}}
                            ]
                        }
                    else:
                        # regulation 문서 전체에서 검색
                        reg_filter = {"document_type": {"$eq": "regulation"}}
                    
                    reg_retriever = vectorstore.as_retriever(
                        search_kwargs={"k": 2, "filter": reg_filter}
                    )
                    
                    # 참조 번호를 검색 쿼리로 사용
                    reg_docs = reg_retriever.invoke(reference)
                    
                    if reg_docs:
                        ref_context = f"\n\n[{reference} 관련 규정]\n"
                        ref_context += "\n".join([doc.page_content[:500] + "..." for doc in reg_docs])
                        additional_context += ref_context
                        
                        ref_urls = [doc.metadata.get("url", "") for doc in reg_docs if doc.metadata.get("url")]
                        additional_urls.extend(ref_urls)
                        
                        print(f"참조 '{reference}'에서 {len(reg_docs)}개 regulation 문서 발견")
                    
                except Exception as e:
                    print(f"참조 '{reference}' 검색 중 오류: {e}")
                    continue
            
            # 일반적인 관련 regulation 검색 (참조가 구체적이지 않은 경우)
            if not additional_context:
                try:
                    search_query = state["question_en"]
                    reg_filter = {"document_type": {"$eq": "regulation"}}
                    reg_retriever = vectorstore.as_retriever(
                        search_kwargs={"k": 2, "filter": reg_filter}
                    )
                    reg_docs = reg_retriever.invoke(search_query)
                    
                    if reg_docs:
                        additional_context = "\n\n[관련 규정 참조]\n"
                        additional_context += "\n".join([doc.page_content[:500] + "..." for doc in reg_docs])
                        additional_urls = [doc.metadata.get("url", "") for doc in reg_docs if doc.metadata.get("url")]
                        print(f"일반 regulation 검색에서 {len(reg_docs)}개 문서 발견")
                
                except Exception as e:
                    print(f"일반 regulation 검색 중 오류: {e}")
        
        except Exception as e:
            print(f"guidance → regulation 참조 검색 중 전체 오류: {e}")
    
    # 종합이 필요한 경우 (여러 카테고리)
    elif state["need_synthesis"]:
        try:
            search_query = state["question_en"]
            cross_filter = {"document_type": {"$eq": state["document_type"]}}
            cross_retriever = vectorstore.as_retriever(
                search_kwargs={"k": 2, "filter": cross_filter}
            )
            cross_docs = cross_retriever.invoke(search_query)
            
            if cross_docs:
                additional_context = "\n\n[추가 관련 정보]\n"
                additional_context += "\n".join([doc.page_content[:500] + "..." for doc in cross_docs])
                additional_urls = [doc.metadata.get("url", "") for doc in cross_docs if doc.metadata.get("url")]
        
        except Exception as e:
            print(f"종합 검색 중 오류: {e}")
    
    # 추가 컨텍스트와 URL 병합
    if additional_context:
        updated_context = state["context"] + additional_context
        updated_urls = state["urls"] + additional_urls
        
        return {
            **state,
            "context": updated_context,
            "urls": updated_urls
        }
    
    return state

def generate_answer(state: GraphState) -> GraphState:
    """답변 생성"""
    doc_info = f"문서 타입: {state['document_type']}, 카테고리: {', '.join(state['categories'])}"
    
    # guidance → regulation 참조 정보 추가
    if state["guidance_references"]:
        doc_info += f", 참조된 regulation: {', '.join(state['guidance_references'])}"
    
    # 채팅 히스토리 처리
    chat_history_text = ""
    if state.get("chat_history"):
        recent_history = state["chat_history"][-4:]
        chat_history_text = "\n".join([f"{msg.__class__.__name__}: {msg.content}" for msg in recent_history])
    
    prompt = PromptTemplate.from_template(
        """당신은 미국 FDA 규제를 전문적으로 해석하는 규제 자문 전문가입니다.
아래 사용자의 질문에 대해 주어진 컨텍스트를 바탕으로 **한국어로 정밀하고 신뢰성 있는 해석**을 제공하세요.
❗️규칙:
- 반드시 규제 문서 내용을 기반으로 판단하세요.
- 출처가 포함된 조항은 **인용 표시(예: 21 U.S.C. § 721(b)(1))**로 명시하고, 가능할 경우 해당 조항의 **URL 링크도 함께 제시**하세요.
- 출처 문서가 없는 경우 **괄호 없이 마무리**하세요.
- 중요 내용은 **항목 또는 번호 형식**으로 정리하고, 구체적인 표현을 사용하세요.
- 컨텍스트에 정보가 부족한 경우, "**관련 문서에서 명확한 기준은 확인되지 않음**"이라고 서술하세요.
- 마지막에는 위의 항목들을 **요약하여 정리한 종합적 분석 문단**을 추가하세요. (3~5문장 정도, 핵심 논점을 서술적으로 설명)

📝 사용자 질문:
{question}

📚 관련 문서 정보:
{doc_info}

📖 문서 컨텍스트:
{context}

💬 이전 대화 기록 (있을 경우):
{chat_history}

🔽 이제 위의 정보를 바탕으로 정리된 전문적 답변을 작성해주세요:"""
    )
    
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.1)
        chain = prompt | llm | StrOutputParser()
        
        answer = chain.invoke({
            "question": state["question"],
            "context": state["context"],
            "chat_history": chat_history_text,
            "doc_info": doc_info
        })
        
        # URL 정보 추가
        if state["urls"]:
            unique_urls = list(set([url for url in state["urls"] if url.strip()]))
            if unique_urls:
                url_text = "\n\n📎 출처:\n" + "\n".join([f"- {url}" for url in unique_urls])
                full_answer = f"{answer}{url_text}"
            else:
                full_answer = answer
        else:
            full_answer = answer
        
        return {
            **state,
            "answer": full_answer
        }
    
    except Exception as e:
        error_answer = f"답변 생성 중 오류가 발생했습니다: {e}"
        return {
            **state,
            "answer": error_answer
        }

def update_chat_history(state: GraphState) -> GraphState:
    """채팅 히스토리 업데이트"""
    try:
        current_history = state.get("chat_history", [])
        
        # 새 메시지 추가
        updated_history = current_history.copy()
        updated_history.append(HumanMessage(content=state["question"]))
        updated_history.append(AIMessage(content=state["answer"]))
        
        # 히스토리 길이 제한 (최대 10개 메시지)
        if len(updated_history) > 10:
            updated_history = updated_history[-10:]
        
        return {
            **state,
            "chat_history": updated_history
        }
    
    except Exception as e:
        print(f"채팅 히스토리 업데이트 중 오류: {e}")
        return state

# 그래프 구성
workflow = StateGraph(GraphState)

# 노드 추가
workflow.add_node("router", router_node)
workflow.add_node("category", category_node) 
workflow.add_node("retrieval", document_retrieval_node)
workflow.add_node("synthesis", synthesis_node)
workflow.add_node("generate", generate_answer)
workflow.add_node("update_history", update_chat_history)

# 엣지 추가
workflow.add_edge(START, "router")
workflow.add_edge("router", "category")
workflow.add_edge("category", "retrieval")
workflow.add_edge("retrieval", "synthesis")
workflow.add_edge("synthesis", "generate")
workflow.add_edge("generate", "update_history")
workflow.add_edge("update_history", END)

# 그래프 컴파일
graph = workflow.compile()

# 메인 실행 함수
def ask_question(question: str, chat_history: List = None) -> Dict[str, Any]:
    """질문 처리 메인 함수"""
    if chat_history is None:
        chat_history = []
    
    try:
        result = graph.invoke({
            "question": question,
            "question_en": "",
            "chat_history": chat_history,
            "document_type": "",
            "categories": [],
            "context": "",
            "urls": [],
            "answer": "",
            "need_synthesis": False,
            "guidance_references": []
        })
        
        return {
            "answer": result["answer"],
            "document_type": result["document_type"],
            "categories": result["categories"],
            "urls": result["urls"],
            "chat_history": result["chat_history"],
            "guidance_references": result["guidance_references"]
        }
    
    except Exception as e:
        return {
            "answer": f"처리 중 오류가 발생했습니다: {e}",
            "document_type": "",
            "categories": [],
            "urls": [],
            "chat_history": chat_history,
            "guidance_references": []
        }
