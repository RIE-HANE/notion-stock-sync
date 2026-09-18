import os
import glob
import time
import sqlite3
import requests
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import japanize_matplotlib

# --- 環境変数から設定を取得 ---
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "RIE-HANE/notion-stock-sync")
DB_FILE = "financial_data.db"


def get_notion_pages():
    """Notionデータベースから全企業リストを動的に取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
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
            
            if any(k in prop_name.lower() for k in ["コード", "ticker", "code", "証券"]):
                if p_type == "rich_text":
                    txt_arr = prop_val.get("rich_text", [])
                    if txt_arr:
                        ticker = txt_arr[0].get("plain_text")
                elif p_type == "number":
                    ticker = str(prop_val.get("number"))
            
            if p_type == "checkbox" and ("3年" in prop_name or "過去" in prop_name):
                target_3years = prop_val.get("checkbox", False)

        if ticker:
            pages.append({
                "page_id": page["id"], 
                "name": name, 
                "ticker": str(ticker).strip(), 
                "target_3years": target_3years
            })
        
    return pages


def get_existing_notion_image_years(page_id):
    """Notionページ内にすでに存在する年度ブロックを検出"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28"
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
            (str(ticker).strip(),)
        )
        row = cursor.fetchone()
        conn.close()
        if row and row[0] is not None:
            return int(row[0])
    
    # DBに該当データがない場合のフォールバック（前年）
    return datetime.now().year - 1


