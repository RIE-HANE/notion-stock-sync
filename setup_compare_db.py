import datetime
import io
import os
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import requests

today = datetime.date.today()
TODAY_STR = today.strftime("%Y-%m-%d")

# 今日の日付から「提出済みの最新年度（BASE_YEAR）」を自動計算
if (today.month, today.day) < (6, 30):
    BASE_YEAR = today.year - 2
else:
    BASE_YEAR = today.year - 1

DB_FILE = "financial_data.db"


# データベース初期化
def init_compare_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
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
            operating_cf REAL,
            investing_cf REAL,
            financing_cf REAL,
            created_at TEXT,
            PRIMARY KEY (ticker, year)
        )
    """
    )

    # 既存テーブルにCFカラムがない場合のみ自動追加
    cursor.execute("PRAGMA table_info(financial_metrics)")
    columns = [col[1] for col in cursor.fetchall()]

    for cf_col in ["operating_cf", "investing_cf", "financing_cf"]:
        if cf_col not in columns:
            cursor.execute(
                f"ALTER TABLE financial_metrics ADD COLUMN {cf_col} REAL"
            )

    conn.commit()
    conn.close()


# 指定企業・年度のデータがすでにDBにあるか確認する関数
def is_cf_exists(ticker, year):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT operating_cf FROM financial_metrics
        WHERE ticker = ? AND year = ? AND operating_cf IS NOT NULL
    """,
        (str(ticker), int(year)),
    )
    result = cursor.fetchone()
    conn.close()
    return result is not None


