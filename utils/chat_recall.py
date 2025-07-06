# utils/chat_recall.py - 핵심 기능만 남긴 버전

import json
import os
from datetime import datetime, timedelta
from typing import TypedDict, List, Dict, Any
# from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langchain_teddynote import logging
from utils.fda_realtime_crawler import get_crawler, update_vectorstore_with_new_data,get_latest_date_from_vectorstore
from utils.google_crawler import search_and_extract_news, format_news_for_context

# load_dotenv()
logging.langsmith("LLMPROJECT")

class RecallState(TypedDict):
    """리콜 검색 시스템 상태"""
    question: str
    question_en: str  # 영어 번역된 질문
    recall_context: str
    recall_documents: List[Document]
    final_answer: str
    chat_history: List[HumanMessage | AIMessage]
    news_context: str  # 구글 뉴스 컨텍스트 추가
    final_answer: str
    news_documents: List[Dict]  # 뉴스 문서들 추가

def load_recall_documents():
    """이 코드는 FDA 리콜 JSON 데이터를 청크 없이 단일 문서로 변환합니다"""
    recall_file = "fda_recall.json"
    documents = []
    
    try:
        with open(recall_file, "r", encoding="utf-8") as f:
            recall_data = json.load(f)
            
            for item in recall_data:
                if isinstance(item, dict) and item.get("document_type") == "recall":
                    # 🆕 청크를 하나의 전체 내용으로 결합
                    chunks = item.get("chunks", [])
                    if not chunks:
                        continue
                    
                    # 모든 청크를 하나로 합치기
                    full_content = "\n\n".join(chunk for chunk in chunks if chunk and len(chunk.strip()) > 30)
                    
                    if not full_content or len(full_content.strip()) < 100:
                        continue
                    
                    # 구조화된 컨텐츠 생성 (기존과 동일)
                    structured_content = f"""
제목: {item.get('title', '')}
카테고리: {item.get('category', '')}
등급: {item.get('class', 'Unclassified')}
발효일: {item.get('effective_date', '')}
최종 업데이트: {item.get('last_updated', '')}

리콜 내용:
{full_content}
                    """.strip()
                    
                    metadata = {
                        "document_type": "recall",
                        "category": item.get("category", ""),
                        "class": item.get("class", "Unclassified"),
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "effective_date": item.get("effective_date", ""),
                        "source": "fda_recall_database"
                        # 🆕 chunk_index 제거 - 더 이상 청크가 아님
                    }
                    
                    doc = Document(page_content=structured_content, metadata=metadata)
                    documents.append(doc)
        
        print(f"리콜 데이터 로드 완료: {len(documents)}개 문서 (청크 제거)")
        return documents
        
    except FileNotFoundError:
        print(f"리콜 파일을 찾을 수 없습니다: {recall_file}")
        return []
    except Exception as e:
        print(f"리콜 데이터 로드 오류: {e}")
        return []

def initialize_recall_vectorstore():
    """이 코드는 리콜 전용 벡터스토어를 초기화하거나 기존 데이터를 로드합니다"""
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

def translation_node(state: RecallState) -> RecallState:
    """조건부 번역 노드 - 고유명사 보존 번역"""
    
    will_use_vectorstore = recall_vectorstore is not None
    
    if will_use_vectorstore:
        # 🆕 고유명사 보존 번역 수행
        question_en = translate_with_proper_nouns(state["question"])
        print(f"🔤 고유명사 보존 번역: '{state['question']}' → '{question_en}'")
    else:
        question_en = state["question"]
        print(f"🔤 번역 생략 (웹 검색 전용): '{question_en}'")
    
    # 🆕 검색용 키워드 추출
    search_keywords = extract_search_keywords(state["question"])
    
    return {
        **state,
        "question_en": question_en,
        "search_keywords": search_keywords  # 🆕 키워드 추가
    }

