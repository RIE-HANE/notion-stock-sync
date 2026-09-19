import glob
import os
import sqlite3
import time
from datetime import datetime
import japanize_matplotlib
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import requests

# --- 環境変数から設定を取得 ---
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
GITHUB_REPOSITORY = os.environ.get(
    "GITHUB_REPOSITORY", "RIE-HANE/notion-stock-sync"
)
DB_FILE = "financial_data.db"

# 処理日の日付文字列 (YYYY-MM-DD)
TODAY_STR = datetime.now().strftime("%Y-%m-%d")


def get_notion_pages():
    """Notionデータベースから全企業リストを動的に取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    payload = {"sorts": [{"property": "名前", "direction": "ascending"}]}
    res = requests.post(url, headers=headers, json=payload)

    pages = []
    if res.status_code != 200:
        print(f"Notion API エラー: {res.text}")
        return pages

    results = res.json().get("results", [])
    for page in results:
        props = page.get("properties", {})
        name = "不明"
        ticker = None
        target_3years = False

        for prop_name, prop_val in props.items():
            p_type = prop_val.get("type")
            if p_type == "title":
                title_arr = prop_val.get("title", [])
                if title_arr:
                    name = title_arr[0].get("plain_text", "不明")

            if any(
                k in prop_name.lower() for k in ["コード", "ticker", "code", "証券"]
            ):
                if p_type == "rich_text":
                    txt_arr = prop_val.get("rich_text", [])
                    if txt_arr:
                        ticker = txt_arr[0].get("plain_text")
                elif p_type == "number":
                    ticker = str(prop_val.get("number"))

            if p_type == "checkbox" and (
                "3年" in prop_name or "過去" in prop_name
            ):
                target_3years = prop_val.get("checkbox", False)

        if ticker:
            pages.append(
                {
                    "page_id": page["id"],
                    "name": name,
                    "ticker": str(ticker).strip(),
                    "target_3years": target_3years,
                }
            )

    return pages


def get_or_create_subpage(parent_page_id, subpage_title):
    """親企業ページ直下に指定タイトルのサブページが存在するか確認し、なければ作成してpage_idを返す"""
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # 1. 親ページ直下のブロック一覧から既存サブページを検索
    url = f"https://api.notion.com/v1/blocks/{parent_page_id}/children"
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        blocks = res.json().get("results", [])
        for b in blocks:
            if b.get("type") == "child_page":
                if b.get("child_page", {}).get("title") == subpage_title:
                    return b["id"]

    # 2. 存在しない場合は新規作成
    create_url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"page_id": parent_page_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": subpage_title}}]
            }
        },
    }
    res_create = requests.post(create_url, headers=headers, json=payload)
    if res_create.status_code == 200:
        subpage_id = res_create.json().get("id")
        print(f"  └ 【サブページ作成】 '{subpage_title}' を作成しました")
        return subpage_id
    else:
        print(f"  └ サブページ作成エラー: {res_create.text}")
        return parent_page_id


def get_existing_notion_image_years(page_id):
    """指定ページ（サブページ含む）内にすでに存在する年度ブロックを検出"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
    }
    res = requests.get(url, headers=headers)
    existing_years = set()

    if res.status_code == 200:
        blocks = res.json().get("results", [])
        for block in blocks:
            b_type = block.get("type")
            if b_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
                txts = block.get(b_type, {}).get("rich_text", [])
                for t in txts:
                    content = t.get("plain_text", "")
                    for yr in range(2020, 2035):
                        if f"{yr}年度" in content:
                            existing_years.add(yr)
    return existing_years


def get_latest_year_for_ticker(ticker):
    """DBに保存されている該当企業の最新年度（MAX年）を動的に取得"""
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT MAX(year) FROM financial_metrics WHERE ticker = ?",
            (str(ticker).strip(),),
        )
        row = cursor.fetchone()
        conn.close()
        if row and row[0] is not None:
            return int(row[0])

    return datetime.now().year - 1


