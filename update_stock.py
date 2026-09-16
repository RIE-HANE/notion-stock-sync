import os
import requests
import yfinance as yf

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=headers)
    return res.json().get("results", [])

def update_notion_price(page_id, price):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {"properties": {"株価": {"number": price}}}
    requests.patch(url, headers=headers, json=payload)

def get_page_blocks(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=headers)
    return res.json().get("results", [])

def append_notebook_template(page_id, code, info):
    # 指標データの整形
    price = info.get("currentPrice") or info.get("regularMarketPrice") or "-"
    mcap = info.get("marketCap")
    mcap_str = f"{mcap / 100000000:,.1f} 億円" if mcap else "-"
    per = round(info.get("trailingPE"), 2) if info.get("trailingPE") else "-"
    pbr = round(info.get("priceToBook"), 2) if info.get("priceToBook") else "-"
    industry = info.get("industryKey") or info.get("sector") or "-"
    summary = info.get("longBusinessSummary") or "事業内容をここに記入"

    # Notionブロックの組み立て
    blocks = [
        # --- 企業概要 ---
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🏢 企業概要"}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"証券コード : {code}"}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"主な事業内容 : {industry}"}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"概要 : {summary[:100]}..."}}]}
        },
        {"object": "block", "type": "divider", "divider": {}},

        # --- 業績・指標チェック ---
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📊 業績・指標チェック"}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"時価総額 : {mcap_str}"}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"PER / PBR : (連){per}倍 / (連){pbr}倍"}}]}
        },
        {"object": "block", "type": "divider", "divider": {}},

        # --- 投資メモ・アクション ---
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🎯 投資メモ・アクション"}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "成長シナリオ（追い風） : "}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "リスク（向かい風） : "}}]}
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": "自分のアクション : "}}]}
        }
    ]

    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    requests.patch(url, headers=headers, json={"children": blocks})

def main():
    print("=== スクリプト処理を開始します ===")
    pages = get_notion_pages()
    print(f"取得したページ数: {len(pages)}")
    
    for page in pages:
        page_id = page["id"]
        props = page["properties"]
        
        # 証券コードの取得（数値型・テキスト型どちらにも対応）
        code_prop = props.get("証券コード", {})
        code = None

        if code_prop.get("type") == "number":
            code = code_prop.get("number")
        elif code_prop.get("type") == "rich_text":
            rich_texts = code_prop.get("rich_text", [])
            if rich_texts:
                code = rich_texts[0].get("plain_text")

        if not code:
            print(f"スキップ: ページID {page_id} は証券コードが空です")
            continue
            
        code = str(code).strip()
        print(f"Processing: {code}...")
        
        try:
            ticker = yf.Ticker(f"{code}.T")
            info = ticker.info
            
            # DBの株価プロパティを更新
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price:
                update_notion_price(page_id, price)
            
            # ページの既存ブロック（本文）を取得
            existing_blocks = get_page_blocks(page_id)
            print(f"{code} の既存ブロック数: {len(existing_blocks)}")

            if len(existing_blocks) <= 2:
                print(f"-> テンプレートを挿入します")
                append_notebook_template(page_id, code, info)
                print(f"Notebook template added for {code}")
            else:
                print(f"-> 本文が存在するためスキップされました")    
        except Exception as e:
            print(f"Error processing {code}: {e}")

if __name__ == "__main__":
    main()