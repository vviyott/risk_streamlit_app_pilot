# utils/data_loader.py

import os
import zipfile
import requests
import streamlit as st

def download_and_unzip_data():
    zip_path = "./data/data.zip"
    extract_path = "./data"

    if os.path.exists(os.path.join(extract_path, "chroma_db")):
        st.info("✅ 데이터 폴더가 이미 존재합니다. 다운로드를 건너뜁니다.")
        return

    file_id = "1meFDZEcAzCauCFRap_T3Tx347xc4H28O" ## 이 부분 각자 상황에 맞게 수정
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    st.info("📥 data.zip 다운로드 중...")
    with requests.get(download_url, stream=True) as r:
        r.raise_for_status()
        os.makedirs("./data", exist_ok=True)
        with open(zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    st.info("🗂️ 압축 해제 중...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)

    st.success("🎉 데이터 준비 완료!")