def is_data_created_today(ticker, year):
    """DB内に指定企業・年度のデータが存在し、かつ作成日(created_at)が処理日(TODAY_STR)と同じか判定"""
    if not os.path.exists(DB_FILE):
        return False

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 1 FROM financial_metrics 
        WHERE ticker = ? AND year = ? AND created_at = ?
    """,
        (str(ticker).strip(), int(year), TODAY_STR),
    )

    row = cursor.fetchone()
    conn.close()
    return row is not None


def fetch_financial_data(ticker, year):
    """SQLデータベースから 'ticker' と 'year' の実データを取得。"""
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT total_assets, current_assets, fixed_assets, current_liab, 
                   fixed_liab, equity, sales, op_profit, net_income
            FROM financial_metrics
            WHERE ticker = ? AND year = ?
        """,
            (str(ticker).strip(), int(year)),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "total_assets": row[0],
                "current_assets": row[1],
                "fixed_assets": row[2],
                "current_liab": row[3],
                "fixed_liab": row[4],
                "equity": row[5],
                "sales": row[6],
                "op_profit": row[7],
                "net_income": row[8],
            }

    return None


def format_amount(amount):
    """金額（億円）に応じて小数点以下の表示桁数を最適化"""
    abs_amt = abs(amount)
    if abs_amt >= 100:
        return f"{amount:,.0f}"
    elif abs_amt >= 10:
        return f"{amount:,.1f}"
    else:
        return f"{amount:,.2f}"