def translate_with_proper_nouns(korean_text: str) -> str:
    """고유명사를 보존하면서 번역하는 개선된 함수"""
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.1)
        
        # 🆕 고유명사 보존 프롬프트
        prompt = f"""
            다음 한국어 텍스트를 영어로 번역하되, 제품명과 브랜드명은 원형을 유지하세요.
            
            번역 규칙:
            1. 제품명/브랜드명은 한국어 원형 유지 (예: 불닭볶음면 → Buldak)
            2. 일반적인 식품 카테고리만 영어로 번역 (예: 라면 → ramen, 과자 → snack)
            3. "리콜", "사례" 등은 영어로 번역
            4. 번역문만 반환하고 설명 없이
            
            예시:
            - "불닭볶음면의 리콜 사례" → "Buldak ramen recall case"
            - "오리온 초코파이 리콜" → "Orion Choco Pie recall"
            
            한국어 텍스트: {korean_text}
            
            영어 번역:"""

        response = llm.invoke([HumanMessage(content=prompt)])
        translated = response.content.strip()
        
        # 🆕 번역 결과 검증 및 후처리
        if translated and len(translated) > 0:
            # 불필요한 따옴표나 설명 제거
            translated = translated.replace('"', '').replace("'", "")
            if translated.lower().startswith('translation:'):
                translated = translated[12:].strip()
            return translated
        else:
            return korean_text
            
    except Exception as e:
        print(f"고유명사 보존 번역 오류: {e}")
        return korean_text
    
def extract_search_keywords(question: str) -> str:
    """이 코드는 질문에서 뉴스 검색용 핵심 키워드를 추출합니다"""
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.1)
        
        prompt = f"""
            다음 질문에서 뉴스 검색에 적합한 핵심 키워드만 추출하세요.
            
            규칙:
            1. 제품명, 브랜드명, 식품명, 회사명만 추출
            2. "회수", "사례", "있나요", "어떤", "최근", "언제" 같은 불필요한 단어 제거
            3. 영어 브랜드명은 원형 유지 (예: McDonald's, KFC)
            4. 최대 3개 키워드로 제한
            5. 키워드 마지막에 "리콜" 단어 항상 추가
            5. 키워드만 공백으로 구분해서 반환 (설명이나 부가설명 없이)
            
            예시:
            - "맥도날드 햄버거 리콜 사례가 있나요?" → "맥도날드 햄버거 리콜"
            - "오리온 초코파이 최근 리콜 어떤 게 있어?" → "오리온 초코파이 리콜"
            - "만두 리콜 사례" → "만두 리콜"
            
            질문: {question}
            키워드:"""

        response = llm.invoke([HumanMessage(content=prompt)])
        keywords = response.content.strip()
        
        # 후처리: 불필요한 따옴표나 설명 제거
        keywords = keywords.replace('"', '').replace("'", "")
        if keywords.lower().startswith('키워드:'):
            keywords = keywords[3:].strip()
        
        print(f"🔍 키워드 추출: '{question}' → '{keywords}'")
        return keywords if keywords else question
        
    except Exception as e:
        print(f"키워드 추출 오류: {e}")
        # fallback: 간단한 정규식 방식
        return extract_keywords_fallback(question)


def extract_keywords_fallback(question: str) -> str:
    """fallback 키워드 추출 방식"""
    import re
    
    # 불용어 제거
    stop_words = ["회수", "사례", "있나요", "어떤", "어떻게", "언제", "왜", "최근", "요즘", "현재"]
    
    # 한글과 영문 단어 추출
    words = re.findall(r'[가-힣A-Za-z]+', question)
    keywords = [word for word in words if word not in stop_words and len(word) > 1]
    
    result = " ".join(keywords[:3])
    print(f"🔍 Fallback 키워드: '{question}' → '{result}'")
    return result if result else question
    

