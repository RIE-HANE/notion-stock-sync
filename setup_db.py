import datetime
import io
import os
import sqlite3
import zipfile
from edinet.xbrl_file import XBRLFile
import requests

# 今日の日付から「提出済みの最新年度（BASE_YEAR）」を自動計算
today = datetime.date.today()
if (today.month, today.day) < (6, 30):
    BASE_YEAR = today.year - 2
else:
    BASE_YEAR = today.year - 1

DB_FILE = "financial_data.db"


# データベースの初期化
def init_db():
    conn = sqlite3.connect(DB_FILE)
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


# 指定した企業・年度のデータがすでにDBにあるか確認
def is_data_exists(ticker, year):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1 FROM financial_metrics WHERE ticker = ? AND year = ?
    """,
        (str(ticker), int(year)),
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


# Notionから全対象企業と「過去データ取得フラグ」を取得
def get_notion_companies():
    notion_key = os.getenv("NOTION_API_KEY")
    db_id = os.getenv("NOTION_DATABASE_ID")

    if not notion_key or not db_id:
        print("⚠ NOTION_API_KEY または NOTION_DATABASE_ID が設定されていません")
        return []

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/databases/{db_id}/query"

    try:
        response = requests.post(url, headers=headers)
        if response.status_code != 200:
            print(
                f"Notion API エラー ({response.status_code}): {response.text}"
            )
            return []

        data = response.json()
        companies = []

        for row in data.get("results", []):
            props = row.get("properties", {})
            ticker = None
            target_3years = False

            for prop_name, prop_val in props.items():
                p_type = prop_val.get("type")

                # 証券コード取得
                if any(
                    k in prop_name.lower()
                    for k in ["コード", "ticker", "code", "証券"]
                ):
                    if p_type == "rich_text":
                        txt_arr = prop_val.get("rich_text", [])
                        if txt_arr:
                            ticker = txt_arr[0].get("plain_text", "")
                    elif p_type == "number":
                        ticker = str(prop_val.get("number"))

                # 「過去」フラグ判定（列名に「過去」「3年」「複数年」が含まれれば対象）
                if p_type == "checkbox" and any(
                    k in prop_name for k in ["過去", "3年", "複数年"]
                ):
                    target_3years = prop_val.get("checkbox", False)

            if ticker:
                companies.append(
                    {"ticker": ticker.strip(), "target_3years": target_3years}
                )

        print(f"✅ Notionから取得した企業数: {len(companies)}件")
        return companies

    except Exception as e:
        print(f"Notion連携エラー: {e}")
        return []


# EDINET API から財務データを検索・取得
def fetch_edinet_data(ticker, year, retry_count=1):
    api_key = os.getenv("EDINET_API_KEY")
    if not api_key:
        print("⚠ EDINET_API_KEY が設定されていません")
        return None

    print(f"  -> EDINET APIで {ticker} ({year}年度) のデータを検索中...")

    # 有価証券報告書が提出される翌年6月下旬（20日〜30日）を検索
    target_year = year + 1
    candidate_dates = [f"{target_year}-06-{d:02d}" for d in range(20, 31)]

    doc_id = None

    for target_date in candidate_dates:
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {
            "date": target_date,
            "type": 2,
            "Subscription-Key": api_key,
        }

        try:
            res = requests.get(url, params=params)
            if res.status_code != 200:
                continue

            results = res.json().get("results", [])

            for doc in results:
                sec_code = str(doc.get("secCode", ""))[:4]
                doc_type = str(doc.get("docTypeCode", ""))

                # 該当企業の有価証券報告書 (120) を検出
                if sec_code == str(ticker).strip()[:4] and doc_type == "120":
                    doc_id = doc.get("docID")
                    print(
                        f"    ✓ 書類発見 ({target_date}): docID={doc_id}"
                    )
                    return parse_edinet_xbrl(doc_id, ticker, year, api_key)

        except Exception:
            continue

    # 1回のみリトライ（前年度で検索）
    if not doc_id and retry_count > 0:
        print(
            f"    ⚠ {year}年度のデータがないため、1年引いて ({year - 1}年度) 再検索します..."
        )
        return fetch_edinet_data(ticker, year - 1, retry_count=retry_count - 1)

    if not doc_id:
        print(
            f"    ⚠ {year}年度の書類が見つかりませんでした (ticker: {ticker})"
        )
        return None


# EDINET XBRL書類のデータ解析処理 (方法A: edinet-python使用)
def parse_edinet_xbrl(doc_id, ticker, year, api_key):
    """EDINET APIから実際の書類(zip)を取得し、XBRLから財務データを抽出"""
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {"type": 1, "Subscription-Key": api_key}

    try:
        res = requests.get(url, params=params)
        if res.status_code != 200:
            return None

        # zipファイルをメモリ上で展開してXBRL解析
        z = zipfile.ZipFile(io.BytesIO(res.content))
        xbrl = XBRLFile(z)

        # 各科目の抽出（見つからない場合は 0.0）
        total_assets = float(
            xbrl.get_value("jpcrp_cor:TotalAssetsSummaryOfBusinessResults")
            or 0.0
        )
        sales = float(
            xbrl.get_value("jpcrp_cor:NetSalesSummaryOfBusinessResults") or 0.0
        )
        op_profit = float(
            xbrl.get_value(
                "jpcrp_cor:OperatingIncomeLossSummaryOfBusinessResults"
            )
            or 0.0
        )
        net_income = float(
            xbrl.get_value("jpcrp_cor:NetIncomeLossSummaryOfBusinessResults")
            or 0.0
        )

        current_assets = float(
            xbrl.get_value("jppfs_cor:CurrentAssets") or 0.0
        )
        fixed_assets = float(
            xbrl.get_value("jppfs_cor:NonCurrentAssets") or 0.0
        )
        current_liab = float(
            xbrl.get_value("jppfs_cor:CurrentLiabilities") or 0.0
        )
        fixed_liab = float(
            xbrl.get_value("jppfs_cor:NonCurrentLiabilities") or 0.0
        )
        equity = float(xbrl.get_value("jppfs_cor:NetAssets") or 0.0)

        return {
            "ticker": str(ticker),
            "year": int(year),
            "total_assets": total_assets,
            "current_assets": current_assets,
            "fixed_assets": fixed_assets,
            "current_liab": current_liab,
            "fixed_liab": fixed_liab,
            "equity": equity,
            "sales": sales,
            "op_profit": op_profit,
            "net_income": net_income,
        }
    except Exception as e:
        print(f"    ⚠ XBRLパース失敗 ({ticker}): {e}")
        return None


# DB追加・更新 (UPSERT)
def upsert_financial_data(data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
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
    """,
        (
            data["ticker"],
            data["year"],
            data["total_assets"],
            data["current_assets"],
            data["fixed_assets"],
            data["current_liab"],
            data["fixed_liab"],
            data["equity"],
            data["sales"],
            data["op_profit"],
            data["net_income"],
        ),
    )
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

    print(f"📌 自動算出された基準年度: {BASE_YEAR}年")

    for comp in companies:
        ticker = comp["ticker"]
        target_3years = comp["target_3years"]

        print(f"\n--- 処理中: 証券コード {ticker} ---")

        # 「過去」フラグによる対象年度の設定
        if target_3years:
            needed_years = [BASE_YEAR - 2, BASE_YEAR - 1, BASE_YEAR]
            print("  [条件] 過去3年分のデータが必要")
        else:
            needed_years = [BASE_YEAR]
            print("  [条件] 最新1年分のみ必要")

        # 各年度についてDB存在チェックを行い、足りない年度だけ取得
        for yr in needed_years:
            if is_data_exists(ticker, yr):
                print(
                    f"  └ 【スキップ】 {yr}年（すでにDBに存在します）"
                )
                continue

            fin_data = fetch_edinet_data(ticker, yr)
            if fin_data:
                upsert_financial_data(fin_data)
                print(f"  └ 【新規追加】 {fin_data['year']}年")
            else:
                print(
                    f"  └ 【取得失敗】 {yr}年（EDINETにデータがありません）"
                )


if __name__ == "__main__":
    print("=== DBセットアップ処理を開始します ===")
    sync_db_from_edinet()
