# components/tableau.py

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import os
import time

def is_cloud_deployment():
    """클라우드 배포 환경인지 확인"""
    return (os.getenv('STREAMLIT_SHARING_MODE') or 
            'herokuapp' in os.getenv('SERVER_NAME', '') or
            'streamlit.app' in os.getenv('SERVER_NAME', ''))

def create_tableau_iframe(viz_url, height=400):
    """안정적인 iframe 방식으로 Tableau 시각화 생성"""
    iframe_html = f"""
    <div style="width: 100%; height: {height}px; border: 1px solid #ddd; border-radius: 5px; overflow: hidden;">
        <iframe 
            src="{viz_url}?:embed=y&:display_count=y&:showVizHome=n&:toolbar=top"
            width="100%" 
            height="{height}px"
            frameborder="0"
            allowfullscreen
            style="border: none;">
        </iframe>
    </div>
    """
    return iframe_html

def create_tableau_embed_with_fallback(viz_name, viz_id, height=420):
    """Tableau 임베드 코드 (iframe 폴백 포함)"""
    embed_html = f"""
    <div class='tableauPlaceholder' id='{viz_id}' style='position:relative;width:100%;'>
        <noscript>
            <a href='#'>
                <img src='https://public.tableau.com/static/images/{viz_name}/1.png'
                    style='border:none' alt='Tableau 시각화'>
            </a>
        </noscript>

        <object class='tableauViz' style='display:none;'>
            <param name='host_url' value='https%3A%2F%2Fpublic.tableau.com%2F'/>
            <param name='embed_code_version' value='3'/>
            <param name='site_root' value=''/>
            <param name='name' value='{viz_name}'/>
            <param name='tabs' value='no'/>
            <param name='toolbar' value='yes'/>
            <param name='language' value='ko-KR'/>
        </object>
    </div>

    <script type='text/javascript'>
        (function() {{
            function loadTableauViz() {{
                try {{
                    var divElement = document.getElementById('{viz_id}');
                    var vizElement = divElement.getElementsByTagName('object')[0];
                    
                    // 반응형 크기 설정
                    if (divElement.offsetWidth > 800) {{
                        vizElement.style.width = '100%';
                        vizElement.style.height = (divElement.offsetWidth * 0.75) + 'px';
                    }} else if (divElement.offsetWidth > 500) {{
                        vizElement.style.width = '100%';
                        vizElement.style.height = (divElement.offsetWidth * 0.75) + 'px';
                    }} else {{
                        vizElement.style.width = '100%';
                        vizElement.style.height = '{height}px';
                    }}
                    
                    // Tableau API 스크립트 로드
                    if (!window.tableauScriptLoaded) {{
                        var scriptElement = document.createElement('script');
                        scriptElement.src = 'https://public.tableau.com/javascripts/api/viz_v1.js';
                        scriptElement.onload = function() {{
                            window.tableauScriptLoaded = true;
                        }};
                        scriptElement.onerror = function() {{
                            console.error('Tableau 스크립트 로딩 실패 - iframe으로 폴백');
                            fallbackToIframe();
                        }};
                        vizElement.parentNode.insertBefore(scriptElement, vizElement);
                    }}
                }} catch (error) {{
                    console.error('Tableau 로딩 오류:', error);
                    fallbackToIframe();
                }}
            }}
            
            function fallbackToIframe() {{
                // iframe 폴백
                var divElement = document.getElementById('{viz_id}');
                var iframe_url = 'https://public.tableau.com/views/{viz_name}?:embed=y&:display_count=y&:showVizHome=n';
                divElement.innerHTML = `
                    <iframe 
                        src="${{iframe_url}}"
                        width="100%" 
                        height="{height}px"
                        frameborder="0"
                        allowfullscreen
                        style="border: 1px solid #ddd; border-radius: 5px;">
                    </iframe>
                `;
            }}
            
            // 페이지 로드 후 실행
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', loadTableauViz);
            }} else {{
                loadTableauViz();
            }}
        }})();
    </script>
    """
    return embed_html