def is_recall_related_question(question: str) -> bool:
    """이 코드는 질문이 리콜 관련인지 판단합니다"""
    recall_keywords = [
        "리콜", "회수", "recall", "withdrawal", "safety alert",
        "FDA", "식품안전", "제품 문제", "오염", "contamination",
        "세균", "bacteria", "E.coli", "salmonella", "listeria",
        "알레르기", "allergen", "라벨링", "labeling",
        "식중독", "안전", "위험", "문제", "사고"
    ]
    
    question_lower = question.lower()
    return any(keyword.lower() in question_lower for keyword in recall_keywords)

def recall_search_node(state: RecallState) -> RecallState:
    """이 코드는 벡터DB에서 리콜 관련 문서를 검색하고 실시간 크롤링을 조건부로 수행합니다"""
    
    # 일반 질문이면 검색 생략
    if not is_recall_related_question(state["question"]):
        print(f"일반 질문 감지 - 리콜 검색 생략")
        return {
            **state,
            "recall_context": "",
            "recall_documents": []
        }
    
    if recall_vectorstore is None:
        print("리콜 벡터스토어가 초기화되지 않았습니다.")
        return {
            **state,
            "recall_context": "",
            "recall_documents": []
        }
    
    try:
        # 실시간 크롤링 조건 체크 (첫 질문 + 최신 데이터 요청)
        chat_history = state.get("chat_history", [])
        is_first_question = len(chat_history) == 0
        
        recent_keywords = ["최근", "recent", "latest", "new", "새로운", "요즘", "현재"]
        is_recent_query = any(keyword in state["question"].lower() for keyword in recent_keywords)
        
        # 세션 내에서 이미 크롤링했는지 확인
        has_crawled_in_session = False
        for msg in chat_history:
            if isinstance(msg, AIMessage) and "⚡실시간:" in msg.content:
                has_crawled_in_session = True
                break
        
        should_crawl = is_recent_query and not has_crawled_in_session
        
        if should_crawl:
            print("🔍 첫 질문 + 최신 데이터 요청 - 실시간 크롤링 수행")
            try:     
                crawler = get_crawler()
                # 벡터DB의 최신 날짜 조회
                latest_date_in_db = get_latest_date_from_vectorstore(recall_vectorstore)
                new_recalls = crawler.crawl_latest_recalls(after_date=latest_date_in_db, vectorstore=recall_vectorstore)
                
                if new_recalls:
                    added_count = update_vectorstore_with_new_data(new_recalls, recall_vectorstore)
                    print(f"✅ 새 데이터 {added_count}건 추가됨")
                else:
                    print("📋 새 리콜 데이터 없음")
                    
            except Exception as e:
                print(f"⚠️ 실시간 크롤링 실패: {e}")
        
        # 🆕 여기에 디버깅 코드 추가 (크롤링 직후)
        all_data = recall_vectorstore.get()
        metadatas = all_data.get('metadatas', [])
        
        # 최근 데이터 확인
        latest_dates = []
        for metadata in metadatas:
            if metadata and metadata.get('effective_date'):
                date_str = metadata['effective_date']
                if date_str.startswith('2025'):  # 2025년 데이터만
                    latest_dates.append({
                        'date': date_str,
                        'title': metadata.get('title', '')[:50],
                        'source': metadata.get('source', ''),
                        'url': metadata.get('url', '')[-30:]
                    })
        
        # 날짜순 정렬해서 최신 5개 출력
        latest_dates.sort(key=lambda x: x['date'], reverse=True)
        print("\n🔍 벡터DB의 2025년 데이터 확인:")
        for item in latest_dates[:5]:
            print(f"  📅 {item['date']} | {item['source']} | {item['title']} | {item['url']}")
        
        # 📅 최신 데이터 우선 검색 (벡터 검색 우회)
        print("📅 최신 데이터 우선 검색...")

        # 전체 데이터 가져오기
        all_data = recall_vectorstore.get()
        all_documents = []

        for i, metadata in enumerate(all_data.get('metadatas', [])):
            if metadata:
                content = all_data.get('documents', [])[i] if i < len(all_data.get('documents', [])) else ""
                doc = Document(page_content=content, metadata=metadata)
                all_documents.append(doc)

        def get_date_for_sorting(doc):
            date_str = doc.metadata.get('effective_date', '1900-01-01')
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except:
                return datetime(1900, 1, 1)

        # 🆕 청크 제거 후에는 단순한 날짜순 정렬만 필요
        if len(all_documents) > 0 and 'chunk_index' in all_documents[0].metadata:
            # 기존 청크 데이터가 있는 경우 - URL별 중복 제거
            url_groups = {}
            for doc in all_documents:
                url = doc.metadata.get('url', 'unknown')
                
                # URL별로 가장 긴 content를 가진 청크만 유지
                if url not in url_groups or len(doc.page_content) > len(url_groups[url].page_content):
                    url_groups[url] = doc
            
            unique_recalls = list(url_groups.values())
            unique_recalls.sort(key=get_date_for_sorting, reverse=True)
            print(f"📊 URL 기준 중복 제거: {len(unique_recalls)}개")
        else:
            # 청크 없는 새 데이터 - 바로 날짜순 정렬
            unique_recalls = all_documents
            unique_recalls.sort(key=get_date_for_sorting, reverse=True)
            print(f"📊 단일 문서 정렬: {len(unique_recalls)}개")

        # 디버깅 출력
        for i, doc in enumerate(unique_recalls[:10]):
            date = doc.metadata.get('effective_date', 'N/A')
            title = doc.metadata.get('title', '')[:50]
            source = doc.metadata.get('source', '')
            url_suffix = doc.metadata.get('url', '')[-30:]
            print(f"  {i+1}. {date} | {source} | {title}... | {url_suffix}")

        # 상위 5개 선택
        selected_docs = unique_recalls[:5]

        print(f"\n🎯 최종 selected_docs:")
        for i, doc in enumerate(selected_docs):
            date = doc.metadata.get('effective_date', 'N/A')
            title = doc.metadata.get('title', '')[:50]
            source = doc.metadata.get('source', '')
            print(f"  {i+1}. {date} | {source} | {title}...")

        # 컨텍스트 생성
        context_parts = []
        for doc in selected_docs:
            content_with_meta = f"{doc.page_content}\nSource URL: {doc.metadata.get('url', 'N/A')}"
            context_parts.append(content_with_meta)

        context = "\n\n---\n\n".join(context_parts)
        
        print(f"📊 검색 완료: 총 {len(selected_docs)}건")
        
        return {
            **state,
            "recall_context": context,
            "recall_documents": selected_docs
        }
        
    except Exception as e:
        print(f"검색 오류: {e}")
        return {
            **state,
            "recall_context": "",
            "recall_documents": []
        }

