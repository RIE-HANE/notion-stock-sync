import os
import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
TARGET_TYPE = os.environ.get("TARGET_TYPE", "SUBPAGES_ONLY")

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def get_all_pages():
    """データベース内のすべての企業ページIDを取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    pages = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        
        res = requests.post(url, headers=HEADERS, json=payload)
        if res.status_code != 200:
            print(f"DB取得エラー: {res.text}")
            break
        
        data = res.json()
        for p in data.get("results", []):
            pages.append(p["id"])
            
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")
        
    return pages

def clean_page_contents(page_id):
    """各ページ内の指定されたブロック／サブページを削除 (アーカイブ)"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return

    blocks = res.json().get("results", [])
    
    for block in blocks:
        block_id = block["id"]
        block_type = block.get("type")
        should_delete = False

        # --- A. サブページの判定 ---
        if block_type == "child_page":
            title = block.get("child_page", {}).get("title", "")
            if "CF比較" in title or "📊" in title:
                if TARGET_TYPE in ["SUBPAGES_ONLY", "ALL"]:
                    should_delete = True
                    print(f" └ [サブページ削除] {title}")

        # --- B. 直貼りテキスト・画像の判定 ---
        elif block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            text_content = "".join([t.get("plain_text", "") for t in rich_text])
            if "競合比較" in text_content or "キャッシュフロー" in text_content:
                if TARGET_TYPE in ["DIRECT_BLOCKS_ONLY", "ALL"]:
                    should_delete = True
                    print(f" └ [直貼りテキスト削除] {text_content}")

        elif block_type == "image":
            if TARGET_TYPE in ["DIRECT_BLOCKS_ONLY", "ALL"]:
                # 直貼り画像ブロックを削除
                should_delete = True
                print(" └ [直貼り画像削除]")

        # 削除実行 (Notion APIでは archived: True に更新)
        if should_delete:
            del_url = f"https://api.notion.com/v1/blocks/{block_id}"
            requests.patch(del_url, headers=HEADERS, json={"archived": True})

def main():
    print(f"=== Notion クリーンアップ開始 (対象モード: {TARGET_TYPE}) ===")
    pages = get_all_pages()
    print(f"対象ページ数: {len(pages)} 件")

    for pid in pages:
        clean_page_contents(pid)

    print("=== クリーンアップ完了 ===")

if __name__ == "__main__":
    main()
