# utils/data_loader.py
import os
import zipfile
import streamlit as st
import gdown

def folder_is_valid(path):
    return os.path.exists(path) and any(os.scandir(path))

@st.cache_resource(show_spinner="📥 첫 실행 시 data.zip 다운로드 중...")
def download_and_unzip_data():
    zip_path = "./data/data.zip"
    extract_path = "./data"
    chroma_path = os.path.join(extract_path, "chroma_db")
    recall_path = os.path.join(extract_path, "chroma_db_recall")
    
    if folder_is_valid(chroma_path) and folder_is_valid(recall_path):
        st.info("✅ 이미 압축 해제되어 있음")
        return
    
    os.makedirs(extract_path, exist_ok=True)
    file_id = "1meFDZEcAzCauCFRap_T3Tx347xc4H28O"
    
    try:
        st.info("📥 Google Drive에서 ZIP 다운로드 시작")
        gdown.download(id=file_id, output=zip_path, quiet=False)
    except Exception as e:
        st.error(f"❌ Google Drive에서 ZIP 파일 다운로드 실패: {e}")
        raise
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        st.success("✅ 압축 해제 완료")  # st.success로 변경
    except zipfile.BadZipFile:
        st.error("❌ 압축 파일이 손상되었습니다.")
        raise
    except Exception as e:
        st.error(f"❌ 압축 해제 중 오류: {e}")
        raise
    
    # 디버깅용 구조 출력 (이 부분은 print 그대로 둬도 됨)
    print("\n📂 압축 해제 후 폴더 구조:")
    for root, dirs, files in os.walk(extract_path):
        level = root.replace(extract_path, "").count(os.sep)
        indent = "  " * level
        print(f"{indent}- {os.path.basename(root)}/")
        for d in dirs:
            print(f"{indent}  📁 {d}")
        for f in files:
            print(f"{indent}  📄 {f}")

# 경로 존재 여부 확인 (추가 디버깅용)
recall_dir = "./data/chroma_db_recall"
if os.path.exists(recall_dir):
    print(f"✅ 경로 존재: {recall_dir}")
else:
    print(f"❌ 경로 없음: {recall_dir}")