#==============================================================
# 답변 생성용 프롬프트 템플릿
PROMPT_RECALL_ANSWER = """
당신은 FDA 리콜·회수 전문 분석가입니다.
아래 정보를 사용해 한국어로 명확하고 실무적인 리콜 브리핑을 작성하세요.

📌 작성 규칙:
1. 제공된 "FDA Recall Database Information"만 근거로 사용합니다.
2. 리콜 사례가 1건 이상이면 표 형식으로 정리합니다:
   | 날짜 | 브랜드 | 제품 | 리콜 사유 | 종료 여부 | 출처 |
3. 출처 링크가 있으면 하이퍼링크 형태로 포함합니다.
4. 관련 없는 결과만 있으면 "현재 데이터 기준 해당 사례 확인 불가"라고 명시합니다.
5. 표 아래에 3-5문장으로 종합 요약을 작성합니다.

📝 질문: {question}

📒 FDA Recall Database Information:
{recall_context}

🔽 위 규칙에 따라 답변을 작성하세요:
"""

PROMPT_GENERAL_QUESTION = """
당신은 도움이 되는 AI 어시스턴트입니다.
사용자의 질문에 대해 정확하고 친절하게 답변해주세요.

질문: {question}

답변:
"""

# 기존 PROMPT_RECALL_ANSWER 다음에 추가
PROMPT_NEWS_ANSWER = """
당신은 FDA 리콜·회수 전문 분석가입니다.
아래 최신 뉴스 정보를 사용해 한국어로 명확하고 실무적인 리콜 브리핑을 작성하세요.

📌 작성 규칙:
1. 제공된 "Latest News Information"만 근거로 사용합니다.
2. 뉴스 기사가 1건 이상이면 표 형식으로 정리합니다:
   | 날짜 | 출처 | 제품/브랜드 | 리콜 사유 | 링크 |
3. 답변 시작 부분에 "관련 리콜 사례가 FDA 공식 사이트에 명시되어있지 않아 관련된 뉴스 정보로 제공합니다."라고 명시합니다.
4. 해외 리콜 사례의 경우 "해외 사례로 국내 직접 영향 없음"을 언급합니다.
5. 관련 있는 뉴스가 없으면 "현재 뉴스 기준 관련 사례 확인 불가"라고 명시합니다.
6. 표 아래에 3-5문장으로 종합 요약 및 참고사항을 작성합니다.

📝 질문: {question}

📰 Latest News Information:
{news_context}

🔽 위 규칙에 따라 답변을 작성하세요:
"""
#==============================================================