# DB内の企業の最新年度を取得する関数
def get_latest_year_in_db(ticker):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT MAX(year) FROM financial_metrics WHERE ticker = ?
    """,
        (str(ticker),),
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] is not None else None


# ページIDから企業の証券コードを取得するヘルパー関数
def get_ticker_by_page_id(page_id, headers):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None

    props = res.json().get("properties", {})
    for k, v in props.items():
        if any(key in k.lower() for key in ["コード", "ticker", "code", "証券"]):
            if v.get("type") == "rich_text" and v.get("rich_text"):
                return v["rich_text"][0].get("plain_text", "").strip()
            elif v.get("type") == "number":
                return str(v.get("number")).strip()
    return None


# Notionから比較対象（Relation欄に設定がある企業＆相手企業）を取得
def get_compare_targets_from_notion():
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

    payload = {
        "filter": {
            "property": "比較",
            "relation": {"is_not_empty": True},
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            print(
                f"Notion API エラー ({response.status_code}): {response.text}"
            )
            return []

        data = response.json()
        target_tickers = set()

        for row in data.get("results", []):
            props = row.get("properties", {})
            ticker = None

            # 1. 自社の証券コードを取得
            for k, v in props.items():
                if any(
                    key in k.lower() for key in ["コード", "ticker", "code", "証券"]
                ):
                    if v.get("type") == "rich_text" and v.get("rich_text"):
                        ticker = v["rich_text"][0].get("plain_text")
                    elif v.get("type") == "number":
                        ticker = str(v.get("number"))

            if ticker:
                target_tickers.add(ticker.strip())

            # 2. リレーション（比較対象）企業の証券コードも取得
            relation_list = props.get("比較", {}).get("relation", [])
            if relation_list:
                target_page_id = relation_list[0]["id"]
                target_ticker = get_ticker_by_page_id(target_page_id, headers)
                if target_ticker:
                    target_tickers.add(target_ticker)

        tickers_list = list(target_tickers)
        print(f"✅ Notionから取得した比較対象企業数: {len(tickers_list)}件 (銘柄: {', '.join(tickers_list)})")
        return tickers_list

    except Exception as e:
        print(f"Notion連携エラー: {e}")
        return []


# EDINET API から財務書類（XBRL）を検索・取得（全日付自動検索・リトライ機能付き）
def fetch_and_parse_cf(ticker, year, retry_count=1):
    api_key = os.getenv("EDINET_API_KEY")
    if not api_key:
        print("⚠ EDINET_API_KEY が設定されていません")
        return None

    print(f"  -> EDINET APIで {ticker} ({year}年度) のデータを検索中...")

    # 対象年度の翌年1年間の全提出日を自動検索（月・日ハードコードなし）
    target_year = year + 1
    start_date = datetime.date(target_year, 1, 1)
    end_date = datetime.date(target_year, 12, 31)

    doc_id = None
    curr_date = start_date

    while curr_date <= end_date:
        date_str = curr_date.strftime("%Y-%m-%d")
        curr_date += datetime.timedelta(days=1)

        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {
            "date": date_str,
            "type": 2,
            "Subscription-Key": api_key,
        }

        try:
            res = requests.get(url, params=params)
            if res.status_code != 200:
                continue

            results = res.json().get("results", [])

            for doc in results:
                # 120 = 有価証券報告書
                if str(doc.get("docTypeCode")) == "120":
                    sec_code = doc.get("secCode")

                    # 証券コード判定（4桁または5桁に対応）
                    if sec_code in [f"{ticker}0", str(ticker)]:
                        doc_id = doc.get("docID") or doc.get("docId")
                        print(f"    ✓ 書類発見 ({date_str}): docID={doc_id}")
                        return parse_compare_data_from_xbrl(doc_id, ticker, year, api_key)

        except Exception:
            continue

    # 1回のみリトライ（前年度で検索）
    if not doc_id and retry_count > 0:
        print(
            f"    ⚠ {year}年度のデータがないため、1年引いて ({year - 1}年度) 再検索します..."
        )
        return fetch_and_parse_cf(
            ticker, year - 1, retry_count=retry_count - 1
        )

    if not doc_id:
        print(
            f"    ⚠ {year}年度の書類が見つかりませんでした (ticker: {ticker})"
        )
        return None


# 文字コードを安全にデコードするヘルパー関数
def safe_decode(raw_bytes):
    for enc in ["utf-8", "utf-16", "cp932", "euc-jp"]:
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="ignore")


# EDINET XBRLから BS/PL/CF をまとめて解析
def parse_compare_data_from_xbrl(doc_id, ticker, year, api_key):
    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {"type": 1, "Subscription-Key": api_key}

    try:
        res = requests.get(url, params=params)
        if res.status_code != 200:
            return None

        data_dict = {}

        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xbrl_files = [f for f in z.namelist() if f.endswith(".xbrl")]

            for xfile in xbrl_files:
                raw_data = z.read(xfile)
                content_str = safe_decode(raw_data)

                try:
                    root = ET.fromstring(content_str)
                    for elem in root.iter():
                        tag_name = (
                            elem.tag.split("}")[-1]
                            if "}" in elem.tag
                            else elem.tag
                        )
                        if elem.text and elem.text.strip():
                            if tag_name not in data_dict:
                                data_dict[tag_name] = elem.text.strip()
                except Exception:
                    continue

        def get_val(key):
            val = data_dict.get(key)
            if val:
                try:
                    return float(val)
                except ValueError:
                    return 0.0
            return 0.0

        # BS/PL科目の抽出
        total_assets = get_val("TotalAssetsSummaryOfBusinessResults") or get_val("TotalAssets")
        sales = get_val("NetSalesSummaryOfBusinessResults") or get_val("NetSales")
        op_profit = get_val("OperatingIncomeLossSummaryOfBusinessResults") or get_val("OperatingIncome")
        net_income = get_val("NetIncomeLossSummaryOfBusinessResults") or get_val("ProfitLoss")

        current_assets = get_val("CurrentAssets")
        fixed_assets = get_val("NonCurrentAssets")
        current_liab = get_val("CurrentLiabilities")
        fixed_liab = get_val("NonCurrentLiabilities")
        equity = get_val("NetAssets")

        # CF科目の抽出
        op_cf = get_val("NetCashProvidedByUsedInOperatingActivities") or get_val(
            "CashFlowsFromUsedInOperatingActivities"
        )
        inv_cf = get_val("NetCashProvidedByUsedInInvestingActivities") or get_val(
            "CashFlowsFromUsedInInvestingActivities"
        )
        fin_cf = get_val("NetCashProvidedByUsedInFinancingActivities") or get_val(
            "CashFlowsFromUsedInFinancingActivities"
        )

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
            "operating_cf": op_cf,
            "investing_cf": inv_cf,
            "financing_cf": fin_cf,
        }

    except Exception as e:
        print(f"    ⚠ XBRLパース失敗 ({ticker}): {e}")
        return None


# DBへ比較用データ（BS/PL/CF）を上書き・追記保存
def save_compare_data_to_db(data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO financial_metrics (
            ticker, year, total_assets, current_assets, fixed_assets,
            current_liab, fixed_liab, equity, sales, op_profit, net_income,
            operating_cf, investing_cf, financing_cf, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, year) DO UPDATE SET
            total_assets = COALESCE(NULLIF(excluded.total_assets, 0), financial_metrics.total_assets),
            current_assets = COALESCE(NULLIF(excluded.current_assets, 0), financial_metrics.current_assets),
            fixed_assets = COALESCE(NULLIF(excluded.fixed_assets, 0), financial_metrics.fixed_assets),
            current_liab = COALESCE(NULLIF(excluded.current_liab, 0), financial_metrics.current_liab),
            fixed_liab = COALESCE(NULLIF(excluded.fixed_liab, 0), financial_metrics.fixed_liab),
            equity = COALESCE(NULLIF(excluded.equity, 0), financial_metrics.equity),
            sales = COALESCE(NULLIF(excluded.sales, 0), financial_metrics.sales),
            op_profit = COALESCE(NULLIF(excluded.op_profit, 0), financial_metrics.op_profit),
            net_income = COALESCE(NULLIF(excluded.net_income, 0), financial_metrics.net_income),
            operating_cf = excluded.operating_cf,
            investing_cf = excluded.investing_cf,
            financing_cf = excluded.financing_cf,
            created_at = excluded.created_at
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
            data["operating_cf"],
            data["investing_cf"],
            data["financing_cf"],
            TODAY_STR,
        ),
    )
    conn.commit()
    conn.close()


# 比較用データ（過去5年分）を同期するメイン関数
def sync_compare_data():
    init_compare_db()
    tickers = get_compare_targets_from_notion()

    if not tickers:
        print("📌 比較対象の企業が見つかりませんでした。")
        return

    for ticker in tickers:
        latest_year = get_latest_year_in_db(ticker) or BASE_YEAR
        years_5 = [latest_year - i for i in range(5)]
        years_5.reverse()

        print(
            f"\n=== 比較用データ収集: 証券コード {ticker} (基準年: {latest_year}年) ==="
        )

        for yr in years_5:
            if is_cf_exists(ticker, yr):
                print(f"  └ 【スキップ】 {yr}年（すでにCFデータが存在します）")
                continue

            print(f"  └ 【取得中】 {yr}年 データを検索...")
            cf_data = fetch_and_parse_cf(ticker, yr)
            if cf_data:
                save_compare_data_to_db(cf_data)
                print(f"  └ 【保存完了】 {yr}年 データ")
            else:
                print(f"  └ 【取得失敗】 {yr}年（データが見つかりませんでした）")


if __name__ == "__main__":
    print("=== 比較表用データセットアップ処理を開始します ===")
    sync_compare_data()
