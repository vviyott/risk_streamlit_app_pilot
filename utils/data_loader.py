# utils/data_loader.py

import os
import zipfile
import streamlit as st
import gdown

@st.cache_resource(show_spinner="📥 첫 실행 시 data.zip 다운로드 중...")
def download_and_unzip_data():
    zip_path = "./data/data.zip"
    extract_path = "./data"

    # 두 폴더(chroma_db, chroma_db_recall)가 모두 존재하면 압축 해제 생략
    chroma_exists = os.path.exists(os.path.join(extract_path, "chroma_db"))
    recall_exists = os.path.exists(os.path.join(extract_path, "chroma_db_recall"))

    if chroma_exists and recall_exists:
        print("✅ 이미 압축 해제되어 있음")
        return

    # ./data 폴더 생성
    os.makedirs(extract_path, exist_ok=True)

    # gdown을 통한 Google Drive ZIP 다운로드
    file_id = "1meFDZEcAzCauCFRap_T3Tx347xc4H28O"
    try:
        print("📥 Google Drive에서 ZIP 다운로드 시작")
        gdown.download(id=file_id, output=zip_path, quiet=False)
    except Exception as e:
        st.error(f"❌ Google Drive에서 ZIP 파일 다운로드 실패: {e}")
        raise

    # ZIP 파일 압축 해제
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        print("✅ 압축 해제 완료")
    except zipfile.BadZipFile:
        st.error("❌ 압축 파일이 손상되었습니다. ZIP 파일을 다시 확인해주세요.")
        raise
    except Exception as e:
        st.error(f"❌ 압축 해제 중 오류: {e}")
        raise

    # 디버깅: 해제된 파일 구조 출력
    print("\n📂 압축 해제 후 폴더 구조:")
    for root, dirs, files in os.walk(extract_path):
        level = root.replace(extract_path, "").count(os.sep)
        indent = "  " * level
        print(f"{indent}- {os.path.basename(root)}/")
        for d in dirs:
            print(f"{indent}  📁 {d}")
        for f in files:
            print(f"{indent}  📄 {f}")

# 디버깅용: chroma_db_recall 존재 여부 출력
recall_dir = "./data/chroma_db_recall"
if os.path.exists(recall_dir):
    print(f"✅ 경로 존재: {recall_dir}")
else:
    print(f"❌ 경로 없음: {recall_dir}")
