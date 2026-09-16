import os
import io
import zipfile
import requests
from bs4 import BeautifulSoup

EDINET_API_KEY = os.environ.get("EDINET_API_KEY")

def get_latest_doc_id(edinet_code):
    """
    指定されたEDINETコードの直近の有価証券報告書(docID)を取得する
    """
    url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "Subscription-Key": EDINET_API_KEY,
        "type": 2
    }
    # API経由で提出書類一覧を取得し、有価証券報告書（type: 120）を探す
    response = requests.get(url, params=params)
    data = response.json()
    
    if "results" in data:
        for doc in data["results"]:
            if doc.get("edinetCode") == edinet_code and doc.get("docTypeCode") == "120":
                return doc.get("docID")
    return None

def fetch_financial_values(doc_id):
    """
    docIDのXBRL/HTMLデータから主要なBS/PL項目を抽出
    """
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {
        "Subscription-Key": EDINET_API_KEY,
        "type": 1  # 本文文書及び監査報告書を取得
    }
    
    res = requests.get(url, params=params)
    if res.status_code != 200:
        print("書類データの取得に失敗しました。")
        return None

    # 初期化（取得対象データ）
    financial_data = {
        "current_assets": 0, # 流動資産
        "fixed_assets": 0,   # 固定資産
        "current_liab": 0,   # 流動負債
        "fixed_liab": 0,     # 固定負債
        "equity": 0,         # 純資産
        "sales": 0,          # 売上高
        "op_profit": 0,      # 営業利益
        "net_profit": 0      # 当期純利益
    }

    # 解凍してXBRL/HTMLファイルを解析する処理（後続ロジック）
    print(f"DocID: {doc_id} の財務データを解析中...")
    return financial_data

if __name__ == "__main__":
    print("EDINETデータ取得モジュール準備完了。")