def create_financial_chart(
    company_name, year_label, financial_data, output_path
):
    """財務構造分析図（BS/PL）を作成（5%以上で図中項目名のみ表示版）"""
    fig, ax = plt.subplots(figsize=(11, 7))

    # --- 単位の正規化 (円 -> 億円) ---
    raw_total_assets = financial_data.get("total_assets", 0)
    scale = 1e8 if raw_total_assets > 1e6 else 1.0

    total_assets = max(raw_total_assets / scale, 1.0)
    current_assets = financial_data.get("current_assets", 0) / scale
    fixed_assets = financial_data.get("fixed_assets", 0) / scale
    current_liab = financial_data.get("current_liab", 0) / scale
    fixed_liab = financial_data.get("fixed_liab", 0) / scale
    equity = financial_data.get("equity", 0) / scale

    sales = financial_data.get("sales", 0) / scale
    op_profit = financial_data.get("op_profit", 0) / scale
    net_income = financial_data.get("net_income", 0) / scale

    # 構成比（%）の計算
    ca_h = (current_assets / total_assets) * 100
    fa_h = (fixed_assets / total_assets) * 100
    cl_h = (current_liab / total_assets) * 100
    fl_h = (fixed_liab / total_assets) * 100
    eq_h = (equity / total_assets) * 100

    sales_h = (sales / total_assets) * 100
    op_h = (op_profit / total_assets) * 100 if op_profit > 0 else 0
    op_ratio = (op_profit / sales * 100) if sales > 0 else 0

    # 財務指標の計算
    fin_lev = total_assets / equity if equity > 0 else 0
    asset_turnover = sales / total_assets if total_assets > 0 else 0
    profit_margin = (net_income / sales) * 100 if sales > 0 else 0
    roe = (net_income / equity) * 100 if equity > 0 else 0

    # --- 指標テーブル作成 ---
    table_data = [
        ["ROE", f"{roe:.1f}%"],
        ["財務レバレッジ", f"{fin_lev:.2f}"],
        ["総資本回転率", f"{asset_turnover:.2f}"],
        ["当期純利益率", f"{profit_margin:.1f}%"],
    ]

    table = ax.table(
        cellText=table_data,
        colWidths=[0.22, 0.18],
        loc="upper right",
        bbox=[1.02, 0.05, 0.40, 0.28],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    for cell in table.get_celld().values():
        cell.set_edgecolor("#cccccc")
        cell.set_linewidth(1)

    # --- 凡例用ラベルの作成 ---
    label_fa = f"固定資産 : {format_amount(fixed_assets)}億円 ({fa_h:.1f}%)"
    label_ca = f"流動資産 : {format_amount(current_assets)}億円 ({ca_h:.1f}%)"
    label_eq = f"純資産     : {format_amount(equity)}億円 ({eq_h:.1f}%)"
    label_fl = f"固定負債 : {format_amount(fixed_liab)}億円 ({fl_h:.1f}%)"
    label_cl = f"流動負債 : {format_amount(current_liab)}億円 ({cl_h:.1f}%)"
    label_sales = f"売上高     : {format_amount(sales)}億円 ({sales_h:.1f}%)"
    label_op = f"営業利益 : {format_amount(op_profit)}億円 ({op_ratio:.1f}%)"

    # --- グラフ描画 ---
    # 左柱：資産
    ax.add_patch(
        patches.Rectangle(
            (5, 0), 25, fa_h, facecolor="#4682b4", edgecolor="black", label=label_fa
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (5, fa_h), 25, ca_h, facecolor="#87ceeb", edgecolor="black", label=label_ca
        )
    )

    # 右柱：負債・純資産
    ax.add_patch(
        patches.Rectangle(
            (33, 0), 25, eq_h, facecolor="#90ee90", edgecolor="black", label=label_eq
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (33, eq_h), 25, fl_h, facecolor="#cd5c5c", edgecolor="black", label=label_fl
        )
    )
    ax.add_patch(
        patches.Rectangle(
            (33, eq_h + fl_h), 25, cl_h, facecolor="#f08080", edgecolor="black", label=label_cl
        )
    )

    # PL柱：売上高・営業利益
    ax.add_patch(
        patches.Rectangle(
            (68, 0), 18, sales_h, facecolor="#ffcccb", edgecolor="black", label=label_sales
        )
    )
    if op_h > 0:
        ax.add_patch(
            patches.Rectangle(
                (68, 0), 18, op_h, facecolor="#ff4500", edgecolor="black", label=label_op
            )
        )

    # --- 図の中に納まる場合のみ項目名テキスト（文字列のみ）をセット (高さ5%以上) ---
    if fa_h >= 5:
        ax.text(17.5, fa_h / 2, "固定資産", ha="center", va="center", fontsize=9, fontweight="bold", color="white")
    if ca_h >= 5:
        ax.text(17.5, fa_h + ca_h / 2, "流動資産", ha="center", va="center", fontsize=9, fontweight="bold")

    if eq_h >= 5:
        ax.text(45.5, eq_h / 2, "純資産", ha="center", va="center", fontsize=9, fontweight="bold")
    if fl_h >= 5:
        ax.text(45.5, eq_h + fl_h / 2, "固定負債", ha="center", va="center", fontsize=9, fontweight="bold", color="white")
    if cl_h >= 5:
        ax.text(45.5, eq_h + fl_h + cl_h / 2, "流動負債", ha="center", va="center", fontsize=9, fontweight="bold")

    if sales_h >= 5:
        # 営業利益の領域と重ならない中央位置に「売上高」とだけ表示
        sales_text_y = (sales_h + op_h) / 2 if op_h >= 5 else sales_h / 2
        ax.text(77, sales_text_y, "売上高", ha="center", va="center", fontsize=9, fontweight="bold")
    if op_h >= 5:
        ax.text(77, op_h / 2, "営業利益", ha="center", va="center", fontsize=8, fontweight="bold", color="white")

    # --- 柱の下のカテゴリ名 ---
    ax.text(17.5, -4, "資産の部", ha="center", va="top", fontsize=10, fontweight="bold")
    ax.text(45.5, -4, "負債・純資産の部", ha="center", va="top", fontsize=10, fontweight="bold")
    ax.text(77, -4, "損益(PL)", ha="center", va="top", fontsize=10, fontweight="bold")

    # --- 凡例と配置調整 ---
    ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.45, 1.0),
        fontsize=9.5,
        frameon=True,
        edgecolor="#cccccc",
    )
    ax.set_xlim(0, 95)
    ax.set_ylim(-8, max(110, sales_h + 12))
    plt.axis("off")
    plt.title(
        f"{company_name} ({year_label}) 財務構造分析図", fontsize=15, pad=15
    )

    os.makedirs("images", exist_ok=True)
    plt.savefig(output_path, bbox_inches="tight", dpi=200)
    plt.close()


