import os
import sqlite3
import time
import japanize_matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import requests

# 環境変数
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "RIE-HANE/notion-stock-sync")
DB_FILE = "financial_data.db"


def get_notion_pages_with_relation():
    """比較欄（Relation）に値が入っている企業のみ取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    payload = {
        "filter": {
            "property": "比較",
            "relation": {"is_not_empty": True},
        }
    }

    res = requests.post(url, headers=headers, json=payload)
    pages = []

    if res.status_code != 200:
        print(f"Notion API エラー: {res.text}")
        return pages

    results = res.json().get("results", [])
    for page in results:
        props = page.get("properties", {})

        # 企業名
        name = "不明"
        for k, v in props.items():
            if v.get("type") == "title" and v.get("title"):
                name = v["title"][0].get("plain_text", "不明")
                break

        # 証券コード
        ticker = None
        for k, v in props.items():
            if any(key in k.lower() for key in ["コード", "ticker", "code", "証券"]):
                if v.get("type") == "rich_text" and v.get("rich_text"):
                    ticker = v["rich_text"][0].get("plain_text")
                elif v.get("type") == "number":
                    ticker = str(v.get("number"))

        # 比較対象のページID
        relation_list = props.get("比較", {}).get("relation", [])
        if relation_list and ticker:
            target_page_id = relation_list[0]["id"]
            pages.append(
                {
                    "page_id": page["id"],
                    "name": name,
                    "ticker": ticker.strip(),
                    "target_page_id": target_page_id,
                }
            )

    return pages


def get_company_detail_by_id(page_id):
    """ページIDから比較対象企業の名前と証券コードを取得"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
    }
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return "比較対象企業", "0000"

    props = res.json().get("properties", {})
    name = "比較対象企業"
    ticker = "0000"

    for k, v in props.items():
        if v.get("type") == "title" and v.get("title"):
            name = v["title"][0].get("plain_text", "比較対象企業")
        if any(key in k.lower() for key in ["コード", "ticker", "code", "証券"]):
            if v.get("type") == "rich_text" and v.get("rich_text"):
                ticker = v["rich_text"][0].get("plain_text")
            elif v.get("type") == "number":
                ticker = str(v.get("number"))

    return name, ticker.strip()


# 数値を三桁区切り＆マイナスを「△ 」記号（百万円単位）にフォーマットする関数
def format_cf_value(val):
    if pd.isna(val) or val is None:
        return "-"
    # 円から百万円に変換（四捨五入）
    val_m = round(val / 1_000_000)
    if val_m < 0:
        return f"△ {abs(val_m):,}"
    return f"{val_m:,}"


def fetch_cf_data_from_db(ticker):
    """SQLite (financial_data.db) から対象企業の過去5期分＋5年計のCFデータを取得"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 過去5期分のCFデータを昇順で取得
    query = """
        SELECT year, operating_cf, investing_cf, financing_cf
        FROM financial_metrics
        WHERE ticker = ? AND operating_cf IS NOT NULL
        ORDER BY year DESC
        LIMIT 5
    """
    cursor.execute(query, (str(ticker),))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        # データが存在しない場合のダミー表示用
        return (
            ["----年", "----年", "----年", "----年", "----年", "5年計"],
            [["-"] * 6, ["-"] * 6, ["-"] * 6],
        )

    # 年度の古い順（過去→最新）に並び替え
    rows.reverse()

    years = [f"{r[0]}年\n3月期" for r in rows] + ["5年計"]

    op_cfs = [r[1] or 0 for r in rows]
    inv_cfs = [r[2] or 0 for r in rows]
    fin_cfs = [r[3] or 0 for r in rows]

    # 5年計の計算
    sum_op = sum(op_cfs)
    sum_inv = sum(inv_cfs)
    sum_fin = sum(fin_cfs)

    # 文字列（百万円・△フォーマット）に変換
    op_str = [format_cf_value(v) for v in op_cfs] + [format_cf_value(sum_op)]
    inv_str = [format_cf_value(v) for v in inv_cfs] + [format_cf_value(sum_inv)]
    fin_str = [format_cf_value(v) for v in fin_cfs] + [format_cf_value(sum_fin)]

    cf_matrix = [op_str, inv_str, fin_str]

    return years, cf_matrix


def create_two_company_cf_table_image(
    comp_a_name, comp_b_name, years_a, cf_a, years_b, cf_b, output_path
):
    """表画像を生成 (日本語フォント文字化け対策版)"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 5.2))
    fig.patch.set_facecolor("white")

    # Linux (GitHub Actions) / Windows / Mac のいずれの環境でも対応する日本語フォントリスト
    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "TakaoPGothic",
        "IPAGothic",
        "Meiryo",
        "MS Gothic",
        "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = (
        False  # マイナス記号の文字化け（豆腐化）を防止
    )

    rows = ["営業CF", "投資CF", "財務CF"]

    # 自社 (A社)
    ax1.axis("off")
    ax1.set_title(
        f"  {comp_a_name}  ",
        fontsize=11,
        fontweight="bold",
        loc="left",
        bbox=dict(
            boxstyle="round,pad=0.3",
            facecolor="white",
            edgecolor="black",
            linewidth=1,
        ),
    )

    t1 = ax1.table(
        cellText=cf_a,
        rowLabels=rows,
        colLabels=years_a,
        loc="bottom",
        cellLoc="center",
    )
    t1.auto_set_font_size(False)
    t1.set_fontsize(9)
    t1.scale(1, 1.6)

    for (r, c), cell in t1.get_celld().items():
        if r == 0:
            cell.set_facecolor("#EFEFEF")
            cell.set_text_props(weight="bold")
        if c == -1:
            cell.set_facecolor("#FFFFFF")
            cell.set_text_props(weight="bold")

    # 比較対象社 (B社)
    ax2.axis("off")
    ax2.set_title(
        f"  {comp_b_name}  ",
        fontsize=11,
        fontweight="bold",
        loc="left",
        bbox=dict(
            boxstyle="round,pad=0.3",
            facecolor="white",
            edgecolor="black",
            linewidth=1,
        ),
    )

    t2 = ax2.table(
        cellText=cf_b,
        rowLabels=rows,
        colLabels=years_b,
        loc="bottom",
        cellLoc="center",
    )
    t2.auto_set_font_size(False)
    t2.set_fontsize(9)
    t2.scale(1, 1.6)

    for (r, c), cell in t2.get_celld().items():
        if r == 0:
            cell.set_facecolor("#EFEFEF")
            cell.set_text_props(weight="bold")
        if c == -1:
            cell.set_facecolor("#FFFFFF")
            cell.set_text_props(weight="bold")

    fig.text(0.85, 0.95, "(単位：百万円)", fontsize=9, ha="right")

    plt.tight_layout()
    os.makedirs("images", exist_ok=True)
    plt.savefig(output_path, bbox_inches="tight", dpi=200)
    plt.close()

