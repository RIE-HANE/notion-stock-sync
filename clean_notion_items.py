import os
import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# 削除対象のキーワード（環境変数 TARGET_KEYWORD から取得。デフォルトは 'CF比較'）
TARGET_KEYWORD = os.environ.get("TARGET_KEYWORD", "CF比較")

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
            pages.append((p["id"], p.get("properties", {})))

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return pages


def clean_page_subpages(page_id, company_name):
    """指定したキーワードを含むサブページ/ブロックを削除 (アーカイブ)"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return

    blocks = res.json().get("results", [])
    deleted_count = 0

    for block in blocks:
        block_id = block["id"]
        block_type = block.get("type")
        should_delete = False

        # 1. サブページ (child_page) の判定
        if block_type == "child_page":
            title = block.get("child_page", {}).get("title", "")
            if TARGET_KEYWORD == "ALL_SUBPAGES" or TARGET_KEYWORD in title:
                should_delete = True

        # 2. 直貼りテキスト (paragraph) の判定
        elif block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            text_content = "".join([t.get("plain_text", "") for t in rich_text])
            if TARGET_KEYWORD in text_content:
                should_delete = True

        # 削除実行 (archived: True)
        if should_delete:
            del_url = f"https://api.notion.com/v1/blocks/{block_id}"
            del_res = requests.patch(
                del_url, headers=HEADERS, json={"archived": True}
            )
            if del_res.status_code == 200:
                deleted_count += 1

    if deleted_count > 0:
        print(
            f"【削除完了】{company_name}: {deleted_count}件の対象（サブページ含む）を削除しました"
        )


def main():
    print(
        f"--- Notion上の「{TARGET_KEYWORD}」関連サブページ/ブロックを削除します ---"
    )
    pages = get_all_pages()

    for pid, props in pages:
        # 企業名取得
        name = "不明"
        for k, v in props.items():
            if v.get("type") == "title" and v.get("title"):
                name = v["title"][0].get("plain_text", "不明")
                break

        clean_page_subpages(pid, name)

    print("--- 削除処理が完了しました ---")


if __name__ == "__main__":
    main()
