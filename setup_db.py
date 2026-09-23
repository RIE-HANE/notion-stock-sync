import calendar
import datetime
import io
import os
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
import requests

today = datetime.date.today()
TODAY_STR = today.strftime("%Y-%m-%d")

if (today.month, today.day) < (6, 30):
    BASE_YEAR = today.year - 2
else:
    BASE_YEAR = today.year - 1

# setup_db.py があるディレクトリ（＝リポジトリルート）直下の financial_data.db を指定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "financial_data.db")

# データベースの初期化
def init_db():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_metrics (
            ticker TEXT,
            year INTEGER,
            fiscal_month INTEGER,
            total_assets REAL,
            current_assets REAL,
            fixed_assets REAL,
            current_liab REAL,
            fixed_liab REAL,
            equity REAL,
            sales REAL,
            op_profit REAL,
            net_income REAL,
            created_at TEXT,
            del_flg INTEGER DEFAULT 0,
            PRIMARY KEY (ticker, year)
        )
    """)

    # 既存テーブルへのカラム追加（移行対策）
    cursor.execute("PRAGMA table_info(financial_metrics)")
    columns = [column[1] for column in cursor.fetchall()]
    if "del_flg" not in columns:
        cursor.execute(
            "ALTER TABLE financial_metrics ADD COLUMN del_flg INTEGER DEFAULT 0"
        )
    if "fiscal_month" not in columns:
        cursor.execute(
            "ALTER TABLE financial_metrics ADD COLUMN fiscal_month INTEGER"
        )

    conn.commit()
    conn.close()


# 指定した企業・年度の有効データ（del_flg = 0）がすでにDBにあるか確認
def is_data_exists(ticker, year):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1 FROM financial_metrics 
        WHERE ticker = ? AND year = ? AND del_flg = 0
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
        SELECT MAX(year) FROM financial_metrics 
        WHERE ticker = ? AND del_flg = 0
    """,
        (str(ticker),),
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result and result[0] is not None else None


# Notionから全対象企業・過去フラグ・決算月（入力がある場合）を取得
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
            fiscal_month = None

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

                # 「過去」フラグ判定
                if p_type == "checkbox" and any(
                    k in prop_name for k in ["過去", "3年", "複数年"]
                ):
                    target_3years = prop_val.get("checkbox", False)

                # 決算月を取得（入力がある場合のみ）
                if any(
                    k in prop_name for k in ["決算", "決算月", "決算期"]
                ):
                    if p_type == "number":
                        fiscal_month = prop_val.get("number")
                    elif p_type == "select" and prop_val.get("select"):
                        val_str = prop_val["select"].get("name", "")
                        fiscal_month = int("".join(filter(str.isdigit, val_str)) or 0)
                    elif p_type == "rich_text":
                        txt_arr = prop_val.get("rich_text", [])
                        if txt_arr:
                            val_str = txt_arr[0].get("plain_text", "")
                            fiscal_month = int("".join(filter(str.isdigit, val_str)) or 0)

            if ticker:
                companies.append(
                    {
                        "ticker": ticker.strip(),
                        "target_3years": target_3years,
                        "fiscal_month": fiscal_month if fiscal_month and 1 <= fiscal_month <= 12 else None,
                    }
                )

        print(f"✅ Notionから取得した企業数: {len(companies)}件")
        return companies

    except Exception as e:
        print(f"Notion連携エラー: {e}")
        return []


def safe_decode(raw_bytes):
    for enc in ["utf-8", "shift_jis", "cp932", "euc-jp"]:
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="ignore")


# EDINET API から財務データを検索・取得
def fetch_edinet_data(ticker, year, fiscal_month=None, retry_count=1):
    api_key = os.getenv("EDINET_API_KEY")
    if not api_key:
        print("⚠ EDINET_API_KEY が設定されていません", flush=True)
        return None

    target_year = year + 1

    # 1. Notion等に入力がある場合：特別対応
    if fiscal_month:
        m1 = (fiscal_month + 2) if (fiscal_month + 2) <= 12 else (fiscal_month + 2 - 12)
        m2 = (fiscal_month + 3) if (fiscal_month + 3) <= 12 else (fiscal_month + 3 - 12)
        target_months = [m1, m2]
        print(
            f"   -> EDINET APIで {ticker} ({year}年度) のデータをピンポイント検索中... (特別対応: {fiscal_month}月決算 ➔ 対象月: {target_months})",
            flush=True,
        )
    # 2. 入力がない場合：従前とおり target_months = [3, 6, 9, 12]
    else:
        target_months = [3, 6, 9, 12]
        print(
            f"   -> EDINET APIで {ticker} ({year}年度) のデータをピンポイント検索中...",
            flush=True,
        )

    doc_id = None

    for month in target_months:
        # 月の最終日を取得 (例: 6月なら30日、12月なら31日)
        _, last_day = calendar.monthrange(target_year, month)

        # 10日〜月末までの日付リストを作成 (早出し企業対策)
        start_date = datetime.date(target_year, month, 10)
        end_date = datetime.date(target_year, month, last_day)

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
                res = requests.get(url, params=params, timeout=10)
                if res.status_code != 200:
                    continue

                results = res.json().get("results", [])

                for doc in results:
                    if str(doc.get("docTypeCode")) == "120":  # 有価証券報告書
                        sec_code = doc.get("secCode")

                        if sec_code in [f"{ticker}0", str(ticker)]:
                            doc_id = doc.get("docID") or doc.get("docId")
                            print(
                                f"     ✓ 書類発見 ({date_str}): docID={doc_id}",
                                flush=True,
                            )

                            fin_data = parse_edinet_xbrl(
                                doc_id, ticker, year, api_key
                            )
                            if fin_data:
                                fin_data["fiscal_month"] = fiscal_month
                            return fin_data

            except Exception:
                continue

    if not doc_id and retry_count > 0:
        print(
            f"     ⚠ {year}年度のデータがないため、1年引いて ({year - 1}年度) 再検索します...",
            flush=True,
        )
        return fetch_edinet_data(
            ticker, year - 1, fiscal_month=fiscal_month, retry_count=retry_count - 1
        )

    if not doc_id:
        print(
            f"     ⚠ {year}年度の書類が見つかりませんでした (ticker: {ticker})",
            flush=True,
        )
        return None


