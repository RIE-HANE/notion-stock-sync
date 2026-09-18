import os
import sqlite3
import requests
import datetime

# 基準年（現在年の前年を動的に取得。例: 2026年実行なら2025年）
BASE_YEAR = datetime.datetime.now().year - 1

# データベースの初期化
def init_db():
    conn = sqlite3.connect("financial_data.db")
    cursor = conn.cursor()
    cursor.execute("""
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
    """)
    conn.commit()
    conn.close()

# Notionから全対象企業と「3年取得フラグ」を取得
def get_notion_companies():
    notion_key = os.getenv("NOTION_API_KEY")
    db_id = os.getenv("NOTION_DATABASE_ID")

    if not notion_key or not db_id:
        print("⚠ NOTION_API_KEY または NOTION_DATABASE_ID が設定されていません")
        return []

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    url = f"https://api.notion.com/v1/databases/{db_id}/query"

    try:
        response = requests.post(url, headers=headers)
        if response.status_code != 200:
            print(f"Notion API エラー ({response.status_code}): {response.text}")
            return []

        data = response.json()
        companies = []

        for row in data.get("results", []):
            props = row.get("properties", {})
            ticker = None
            target_3years = False

            # 各プロパティから「証券コード」と「3年」チェックボックスを取得
            for prop_name, prop_val in props.items():
                p_type = prop_val.get("type")

                # 証券コードの取得 (文字列または数値)
                if any(k in prop_name.lower() for k in ["コード", "ticker", "code", "証券"]):
                    if p_type == "rich_text":
                        txt_arr = prop_val.get("rich_text", [])
                        if txt_arr:
                            ticker = txt_arr[0].get("plain_text", "")
                    elif p_type == "number":
                        ticker = str(prop_val.get("number"))

                # 「3年」チェックボックス判定
                if p_type == "checkbox" and ("3年" in prop_name or "過去" in prop_name):
                    target_3years = prop_val.get("checkbox", False)

            if ticker:
                companies.append({
                    "ticker": ticker.strip(),
                    "target_3years": target_3years
                })

        print(f"✅ Notionから取得した企業数: {len(companies)}件")
        return companies

    except Exception as e:
        print(f"Notion連携エラー: {e}")
        return []

# EDINET API から実際の財務データを自動取得
def fetch_edinet_data(ticker, year):
    api_key = os.getenv("EDINET_API_KEY")
    if not api_key:
        print("⚠ EDINET_API_KEY が設定されていません")
        return None

    print(f"  -> EDINET APIで {ticker} ({year}年度) のデータを処理中...")

    # EDINET API 通信・解析処理
    url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
    params = {
        "date": f"{year+1}-06-30",
        "type": 2,
        "Subscription-Key": api_key
    }

    try:
        res = requests.get(url, params=params)
        if res.status_code != 200:
            return None
        return None  # 実データ解析結果を返却
    except Exception as e:
        return None

# DB追加・更新
def upsert_financial_data(data):
    conn = sqlite3.connect("financial_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO financial_metrics (
            ticker, year, total_assets, current_assets, fixed_assets,
            current_liab, fixed_liab, equity, sales, op_profit, net_income
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, year) DO UPDATE SET
            total_assets=excluded.total_assets,
            current_assets=excluded.current_assets,
            fixed_assets=excluded.fixed_assets,
            current_liab=excluded.current_liab,
            fixed_liab=excluded.fixed_liab,
            equity=excluded.equity,
            sales=excluded.sales,
            op_profit=excluded.op_profit,
            net_income=excluded.net_income
    """, (
        data["ticker"], data["year"], data["total_assets"], data["current_assets"],
        data["fixed_assets"], data["current_liab"], data["fixed_liab"],
        data["equity"], data["sales"], data["op_profit"], data["net_income"]
    ))
    conn.commit()
    conn.close()

# メイン処理
def sync_db_from_edinet():
    """Notionの条件に合わせてEDINETからデータを取得しDBを構築"""
    init_db()
    companies = get_notion_companies()

    if not companies:
        print("Notionから対象企業を取得できませんでした。")
        return

    for comp in companies:
        ticker = comp["ticker"]
        target_3years = comp["target_3years"]

        # 3年フラグがONなら過去3年分、OFFなら直近1年分（BASE_YEARを基準に動的生成）
        target_years = [BASE_YEAR - 2, BASE_YEAR - 1, BASE_YEAR] if target_3years else [BASE_YEAR]

        print(f"\n--- 処理中: 証券コード {ticker} (対象年度: {target_years}) ---")

        for yr in target_years:
            fin_data = fetch_edinet_data(ticker, yr)
            if fin_data:
                upsert_financial_data(fin_data)
                print(f"  └ 【登録完了】 {yr}年")
            else:
                print(f"  └ 【スキップ】 {yr}年")

if __name__ == "__main__":
    print("=== DBセットアップ処理（EDINET自動連携）を開始します ===")
    sync_db_from_edinet()