## tableau
def create_market_dashboard():
    """미국 시장 진출 대시보드 UI 생성"""
    # 설명 문구 추가
    st.info("""
    미국 식품 시장 동향을 시각화된 자료로 확인할 수 있습니다.\n
    모든 시각화 자료는 다운로드 기능을 제공합니다.""")
    
    # 배포 환경 확인
    is_cloud = is_cloud_deployment()
    
    if is_cloud:
        st.warning("클라우드 환경에서는 iframe 방식으로 시각화를 로드합니다. 로딩이 느릴 수 있습니다.")
    
    # 2행: 두 개의 태블로 시각화
    viz_col1, viz_col2 = st.columns(2)
    
    with viz_col1:
        st.markdown("<h5 style='text-align: left;'># 미국 주별 식품 지출 시각화</h5>", unsafe_allow_html=True)
        
        if is_cloud:
            # 클라우드 환경: iframe 방식
            tableau_url = "https://public.tableau.com/views/state_food_exp2_17479635670940/State"
            components.html(create_tableau_iframe(tableau_url, 420), height=420, scrolling=False)
        else:
            # 로컬 환경: 기존 임베드 방식
            components.html(
                """
                <!-- Tableau Public embed (state_food_exp2_17479635670940 / State) -->
                <div id="viz_food_state" class="tableauPlaceholder" style="position:relative; width:100%;">
                <noscript>
                    <a href="#">
                    <img style="border:none"
                        src="https://public.tableau.com/static/images/st/state_food_exp2_17479635670940/State/1.png"
                        alt="State">
                    </a>
                </noscript>

                <object class="tableauViz" style="display:none;">
                    <param name="host_url" value="https%3A%2F%2Fpublic.tableau.com%2F" />
                    <param name="embed_code_version" value="3" />
                    <param name="site_root" value="" />
                    <param name="name" value="state_food_exp2_17479635670940/State" />
                    <param name="tabs" value="no" />
                    <param name="toolbar" value="bottom" />
                    <param name="language" value="ko-KR" />
                </object>
                </div>

                <script src="https://public.tableau.com/javascripts/api/viz_v1.js"></script>
                <script>
                const div = document.getElementById("viz_food_state");
                const vizOB = div.getElementsByTagName("object")[0];

                function resizeViz(){
                    vizOB.style.width = "100%";
                    vizOB.style.height = (div.offsetWidth * 0.75) + "px";
                }
                resizeViz();
                window.addEventListener("resize", resizeViz);
                </script>
                """,
                height=420,
                scrolling=False
            )
        
        st.caption("출처: [Statista Food](https://www.statista.com/outlook/cmo/food/united-states)")
    
    with viz_col2:
        st.markdown("<h5 style='text-align:left;'># 연도/리콜원인별 발생 건수 히트맵</h5>", unsafe_allow_html=True)

        if is_cloud:
            # 클라우드 환경: iframe 방식
            tableau_url = "https://public.tableau.com/views/food_recall_year_01/1_1"
            components.html(create_tableau_iframe(tableau_url, 420), height=420, scrolling=False)
        else:
            # 로컬 환경: 기존 임베드 방식 (폴백 포함)
            components.html(
                create_tableau_embed_with_fallback("food_recall_year_01/1_1", "viz_recall_trend", 420),
                height=420
            )
            
        st.caption("출처: [FDA Recall Database](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts)")

    # 3행: 두 개의 태블로 시각화
    viz_col3, viz_col4 = st.columns(2)

    with viz_col3:
        st.markdown("<h5 style='text-align:left;'># 연도/카테고리별 미국 식품 지출 추이</h5>", unsafe_allow_html=True)

        if is_cloud:
            # 클라우드 환경: iframe 방식
            tableau_url = "https://public.tableau.com/views/main01/1_1"
            components.html(create_tableau_iframe(tableau_url, 540), height=540, scrolling=False)
        else:
            # 로컬 환경: 기존 임베드 방식
            components.html(
                """
                <div class='tableauPlaceholder' id='vizPublic' style='position:relative;width:100%;'>
                <noscript><a href='#'>
                    <img src='https://public.tableau.com/static/images/ma/main01/1_1/1.png'
                        style='border:none' alt='대시보드 1'></a></noscript>

                <object class='tableauViz' style='display:none;'>
                    <param name='host_url' value='https%3A%2F%2Fpublic.tableau.com%2F'/>
                    <param name='embed_code_version' value='3'/>
                    <param name='site_root' value=''/>
                    <param name='name' value='main01/1_1'/>
                    <param name='tabs' value='no'/>
                    <param name='toolbar' value='yes'/>
                    <param name='language' value='ko-KR'/>
                </object>
                </div>

                <script src='https://public.tableau.com/javascripts/api/viz_v1.js'></script>
                <script>
                const divEl = document.getElementById('vizPublic');
                const vizEl = divEl.getElementsByTagName('object')[0];
                vizEl.style.width = '100%';
                vizEl.style.height = (divEl.offsetWidth * 0.75) + 'px';
                </script>
                """,
                height=540
            )
        
        st.caption("출처: [USDA](https://www.ers.usda.gov/data-products/us-food-imports)")
    
    with viz_col4:
        st.markdown("<h5 style='text-align: left;'># 리콜 등급(Class)별 발생 건수</h5>", unsafe_allow_html=True)

        if is_cloud:
            # 클라우드 환경: iframe 방식
            tableau_url = "https://public.tableau.com/views/food_recall_class_01/1_1"
            components.html(create_tableau_iframe(tableau_url, 540), height=540, scrolling=False)
        else:
            # 로컬 환경: 기존 임베드 방식 (폴백 포함)
            components.html(
                create_tableau_embed_with_fallback("food_recall_class_01/1_1", "viz_recall_class", 540),
                height=540
            )
        
        st.caption("출처: [FDA Recall Database](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts)")