def google_news_search_node(state: RecallState) -> RecallState:
    """이 코드는 구글 뉴스에서 리콜 정보를 검색합니다"""
    
    try:
        # 🆕 뉴스 검색 전용 키워드 추출
        clean_keywords = extract_question_keywords(state["question"])  # "만두 리콜 사례" → "만두"
        
        print(f"📰 구글 뉴스 검색 시작: '{clean_keywords}' (원본: '{state['question']}')")
        
        # 뉴스 검색 및 본문 추출
        news_results = search_and_extract_news(clean_keywords, max_results=3)
        
        if news_results:
            # 뉴스 컨텍스트 생성
            news_context = format_news_for_context(news_results)
            print(f"✅ 구글 뉴스 검색 완료: {len(news_results)}건")
            
            return {
                **state,
                "recall_context": "",  # 🆕 FDA 컨텍스트 완전 제거
                "recall_documents": [],  # 🆕 FDA 문서 완전 제거
                "news_context": news_context,
                "news_documents": news_results
            }
        else:
            print("❌ 관련 뉴스를 찾을 수 없습니다")
            return {
                **state,
                "news_context": "",
                "news_documents": []
            }
            
    except Exception as e:
        print(f"구글 뉴스 검색 오류: {e}")
        return {
            **state,
            "news_context": "",
            "news_documents": []
        }

def should_use_google_news(state: RecallState) -> str:
    """이 코드는 구글 뉴스 검색 여부를 결정합니다 - 유사도 기반 판단"""
    
    # 리콜 관련 질문인지 확인
    if not is_recall_related_question(state["question"]):
        print("📝 일반 질문 - 답변 생성으로 직행")
        return "generate_answer"
    
    # 벡터DB 검색 결과 확인
    recall_docs = state.get("recall_documents", [])
    recall_count = len(recall_docs)
    
    print(f"🔍 벡터DB 검색 결과: {recall_count}건")
    
    # 🆕 유사도 기반 관련성 검사
    if recall_count > 0:
        relevant_docs = check_document_relevance(state["question"], recall_docs)
        relevant_count = len(relevant_docs)
        
        print(f"🎯 유사도 검사 후 관련 문서: {relevant_count}건")
        
        # 관련 문서가 2건 미만이면 구글 뉴스 검색
        if relevant_count < 2:
            print("📰 관련 문서 부족 - 구글 뉴스 검색 수행")
            return "google_search"
        else:
            print("📋 관련 문서 충분 - 답변 생성으로 진행")
            return "generate_answer"
    else:
        print("📰 검색 결과 없음 - 구글 뉴스 검색 수행")
        return "google_search"

