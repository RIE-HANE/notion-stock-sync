import os
import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

def get_all_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    pages = []
    has_more = True
    next_cursor = None

    while has_more:
        payload = {}
        if next_cursor:
            payload["start_cursor"] = next_cursor
            
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code != 200:
            print(f"Notion API エラー: {res.text}")
            break
            
        data = res.json()
        pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        next_cursor = data.get("next_cursor")

    return pages

def remove_financial_charts_from_page(page_id, page_title):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28"
    }
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return

    blocks = res.json().get("results", [])
    deleted_count = 0

    for i, block in enumerate(blocks):
        b_type = block.get("type")
        block_id = block.get("id")

        # 「▼ ○○年度 財務構造」のテキストの見出し・段落を判定
        is_target_text = False
        if b_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
            txts = block.get(b_type, {}).get("rich_text", [])
            for t in txts:
                if "財務構造" in t.get("plain_text", ""):
                    is_target_text = True
                    break

        # ターゲットテキストまたはその直後の画像ブロックを削除
        if is_target_text or b_type == "image":
            del_url = f"https://api.notion.com/v1/blocks/{block_id}"
            del_res = requests.delete(del_url, headers=headers)
            if del_res.status_code == 200:
                deleted_count += 1

    if deleted_count > 0:
        print(f"【削除完了】{page_title}: {deleted_count}件のブロックを削除しました")

if __name__ == "__main__":
    print("--- Notion上の財務構造画像を自動削除します ---")
    pages = get_all_pages()
    for page in pages:
        props = page.get("properties", {})
        title_arr = props.get("名前", {}).get("title", [])
        title = title_arr[0].get("plain_text", "不明") if title_arr else "不明"
        
        remove_financial_charts_from_page(page["id"], title)
        
    print("--- 削除処理が完了しました ---")