# 추가 유틸리티 함수들
def preload_tableau_script():
    """Tableau 스크립트를 미리 로드"""
    components.html("""
        <script>
            if (!window.tableauScriptLoaded) {
                var script = document.createElement('script');
                script.src = 'https://public.tableau.com/javascripts/api/viz_v1.js';
                script.onload = function() {
                    window.tableauScriptLoaded = true;
                    console.log('Tableau API 스크립트 로드 완료');
                };
                script.onerror = function() {
                    console.error('Tableau API 스크립트 로드 실패');
                };
                document.head.appendChild(script);
            }
        </script>
    """, height=0)

def test_tableau_connectivity():
    """Tableau Public 연결 테스트"""
    st.write("### Tableau Public 연결 테스트")
    
    test_url = "https://public.tableau.com/views/state_food_exp2_17479635670940/State"
    
    with st.expander("연결 테스트 결과 보기"):
        if st.button("테스트 실행"):
            try:
                import requests
                response = requests.get(test_url, timeout=10)
                if response.status_code == 200:
                    st.success("✅ Tableau Public 연결 성공")
                else:
                    st.error(f"❌ 연결 실패: HTTP {response.status_code}")
            except Exception as e:
                st.error(f"❌ 연결 오류: {str(e)}")
                st.info("iframe 방식을 사용하는 것을 권장합니다.")

# 사용 예시
if __name__ == "__main__":
    st.set_page_config(page_title="미국 식품 시장 대시보드", layout="wide")
    
    # Tableau 스크립트 미리 로드 (선택사항)
    # preload_tableau_script()
    
    # 메인 대시보드 생성
    create_market_dashboard()
    
    # 연결 테스트 (개발/디버깅용)
    if st.sidebar.checkbox("연결 테스트 표시"):
        test_tableau_connectivity()