def check_document_relevance(question: str, documents: List[Document]) -> List[Document]:
    """이 코드는 검색된 문서와 질문의 관련성을 LLM으로 판단합니다"""
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.1)
        
        # 질문에서 핵심 키워드 추출
        question_keywords = extract_question_keywords(question)
        
        relevant_docs = []
        
        for i, doc in enumerate(documents):
            title = doc.metadata.get('title', '')
            content_preview = doc.page_content[:500]
            
            # 🆕 개선된 관련성 판단 프롬프트
            relevance_prompt = f"""
                다음 질문과 FDA 리콜 문서의 관련성을 엄격히 판단하세요.
                
                질문: {question}
                핵심 키워드: {question_keywords}
                
                FDA 리콜 문서:
                제목: {title}
                내용: {content_preview}
                
                엄격한 판단 기준:
                1. 핵심 키워드가 제목이나 내용에 직접적으로 포함되어 있는가?
                2. 동일한 제품명/브랜드명이 언급되는가?
                3. 같은 식품 카테고리 내에서도 구체적으로 일치하는가?
                
                예시:
                - 질문 "만두 리콜" vs 문서 "dumpling recall" → 관련
                - 질문 "만두 리콜" vs 문서 "pasta recall" → 무관
                - 질문 "삼양 라면" vs 문서 "농심 라면" → 무관
                
                답변: "관련" 또는 "무관" 중 하나만 반환하세요.
                """
            
            response = llm.invoke([HumanMessage(content=relevance_prompt)])
            relevance = response.content.strip().lower()
            
            if "관련" in relevance:
                relevant_docs.append(doc)
                print(f"    ✅ 관련 문서 {i+1}: {title[:50]}...")
            else:
                print(f"    ❌ 무관 문서 {i+1}: {title[:50]}...")
        
        return relevant_docs
        
    except Exception as e:
        print(f"관련성 검사 오류: {e}")
        return documents

def extract_question_keywords(question: str) -> str:
    """이 코드는 질문에서 핵심 키워드를 간단 추출합니다"""
    import re
    
    # 불용어 제거
    stop_words = ["리콜", "회수", "사례", "있나요", "어떤", "어떻게", "언제", "왜", "최근", "요즘", "현재"]
    
    # 한글과 영문 단어 추출
    words = re.findall(r'[가-힣A-Za-z]+', question)
    keywords = [word for word in words if word not in stop_words and len(word) > 1]
    
    return " ".join(keywords[:3])