def sync_pending_images_to_notion(tasks):
    """Notionのサブページへ生成画像を連携追加"""
    now_ts = int(time.time())
    for task in tasks:
        subpage_id = task["subpage_id"]
        chart_list = task["chart_list"]
        chart_list = sorted(task["chart_list"], key=lambda x: x["year"])
        
        for item in chart_list:
            year = item["year"]
            rel_path = item["rel_path"]
            
            upload_image_to_notion_subpage(subpage_id, year, rel_path)

        children_blocks = []
        for item in chart_list:
            filename = os.path.basename(item["rel_path"])
            raw_image_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/images/{filename}?v={now_ts}"

            children_blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"▼ {item['year']}年度 財務構造 (BS/PL)"
                                },
                            }
                        ]
                    },
                }
            )
            children_blocks.append(
                {
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": raw_image_url},
                    },
                }
            )

        url = f"https://api.notion.com/v1/blocks/{subpage_id}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        res = requests.patch(
            url, headers=headers, json={"children": children_blocks}
        )
        if res.status_code == 200:
            print(f"Notionサブページへ {len(chart_list)}枚 の画像を追加しました。")
        else:
            print(f"Notion画像追加エラー: {res.text}")


if __name__ == "__main__":
    mode = os.environ.get("SYNC_MODE", "GENERATE")

    if mode == "GENERATE":
        print(
            f"【Phase 1】作図処理を開始します (判定基準日: {TODAY_STR})..."
        )
        os.makedirs("images", exist_ok=True)
        companies = get_notion_pages()

        for comp in companies:
            ticker = comp.get("ticker")
            name = comp.get("name")
            page_id = comp.get("page_id")
            target_3years = comp.get("target_3years")

            if not ticker or str(ticker) == "None":
                continue

            print(f"\n--- 処理開始: {name} (コード: {ticker}) ---")

            # ★ サブページ「財務構造分析 (BS/PL)」の取得/作成
            subpage_id = get_or_create_subpage(page_id, "財務構造分析 (BS/PL)")

            # サブページ内の既存年度を取得
            existing_years = get_existing_notion_image_years(subpage_id)

            latest_year = get_latest_year_for_ticker(ticker)

            target_years = (
                [latest_year - 2, latest_year - 1, latest_year]
                if target_3years
                else [latest_year]
            )

            for yr in target_years:
                if yr in existing_years:
                    print(
                        f"【スキップ】{yr}年度の画像はすでにNotionサブページ内に存在します。"
                    )
                    continue

                if not is_data_created_today(ticker, yr):
                    print(
                        f"【スキップ】{name} ({ticker}) の {yr}年度データがDBに存在しない、または本日 ({TODAY_STR}) 作成されたデータではありません。"
                    )
                    continue

                fin_data = fetch_financial_data(ticker, yr)
                if not fin_data:
                    print(
                        f"【スキップ】{name} ({ticker}) の {yr}年度データがDBに見つかりません。"
                    )
                    continue

                file_name = f"{ticker}_{yr}.png"
                rel_path = f"images/{file_name}"
                create_financial_chart(name, f"{yr}年度", fin_data, rel_path)
                print(f"【作成成功】{yr}年度の画像を生成しました: {rel_path}")

    elif mode == "NOTION_SYNC":
        print("【Phase 2】未追加の画像のみNotionサブページへ反映中...")
        companies = get_notion_pages()
        pending_tasks = []

        for comp in companies:
            ticker = comp.get("ticker")
            page_id = comp.get("page_id")
            if not ticker or str(ticker) == "None":
                continue

            # サブページ「財務構造分析 (BS/PL)」を取得
            subpage_id = get_or_create_subpage(page_id, "財務構造分析 (BS/PL)")

            existing_years = get_existing_notion_image_years(subpage_id)
            local_files = glob.glob(f"images/{ticker}_*.png")
            chart_list = []

            for file_path in local_files:
                filename = os.path.basename(file_path)
                try:
                    yr = int(filename.split("_")[1].split(".")[0])
                    if yr not in existing_years and is_data_created_today(
                        ticker, yr
                    ):
                        rel_path = f"images/{filename}".replace("\\", "/")
                        chart_list.append({"year": yr, "rel_path": rel_path})
                except Exception:
                    continue

            if chart_list:
                chart_list = sorted(chart_list, key=lambda x: x["year"])
                pending_tasks.append(
                    {"subpage_id": subpage_id, "chart_list": chart_list}
                )

        if pending_tasks:
            sync_pending_images_to_notion(pending_tasks)
        else:
            print("Notionへ同期する新規画像はありません。")
