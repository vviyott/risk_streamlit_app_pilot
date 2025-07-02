# utils/data_loader.py

import os
import zipfile
import requests
import streamlit as st

@st.cache_resource(show_spinner="📥 첫 실행 시 data.zip 다운로드 중...")
def download_and_unzip_data():
    zip_path = "./data/data.zip"
    extract_path = "./data"

    if os.path.exists(os.path.join(extract_path, "chroma_db")):
        return  # 이미 준비됨

    file_id = "1meFDZEcAzCauCFRap_T3Tx347xc4H28O"
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    os.makedirs("./data", exist_ok=True)
    with requests.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)
