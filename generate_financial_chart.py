import os
import requests
import json

# GitHub SecretsからAPIキーとNotion設定を取得
EDINET_API_KEY = os.environ.get("EDINET_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

def get_edinet_code(ticker_symbol):
    """
    証券コードからEDINETコード（EXXXXX）を取得する処理
    """
    # EDINET提出者一覧APIエンドポイント
    url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "Subscription-Key": EDINET_API_KEY,
        "type": 2
    }
    # 後続処理でリストを参照して該当企業のEDINETコードを特定
    print(f"証券コード {ticker_symbol} のEDINETコードを検索中...")
    return None

def fetch_financial_data(edinet_code):
    """
    最新の有価証券報告書(XBRL)からBS/PLの数値を自動抽出
    """
    # 抽出予定の項目
    financial_data = {
        "current_assets": 0,  # 流動資産
        "fixed_assets": 0,    # 固定資産
        "current_liab": 0,    # 流動負債
        "fixed_liab": 0,      # 固定負債
        "equity": 0,          # 純資産
        "sales": 0,           # 売上高
        "operating_income": 0 # 営業利益
    }
    return financial_data

if __name__ == "__main__":
    print("EDINETデータ取得＆図解生成処理を開始します。")