def sync_compare_images_to_notion(tasks):
    """Notionへ比較表のサブページを作成し、その中に画像のみを反映（メインページやサブページにテキストタイトルを挿入しない）"""
    now_ts = int(time.time())
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    for task in tasks:
        page_id = task["page_id"]
        rel_path = task["rel_path"]
        filename = os.path.basename(rel_path)
        raw_image_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/images/{filename}?v={now_ts}"

        # 1. 親ページの中に「サブページ」を新規作成する
        create_page_url = "https://api.notion.com/v1/pages"
        subpage_payload = {
            "parent": {"page_id": page_id},  # 親ページのID
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {
                                "content": f"📊 CF比較 ({task['comp_a_name']} vs {task['comp_b_name']})"
                            },
                        }
                    ]
                }
            },
            # サブページの中身（画像のみを配置し、余計なテキスト挿入をカット）
            "children": [
                {
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": raw_image_url},
                    },
                },
            ],
        }

        res = requests.post(
            create_page_url, headers=headers, json=subpage_payload
        )
        if res.status_code == 200:
            print(
                f"✅ Notionにサブページを作成して画像を反映しました: {task['comp_a_name']} vs {task['comp_b_name']}"
            )
        else:
            print(f"⚠ Notionサブページ作成エラー: {res.text}")


if __name__ == "__main__":
    mode = os.environ.get("SYNC_MODE", "GENERATE")

    if mode == "GENERATE":
        print("【Phase 1】DBから比較データを集計し、表画像を生成します...")
        targets = get_notion_pages_with_relation()
        print(f"比較対象が設定されている企業数: {len(targets)} 件")

        for item in targets:
            comp_a_name = item["name"]
            ticker_a = item["ticker"]

            comp_b_name, ticker_b = get_company_detail_by_id(
                item["target_page_id"]
            )
            print(
                f"\n--- 表画像作成: {comp_a_name} ({ticker_a})  vs  {comp_b_name} ({ticker_b}) ---"
            )

            # DBから2社のCF実データを取得
            years_a, cf_a = fetch_cf_data_from_db(ticker_a)
            years_b, cf_b = fetch_cf_data_from_db(ticker_b)

            file_name = f"compare_{ticker_a}_vs_{ticker_b}.png"
            rel_path = f"images/{file_name}"

            # 綺麗に装飾された表画像を保存
            create_two_company_cf_table_image(
                comp_a_name,
                comp_b_name,
                years_a,
                cf_a,
                years_b,
                cf_b,
                rel_path,
            )
            print(f"【生成完了】{rel_path}")

    elif mode == "NOTION_SYNC":
        print("【Phase 2】生成された比較表画像をNotionへ同期します...")
        targets = get_notion_pages_with_relation()
        pending_tasks = []

        for item in targets:
            comp_a_name = item["name"]
            ticker_a = item["ticker"]
            comp_b_name, ticker_b = get_company_detail_by_id(
                item["target_page_id"]
            )

            file_name = f"compare_{ticker_a}_vs_{ticker_b}.png"
            rel_path = f"images/{file_name}"

            if os.path.exists(rel_path):
                pending_tasks.append(
                    {
                        "page_id": item["page_id"],
                        "comp_a_name": comp_a_name,
                        "comp_b_name": comp_b_name,
                        "rel_path": rel_path,
                    }
                )

        if pending_tasks:
            sync_compare_images_to_notion(pending_tasks)
        else:
            print("Notionへ同期する比較画像はありません。")