def parse_edinet_xbrl(doc_id, ticker, year, api_key):
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
                        context = elem.attrib.get("contextRef", "")

                        if any(
                            k in context
                            for k in [
                                "NonConsolidated",
                                "Prior",
                                "Comparative",
                            ]
                        ):
                            continue

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

        def get_val(*keys):
            for key in keys:
                val = data_dict.get(key)
                if val:
                    try:
                        return float(val)
                    except ValueError:
                        continue
            return 0.0

        current_assets = get_val("CurrentAssetsIFRS", "CurrentAssets")
        fixed_assets = get_val("NonCurrentAssetsIFRS", "NonCurrentAssets")

        total_assets = (
            get_val("TotalAssetsSummaryOfBusinessResults")
            or get_val("AssetsIFRS", "TotalAssets", "Assets")
            or (current_assets + fixed_assets)
        )

        current_liab = get_val(
            "TotalCurrentLiabilitiesIFRS",
            "CurrentLiabilitiesIFRS",
            "CurrentLiabilities",
        )

        equity = get_val(
            "EquityAttributableToOwnersOfParentIFRS",
            "EquityIFRS",
            "Equity",
            "NetAssetsSummaryOfBusinessResults",
            "NetAssets",
        )

        fixed_liab = get_val(
            "NonCurrentLabilitiesIFRS",
            "NonCurrentLiabilitiesIFRS",
            "TotalNonCurrentLiabilitiesIFRS",
            "NonCurrentLiabilities",
        )

        if fixed_liab == 0.0 and total_assets > 0 and current_liab > 0 and equity > 0:
            fixed_liab = total_assets - current_liab - equity

        sales = get_val(
            "RevenueIFRS",
            "NetSalesSummaryOfBusinessResults",
            "RevenueSummaryOfBusinessResults",
            "NetSales",
            "Revenue",
        )

        op_profit = get_val(
            "OperatingProfitLossIFRS",
            "OperatingIncomeLossSummaryOfBusinessResults",
            "OperatingProfitLossSummaryOfBusinessResults",
            "OperatingIncome",
            "OperatingProfit",
        )

        net_income = get_val(
            "ProfitLossAttributableToOwnersOfParentIFRS",
            "ProfitLossIFRS",
            "NetIncomeLossSummaryOfBusinessResults",
            "ProfitLossSummaryOfBusinessResults",
            "ProfitLoss",
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
        }

    except Exception as e:
        print(f"     ⚠ XBRLパース失敗 ({ticker}): {e}")
        return None


def upsert_financial_data(data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO financial_metrics (
            ticker, year, fiscal_month, total_assets, current_assets, fixed_assets,
            current_liab, fixed_liab, equity, sales, op_profit, net_income, created_at, del_flg
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        ON CONFLICT(ticker, year) DO UPDATE SET
            fiscal_month=excluded.fiscal_month,
            total_assets=excluded.total_assets,
            current_assets=excluded.current_assets,
            fixed_assets=excluded.fixed_assets,
            current_liab=excluded.current_liab,
            fixed_liab=excluded.fixed_liab,
            equity=excluded.equity,
            sales=excluded.sales,
            op_profit=excluded.op_profit,
            net_income=excluded.net_income,
            created_at=excluded.created_at,
            del_flg=0
    """,
        (
            data["ticker"],
            data["year"],
            data.get("fiscal_month"),
            data["total_assets"],
            data["current_assets"],
            data["fixed_assets"],
            data["current_liab"],
            data["fixed_liab"],
            data["equity"],
            data["sales"],
            data["op_profit"],
            data["net_income"],
            TODAY_STR,
        ),
    )
    conn.commit()
    conn.close()


def sync_db_from_edinet():
    init_db()
    companies = get_notion_companies()

    if not companies:
        print("Notionから対象企業を取得できませんでした。")
        return

    print(f"📌 自動算出された基準年度: {BASE_YEAR}年 (本日: {TODAY_STR})")

    for comp in companies:
        ticker = comp["ticker"]
        target_3years = comp["target_3years"]
        fiscal_month = comp["fiscal_month"]

        db_latest_year = get_latest_year_in_db(ticker)

        print(
            f"\n--- 処理中: 証券コード {ticker} (DB最新: {db_latest_year or 'なし'} / 決算月指定: {fiscal_month or 'なし(通常処理)'}) ---"
        )

        needed_years = (
            [BASE_YEAR - 2, BASE_YEAR - 1, BASE_YEAR]
            if target_3years
            else [BASE_YEAR]
        )

        for yr in needed_years:
            if is_data_exists(ticker, yr):
                print(f"   └ 【スキップ】 {yr}年（すでにDBに存在します）")
                continue

            fin_data = fetch_edinet_data(ticker, yr, fiscal_month=fiscal_month)
            if fin_data:
                upsert_financial_data(fin_data)
                print(f"   └ 【登録/更新完了】 {fin_data['year']}年")
            else:
                print(
                    f"   └ 【取得失敗】 {yr}年（EDINETにデータがありません）"
                )


if __name__ == "__main__":
    print("=== DBセットアップ処理を開始します ===")
    sync_db_from_edinet()
