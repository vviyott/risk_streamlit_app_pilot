# utils/google_crawler.py
"""
구글 뉴스 RSS 피드 기반 리콜 정보 검색 모듈
"""
import feedparser
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import re
from urllib.parse import quote_plus

def get_google_news_rss_url(keyword: str) -> str:
    """이 코드는 키워드로 구글 뉴스 RSS URL을 생성합니다"""
    enhanced_keyword = f"{keyword} FDA 리콜 recall"
    encoded_keyword = quote_plus(enhanced_keyword)
    
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
    return rss_url

def search_google_news_rss(keyword: str, max_results: int = 5, days_back: int = 30) -> List[Dict]:
    """이 코드는 구글 뉴스 RSS에서 리콜 관련 뉴스를 검색합니다"""
    try:
        search_strategies = [
            f"{keyword} FDA 리콜",           
            f"{keyword} 미국 리콜",          
            f"{keyword} recall USA",        
            f"Korean {keyword} FDA recall", 
            f"{keyword} 제품 회수"           
        ]
        
        all_results = []
        
        for i, search_query in enumerate(search_strategies):

            print(f"🔍 검색 전략 {i+1}: '{search_query}'")  # 🆕 디버깅 추가
            
            encoded_query = quote_plus(search_query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
            
            feed = feedparser.parse(rss_url)
            print(f"   RSS 결과: {len(feed.entries)}건") 
            
            if not feed.entries:
                continue
                
            strategy_results = []
            for entry in feed.entries[:max_results]:
                try:
                    pub_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    
                    title = entry.title if hasattr(entry, 'title') else '제목 없음'
                    link = entry.link if hasattr(entry, 'link') else ''
                    summary = entry.summary if hasattr(entry, 'summary') else ''
                    
                    source = 'Unknown'
                    if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                        source = entry.source.title
                    
                    is_fda_related = any(term in (title + summary).lower() 
                                       for term in ['fda', '미국', 'usa', 'america', 'recall', '리콜'])
                    
                    is_recall_relevant = is_recall_related_text(title + " " + summary)
                    
                    if is_fda_related or is_recall_relevant:
                        strategy_results.append({
                            'title': title,
                            'link': link,
                            'summary': summary,
                            'published': pub_date.strftime('%Y-%m-%d %H:%M') if pub_date else 'Unknown',
                            'source': source,
                            'content': '',
                            'search_strategy': i+1,
                            'is_fda_related': is_fda_related,
                            'is_recall_related': is_recall_relevant
                        })
                        
                except Exception as e:
                    continue
            
            all_results.extend(strategy_results)
            
            if len(all_results) >= max_results:
                break
        
        def sort_priority(item):
            fda_score = 10 if item['is_fda_related'] else 0
            recall_score = 5 if item['is_recall_related'] else 0
            strategy_score = 6 - item['search_strategy']
            return fda_score + recall_score + strategy_score
        
        all_results.sort(key=sort_priority, reverse=True)
        
        unique_results = []
        seen_titles = set()
        for result in all_results:
            if result['title'] not in seen_titles:
                unique_results.append(result)
                seen_titles.add(result['title'])
        
        return unique_results[:max_results]
        
    except Exception as e:
        return []

def is_recall_related_text(text: str) -> bool:
    """이 코드는 텍스트가 리콜 관련인지 확인합니다"""
    recall_keywords = [
        "리콜", "회수", "recall", "withdrawal", 
        "식품안전", "오염", "contamination",
        "세균", "bacteria", "안전경고", "위험",
        "식중독", "알레르기", "라벨링",
        "문제", "결함", "하자", "부적합",
        "판매중단", "유통중단", "반품"
    ]
    
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in recall_keywords)

def extract_news_content(url: str) -> str:
    """이 코드는 실제 뉴스 사이트에서 본문을 추출합니다"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        response.encoding = response.apparent_encoding
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for script in soup(["script", "style", "nav", "header", "footer", "aside"]):
            script.decompose()
        
        content_selectors = [
            'article',
            '.article-content', 
            '.news-content',
            '.post-content',
            '.content-body',
            '#article-view-content-div',
            '.article_view',
            'div[class*="content"]',
            'div[class*="article"]',
            'div[id*="content"]'
        ]
        
        content = ""
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                for element in elements:
                    paragraphs = element.find_all('p')
                    if paragraphs:
                        temp_content = '\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
                        if len(temp_content) > len(content):
                            content = temp_content
                
                if len(content) > 100:
                    break
        
        if len(content) < 100:
            paragraphs = soup.find_all('p')
            content = '\n'.join([p.get_text().strip() for p in paragraphs 
                               if len(p.get_text().strip()) > 20])
        
        if content:
            content = re.sub(r'\s+', ' ', content)
            content = re.sub(r'\n+', '\n', content)
            content = content.strip()
            content = content[:2000]
        
        return content
        
    except Exception as e:
        return ""

def search_and_extract_news(keyword: str, max_results: int = 3) -> List[Dict]:
    """이 코드는 구글 뉴스 RSS 검색과 본문 추출을 통합 수행합니다"""
    try:
        news_results = search_google_news_rss(keyword, max_results)
        
        if not news_results:
            return []
        
        enriched_results = []
        for i, news_item in enumerate(news_results):
            content = extract_news_content(news_item['link'])
            
            if content and len(content) > 50:
                news_item['content'] = content
                enriched_results.append(news_item)
            else:
                if news_item.get('summary') and len(news_item['summary']) > 30:
                    news_item['content'] = news_item['summary']
                    enriched_results.append(news_item)
            
            time.sleep(1)
        
        return enriched_results
        
    except Exception as e:
        return []

def format_news_for_context(news_results: List[Dict]) -> str:
    """이 코드는 뉴스 결과를 컨텍스트 형태로 포맷합니다"""
    if not news_results:
        return ""
    
    context_parts = []
    
    for i, news in enumerate(news_results):
        news_context = f"""
뉴스 제목: {news.get('title', '')}
출처: {news.get('source', 'Unknown')}
발행일: {news.get('published', 'Unknown')}
URL: {news.get('link', '')}

기사 내용:
{news.get('content', news.get('summary', ''))}
        """.strip()
        
        context_parts.append(news_context)
    
    return "\n\n---\n\n".join(context_parts)

def is_recall_related_news(news_item: Dict) -> bool:
    """이 코드는 뉴스가 리콜 관련인지 확인합니다"""
    title = news_item.get('title', '').lower()
    content = news_item.get('content', '').lower()
    summary = news_item.get('summary', '').lower()
    
    combined_text = f"{title} {content} {summary}"
    
    return is_recall_related_text(combined_text)
