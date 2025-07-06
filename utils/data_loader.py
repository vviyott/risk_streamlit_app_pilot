# utils/data_loader.py

import os
import zipfile
import streamlit as st
import gdown

@st.cache_resource(show_spinner="📥 첫 실행 시 data.zip 다운로드 중...") # 최초 한 번만 실행됨
def download_and_unzip_data():
    zip_path = "./data/data.zip"
    extract_path = "./data"

    if os.path.exists(os.path.join(extract_path, "chroma_db")):
        return  # 이미 압축 해제되어 있으면 종료

    # 폴더 생성
    os.makedirs("./data", exist_ok=True)

    # gdown 다운로드
    file_id = "1meFDZEcAzCauCFRap_T3Tx347xc4H28O"
    gdown.download(id=file_id, output=zip_path, quiet=False)

    # 압축 해제
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)