def fetch_financial_data(ticker, year):
    """
    SQLデータベースから 'ticker' と 'year' の実データを取得。
    EDINETから取得した実データが存在しない場合は None を返します。
    """
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT total_assets, current_assets, fixed_assets, current_liab, 
                   fixed_liab, equity, sales, op_profit, net_income
            FROM financial_metrics
            WHERE ticker = ? AND year = ?
        ''', (str(ticker).strip(), int(year)))
        
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


def create_financial_chart(company_name, year_label, financial_data, output_path):
    """財務構造分析図（BS/PL）を作成（実数値に基づいた描画）"""
    fig, ax = plt.subplots(figsize=(10, 9))
    
    total_assets = max(financial_data.get("total_assets", 1000), 1)
    current_assets = financial_data.get("current_assets", 0)
    fixed_assets = financial_data.get("fixed_assets", 0)
    current_liab = financial_data.get("current_liab", 0)
    fixed_liab = financial_data.get("fixed_liab", 0)
    equity = financial_data.get("equity", 0)

    sales = financial_data.get("sales", 0)
    op_profit = financial_data.get("op_profit", 0)
    net_income = financial_data.get("net_income", 0)

    # 構成比（%）の計算
    ca_h = (current_assets / total_assets) * 100
    fa_h = (fixed_assets / total_assets) * 100
    cl_h = (current_liab / total_assets) * 100
    fl_h = (fixed_liab / total_assets) * 100
    eq_h = (equity / total_assets) * 100

    sales_h = (sales / total_assets) * 100
    op_h = (op_profit / total_assets) * 100 if op_profit > 0 else 0

    # 財務指標の計算
    fin_lev = total_assets / equity if equity > 0 else 0
    asset_turnover = sales / total_assets if total_assets > 0 else 0
    profit_margin = (net_income / sales) * 100 if sales > 0 else 0
    roe = (net_income / equity) * 100 if equity > 0 else 0

    # 指標テーブル作成
    table_data = [
        ["ROE", f"{roe:.1f}%"],
        ["財務レバレッジ", f"{fin_lev:.2f}"],
        ["総資本回転率", f"{asset_turnover:.2f}"],
        ["当期純利益率", f"{profit_margin:.1f}%"]
    ]

    table = ax.table(
        cellText=table_data,
        colWidths=[0.25, 0.20],
        loc='upper right',
        bbox=[1.10, 0.25, 0.45, 0.25]
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)

    for cell in table.get_celld().values():
        cell.set_edgecolor('#cccccc')
        cell.set_linewidth(1)

    # --- グラフ描画 ---
    # 左柱：資産（流動［上］＋ 固定［下］）
    ax.add_patch(patches.Rectangle((5, 100 - ca_h), 30, ca_h, facecolor='#87ceeb', edgecolor='black', label='流動資産'))
    ax.add_patch(patches.Rectangle((5, 0), 30, fa_h, facecolor='#4682b4', edgecolor='black', label='固定資産'))
    
    # 右柱：負債・純資産（流動負債［上］＋ 固定負債［中］＋ 純資産［下］）
    ax.add_patch(patches.Rectangle((35, 100 - cl_h), 30, cl_h, facecolor='#f08080', edgecolor='black', label='流動負債'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h - fl_h), 30, fl_h, facecolor='#cd5c5c', edgecolor='black', label='固定負債'))
    ax.add_patch(patches.Rectangle((35, 0), 30, eq_h, facecolor='#90ee90', edgecolor='black', label='純資産'))

    # PL柱：売上高・営業利益
    ax.add_patch(patches.Rectangle((75, 0), 20, sales_h, facecolor='#ffcccb', edgecolor='black', label='売上高'))
    if op_h > 0:
        ax.add_patch(patches.Rectangle((75, 0), 20, op_h, facecolor='#ff4500', edgecolor='black', label='営業利益'))

    # --- ラベル表示 ---
    ax.text(20, 100 - ca_h/2, f'流動資産\n{current_assets:,.0f}億円\n{ca_h:.1f}%', ha='center', va='center', fontsize=9, fontweight='bold')
    ax.text(20, fa_h/2, f'固定資産\n{fixed_assets:,.0f}億円\n{fa_h:.1f}%', ha='center', va='center', fontsize=9, fontweight='bold', color='white')
    ax.text(50, 100 - cl_h/2, f'流動負債\n{current_liab:,.0f}億円\n{cl_h:.1f}%', ha='center', va='center', fontsize=9, fontweight='bold')
    ax.text(50, 100 - cl_h - fl_h/2, f'固定負債\n{fixed_liab:,.0f}億円\n{fl_h:.1f}%', ha='center', va='center', fontsize=9, fontweight='bold', color='white')
    ax.text(50, eq_h/2, f'純資産\n{equity:,.0f}億円\n{eq_h:.1f}%', ha='center', va='center', fontsize=9, fontweight='bold')
    ax.text(85, sales_h + 3, f'売上高\n{sales:,.0f}億円', ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    if op_h > 3:
        ax.text(85, op_h/2, f'営業利益\n{op_profit:,.0f}億円\n{(op_profit/sales*100):.1f}%', ha='center', va='center', fontsize=8, fontweight='bold', color='white')

    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1), fontsize=10, frameon=True)
    ax.set_xlim(0, 110)
    ax.set_ylim(-10, max(110, sales_h + 15))
    plt.axis('off')
    plt.title(f"{company_name} ({year_label}) 財務構造分析図", fontsize=16, pad=20)
    
    os.makedirs("images", exist_ok=True)
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close()


def sync_pending_images_to_notion(tasks):
    """Notionへ生成画像を連携追加"""
    now_ts = int(time.time())
    for task in tasks:
        page_id = task['page_id']
        chart_list = sorted(task['chart_list'], key=lambda x: x['year'])
        
        children_blocks = []
        for item in chart_list:
            filename = os.path.basename(item['rel_path'])
            raw_image_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/images/{filename}?v={now_ts}"
            
            children_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": f"▼ {item['year']}年度 財務構造 (BS/PL)"}}]
                }
            })
            children_blocks.append({
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": raw_image_url}
                }
            })

        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        res = requests.patch(url, headers=headers, json={"children": children_blocks})
        if res.status_code == 200:
            print(f"Notionへ {len(chart_list)}枚 の画像を追加しました。")
        else:
            print(f"Notion画像追加エラー: {res.text}")


if __name__ == "__main__":
    mode = os.environ.get("SYNC_MODE", "GENERATE")
    
    if mode == "GENERATE":
        print("【Phase 1】作図処理を開始します...")
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
            existing_years = get_existing_notion_image_years(page_id)
            
            # ★ 企業ごとにDBから最新年度を取得（決算月に依存しない設計）
            latest_year = get_latest_year_for_ticker(ticker)
            
            # 3年フラグに応じて対象年度を判定
            target_years = [latest_year - 2, latest_year - 1, latest_year] if target_3years else [latest_year]

            for yr in target_years:
                if yr in existing_years:
                    print(f"【スキップ】{yr}年度の画像はすでにNotion内に存在します。")
                    continue
                
                fin_data = fetch_financial_data(ticker, yr)
                
                if not fin_data:
                    print(f"【スキップ】{name} ({ticker}) の {yr}年度データがDBに見つかりません。")
                    continue

                file_name = f"{ticker}_{yr}.png"
                rel_path = f"images/{file_name}"
                create_financial_chart(name, f"{yr}年度", fin_data, rel_path)
                print(f"【作成成功】{yr}年度の画像を生成しました: {rel_path}")

    elif mode == "NOTION_SYNC":
        print("【Phase 2】未追加の画像のみNotionへ反映中...")
        companies = get_notion_pages()
        pending_tasks = []

        for comp in companies:
            ticker = comp.get("ticker")
            page_id = comp.get("page_id")
            if not ticker or str(ticker) == "None":
                continue

            existing_years = get_existing_notion_image_years(page_id)
            local_files = glob.glob(f"images/{ticker}_*.png")
            chart_list = []
            
            for file_path in local_files:
                filename = os.path.basename(file_path)
                try:
                    yr = int(filename.split("_")[1].split(".")[0])
                    if yr not in existing_years:
                        rel_path = f"images/{filename}".replace("\\", "/")
                        chart_list.append({"year": yr, "rel_path": rel_path})
                except Exception:
                    continue

            if chart_list:
                chart_list = sorted(chart_list, key=lambda x: x['year'])
                pending_tasks.append({"page_id": page_id, "chart_list": chart_list})

        if pending_tasks:
            sync_pending_images_to_notion(pending_tasks)
        else:
            print("Notionへ同期する新規画像はありません。")
