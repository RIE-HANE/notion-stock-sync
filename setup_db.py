import os
import sqlite3
import requests

# --- 設定値 ---
DB_FILE = "financial_data.db"
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
BASE_YEAR = 2024  # 直近の基準年度


def init_db():
    """データベースとテーブルの初期化"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS financial_metrics (
        ticker TEXT,
        year INTEGER,
        total_assets REAL,
        current_assets REAL,
        fixed_assets REAL,
        current_liab REAL,
        fixed_liab REAL,
        equity REAL,
        sales REAL,
        op_profit REAL,
        net_income REAL,
        PRIMARY KEY (ticker, year)
    )
    ''')
    conn.commit()
    conn.close()


def upsert_financial_data(ticker, year, data):
    """
    動的引数を受け取ってDBに登録・更新する汎用関数
    """
    if not data:
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR REPLACE INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        str(ticker).strip(),
        int(year),
        data.get("total_assets", 0),
        data.get("current_assets", 0),
        data.get("fixed_assets", 0),
        data.get("current_liab", 0),
        data.get("fixed_liab", 0),
        data.get("equity", 0),
        data.get("sales", 0),
        data.get("op_profit", 0),
        data.get("net_income", 0)
    ))
    
    conn.commit()
    conn.close()


def get_notion_companies():
    """Notionから企業リストと『3年』フラグを取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    res = requests.post(url, headers=headers)
    companies = []
    
    if res.status_code != 200:
        print(f"Notion API エラー: {res.text}")
        return companies

    results = res.json().get("results", [])
    for page in results:
        props = page.get("properties", {})
        ticker = None
        target_3years = False

        for prop_name, prop_val in props.items():
            p_type = prop_val.get("type")
            
            # 証券コードの取得
            if any(k in prop_name.lower() for k in ["コード", "ticker", "code", "証券"]):
                if p_type == "rich_text":
                    txt_arr = prop_val.get("rich_text", [])
                    if txt_arr:
                        ticker = txt_arr[0].get("plain_text")
                elif p_type == "number":
                    ticker = str(prop_val.get("number"))
            
            # 「3年」チェックボックスの取得
            if p_type == "checkbox" and ("3年" in prop_name or "過去" in prop_name):
                target_3years = prop_val.get("checkbox", False)

        if ticker:
            companies.append({
                "ticker": str(ticker).strip(),
                "target_3years": target_3years
            })
            
    return companies


def fetch_edinet_data(ticker, year):
    """
    【ここに既存の EDINET API 呼び出し・データ取得ロジックを実装】
    ※実際のEDINET API連携ロジックに合わせて数値を返してください。
    """
    # モック/実装例（EDINET API経由で取得できた辞書データを返す想定）
    # 本来は EDINET API から書類を検索し、XBRLを解析して返します。
    return None 


def sync_db_from_edinet():
    """Notionの条件に合わせてEDINETからデータを取得しDBを構築"""
    init_db()
    companies = get_notion_companies()
    
    for comp in companies:
        ticker = comp["ticker"]
        target_3years = comp["target_3years"]
        
        # 3年フラグがONなら過去3年分、OFFなら直近1年分
        target_years = [BASE_YEAR - 2, BASE_YEAR - 1, BASE_YEAR] if target_3years else [BASE_YEAR]
        
        print(f"--- 処理中: 証券コード {ticker} (対象年度: {target_years}) ---")
        
        for yr in target_years:
            # EDINETから指定年度のデータを取得
            fin_data = fetch_edinet_data(ticker, yr)
            
            if fin_data:
                upsert_financial_data(ticker, yr, fin_data)
                print(f"  └ 【登録完了】{yr}年度")
            else:
                print(f"  └ 【スキップ】{yr}年度のデータがEDINETから取得できませんでした")


if __name__ == "__main__":
    # 単体実行時はDB構築処理を走らせる
    sync_db_from_edinet()
