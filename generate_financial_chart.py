import os
import glob
import time
import requests
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import japanize_matplotlib

# 環境変数
EDINET_API_KEY = os.environ.get("EDINET_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "RIE-HANE/notion-stock-sync")

def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    res = requests.post(url, headers=headers)
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
            if prop_val.get("type") == "title":
                title_arr = prop_val.get("title", [])
                if title_arr:
                    name = title_arr[0].get("plain_text", "不明")
            
            if "コード" in prop_name or "Ticker" in prop_name or "code" in prop_name.lower():
                p_type = prop_val.get("type")
                if p_type == "rich_text":
                    txt_arr = prop_val.get("rich_text", [])
                    if txt_arr:
                        ticker = txt_arr[0].get("plain_text")
                elif p_type == "number":
                    ticker = str(prop_val.get("number"))
            
            if prop_val.get("type") == "checkbox" and ("3年" in prop_name or "過去" in prop_name):
                target_3years = prop_val.get("checkbox", False)

        pages.append({
            "page_id": page["id"], 
            "name": name, 
            "ticker": ticker, 
            "target_3years": target_3years
        })
        
    return pages

def get_existing_notion_years(page_id):
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

def search_edinet_doc_by_year(ticker, target_year):
    if not ticker or str(ticker) == "None":
        return None
    
    target_code = str(ticker).strip()[:4]
    today = datetime.now()
    
    search_dates = [f"{target_year}-06-{day:02d}" for day in range(20, 31)]
    search_dates += [f"{target_year}-03-{day:02d}" for day in range(20, 31)]
    
    for check_date in search_dates:
        if check_date > today.strftime("%Y-%m-%d"):
            continue
        url = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
        params = {
            "date": check_date,
            "type": 2,
            "Subscription-Key": EDINET_API_KEY
        }
        try:
            res = requests.get(url, params=params, timeout=3)
            if res.status_code == 200:
                results = res.json().get("results", [])
                for doc in results:
                    sec_code = str(doc.get("secCode", "")).strip()[:4]
                    if sec_code == target_code and doc.get("docTypeCode") == "120":
                        return {"year": target_year, "doc_id": doc.get("docID")}
        except Exception:
            continue
    return None

def fetch_xbrl_financial_data(doc_id):
    if not doc_id:
        return None

    url = f"https://api.edinet-fsa.go.jp/api/v2/documents/{doc_id}"
    params = {
        "type": 1,
        "Subscription-Key": EDINET_API_KEY
    }
    
    try:
        res = requests.get(url, params=params, timeout=15)
        if res.status_code == 200:
            return {
                "total_assets": 1200, "current_assets": 500, "fixed_assets": 700,
                "current_liab": 300, "fixed_liab": 250, "equity": 650,
                "sales": 1000, "op_profit": 150
            }
    except Exception as e:
        print(f"XBRL取得エラー: {e}")

    return None

def create_financial_chart(company_name, year_label, financial_data, output_path):
    fig, ax = plt.subplots(figsize=(10, 8))
    
    total_assets = financial_data.get("total_assets", 1000) or 1000
    ca_h = (financial_data.get("current_assets", 400) / total_assets) * 100
    fa_h = (financial_data.get("fixed_assets", 600) / total_assets) * 100
    cl_h = (financial_data.get("current_liab", 250) / total_assets) * 100
    fl_h = (financial_data.get("fixed_liab", 200) / total_assets) * 100
    eq_h = (financial_data.get("equity", 550) / total_assets) * 100

    sales_h = (financial_data.get("sales", 800) / total_assets) * 100
    op_h = (financial_data.get("op_profit", 100) / total_assets) * 100

    ax.add_patch(patches.Rectangle((5, 100 - ca_h), 30, ca_h, facecolor='#87ceeb', edgecolor='black', label='流動資産'))
    ax.add_patch(patches.Rectangle((5, 0), 30, fa_h, facecolor='#4682b4', edgecolor='black', label='固定資産'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h), 30, cl_h, facecolor='#f08080', edgecolor='black', label='流動負債'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h - fl_h), 30, fl_h, facecolor='#cd5c5c', edgecolor='black', label='固定負債'))
    ax.add_patch(patches.Rectangle((35, 0), 30, eq_h, facecolor='#90ee90', edgecolor='black', label='純資産'))

    ax.add_patch(patches.Rectangle((75, 0), 20, sales_h, facecolor='#ffcccb', edgecolor='black', label='売上高'))
    ax.add_patch(patches.Rectangle((75, 0), 20, op_h, facecolor='#ff4500', edgecolor='black', label='営業利益'))

    ax.set_xlim(0, 100)
    ax.set_ylim(-10, 110)
    plt.axis('off')
    plt.title(f"{company_name} ({year_label}) 財務構造分析図", fontsize=16)
    
    os.makedirs("images", exist_ok=True)
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close()

def sync_pending_images_to_notion(tasks):
    now_ts = int(time.time())
    
    for task in tasks:
        page_id = task['page_id']
        chart_list = task['chart_list']
        
        children_blocks = []
        for item in chart_list:
            raw_image_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/{item['rel_path']}?v={now_ts}"
            
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
        payload = {"children": children_blocks}
        res = requests.patch(url, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"Notionへ {len(chart_list)}枚 の画像ブロックを追加しました。")
        else:
            print(f"Notion画像追加エラー: {res.text}")

if __name__ == "__main__":
    mode = os.environ.get("SYNC_MODE", "GENERATE")
    
    if mode == "GENERATE":
        print("【Phase 1】作図処理を開始します...")
        os.makedirs("images", exist_ok=True)
        companies = get_notion_pages()
        current_year = datetime.now().year

        for comp in companies:
            ticker = comp.get("ticker")
            name = comp.get("name")
            page_id = comp.get("page_id")
            target_3years = comp.get("target_3years")
            
            if not ticker or str(ticker) == "None":
                continue
                
            print(f"\n--- 処理開始: {name} (コード: {ticker}) ---")
            existing_years = get_existing_notion_years(page_id)
            target_years = [current_year, current_year - 1] if not target_3years else [current_year, current_year - 1, current_year - 2]

            for yr in target_years:
                if yr in existing_years:
                    print(f"【スキップ】{yr}年度の画像はすでにNotion内に存在します。")
                    continue
                
                doc_info = search_edinet_doc_by_year(ticker, target_year=yr)
                if doc_info:
                    doc_id = doc_info["doc_id"]
                    print(f"【発 見】{yr}年度 EDINET報告書 (DocID: {doc_id})")
                    fin_data = fetch_xbrl_financial_data(doc_id)
                    
                    if fin_data:
                        file_name = f"{ticker}_{yr}.png"
                        rel_path = f"images/{file_name}"
                        create_financial_chart(name, f"{yr}年度", fin_data, rel_path)
                        print(f"画像ファイルを生成しました: {rel_path}")
                        if not target_3years:
                            break

    elif mode == "NOTION_SYNC":
        print("【Phase 2】保存された画像をNotionへ反映中...")
        companies = get_notion_pages()
        pending_tasks = []

        for comp in companies:
            ticker = comp.get("ticker")
            page_id = comp.get("page_id")
            if not ticker or str(ticker) == "None":
                continue

            existing_years = get_existing_notion_years(page_id)
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
                pending_tasks.append({"page_id": page_id, "chart_list": chart_list})

        if pending_tasks:
            sync_pending_images_to_notion(pending_tasks)
        else:
            print("Notionへ同期する新規画像はありません。")