def answer_generation_node(state: RecallState) -> RecallState:
    """이 코드는 검색된 데이터를 바탕으로 적절한 답변을 생성합니다"""
    
    # 질문 타입별 프롬프트 선택
    is_recall_question = is_recall_related_question(state["question"])
    
    if not is_recall_question:
        # 일반 질문 처리
        try:
            llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.3)
            prompt = PromptTemplate.from_template(PROMPT_GENERAL_QUESTION)
            chain = prompt | llm | StrOutputParser()
            
            answer = chain.invoke({"question": state["question"]})
            final_answer = f"{answer}\n\n💡 일반 질문으로 처리됨"
            
            return {
                **state,
                "final_answer": final_answer
            }
            
        except Exception as e:
            return {
                **state,
                "final_answer": f"일반 질문 처리 중 오류: {e}"
            }
    
    # 리콜 관련 질문 처리
    try:
        llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.1)
        
        # 🆕 컨텍스트 결정 (FDA vs 뉴스)
        recall_context = state.get("recall_context", "")
        news_context = state.get("news_context", "")

        print(f"🔍 recall_context 길이: {len(recall_context)}")
        print(f"🔍 news_context 길이: {len(news_context)}")
        
        if recall_context:
            print("📋 FDA 데이터 기반 답변 선택")
            # FDA 데이터 기반 답변
            prompt = PromptTemplate.from_template(PROMPT_RECALL_ANSWER)
            context = recall_context
            source_type = "FDA 공식 데이터"
        elif news_context:
            print("📰 뉴스 데이터 기반 답변 선택")
            # 뉴스 데이터 기반 답변
            prompt = PromptTemplate.from_template(PROMPT_NEWS_ANSWER)  # 🆕 뉴스용 프롬프트
            context = news_context
            source_type = "최신 뉴스"
        else:
            return {
                **state,
                "final_answer": "현재 데이터 기준으로 해당 리콜 사례를 확인할 수 없습니다."
            }
        
        chain = prompt | llm | StrOutputParser()
        
        answer = chain.invoke({
            "question": state["question"],
            "recall_context": context if recall_context else "",
            "news_context": context if news_context else ""
        })
        
        # 🆕 검색 정보 추가
        search_info = f"\n\n📋 정보 출처: {source_type}"
        
        if recall_context:
            recall_docs = state.get("recall_documents", [])
            if recall_docs:
                realtime_count = len([doc for doc in recall_docs 
                                   if doc.metadata.get("source") == "realtime_crawl"])
                search_info += f" (총 {len(recall_docs)}건"
                if realtime_count > 0:
                    search_info += f", ⚡실시간: {realtime_count}건"
                search_info += ")"
        elif news_context:
            news_docs = state.get("news_documents", [])
            search_info += f" (뉴스 {len(news_docs)}건)"
        
        final_answer = f"{answer}{search_info}"
        
        return {
            **state,
            "final_answer": final_answer
        }
        
    except Exception as e:
        return {
            **state,
            "final_answer": f"답변 생성 중 오류: {e}"
        }

def update_history_node(state: RecallState) -> RecallState:
    """이 코드는 채팅 히스토리를 업데이트합니다"""
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

# LangGraph 워크플로우 구성 부분 수정
recall_workflow = StateGraph(RecallState)

# 노드 추가
recall_workflow.add_node("translate", translation_node)
recall_workflow.add_node("recall_search", recall_search_node)
recall_workflow.add_node("google_search", google_news_search_node)  # 🆕 추가
recall_workflow.add_node("generate_answer", answer_generation_node)
recall_workflow.add_node("update_history", update_history_node)

# 엣지 수정
recall_workflow.add_edge(START, "translate")
recall_workflow.add_edge("translate", "recall_search")

# 🆕 조건부 엣지 추가
recall_workflow.add_conditional_edges("recall_search", should_use_google_news, {
    "google_search": "google_search",
    "generate_answer": "generate_answer"
})

recall_workflow.add_edge("google_search", "generate_answer")  # 🆕 추가
recall_workflow.add_edge("generate_answer", "update_history")
recall_workflow.add_edge("update_history", END)

# 그래프 컴파일
recall_graph = recall_workflow.compile()

def ask_recall_question(question: str, chat_history: List = None) -> Dict[str, Any]:
    """이 코드는 리콜 질문을 처리하는 메인 함수입니다"""
    if chat_history is None:
        chat_history = []
    
    try:
        result = recall_graph.invoke({
            "question": question,
            "question_en": "",  # 번역 노드에서 채워짐
            "recall_context": "",
            "recall_documents": [],
            "final_answer": "",
            "chat_history": chat_history
        })
        
        return {
            "answer": result["final_answer"],
            "recall_documents": result["recall_documents"],
            "chat_history": result["chat_history"]
        }
        
    except Exception as e:
        return {
            "answer": f"처리 중 오류가 발생했습니다: {e}",
            "recall_documents": [],
            "chat_history": chat_history
        }
