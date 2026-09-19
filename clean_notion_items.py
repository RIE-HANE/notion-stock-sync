import os
import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# 削除対象キーワード
TARGET_KEYWORD = os.environ.get("TARGET_KEYWORD", "CF比較")

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def get_all_pages():
    """データベース内のすべての企業ページIDを漏れなく取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    pages = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {"page_size": 100}
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


def is_target_title(text):
    """判定ロジック（全角半角・大文字小文字対応）"""
    if not text:
        return False
    if TARGET_KEYWORD == "ALL_SUBPAGES":
        return True

    normalized_text = (
        text.replace("ＣＦ", "CF").replace("ｃｆ", "cf").lower()
    )
    normalized_target = TARGET_KEYWORD.replace("ＣＦ", "CF").lower()

    return (
        normalized_target in normalized_text or "競合比較" in normalized_text
    )


def delete_item(item_id, is_child_page=False):
    """サブページか通常のブロックかで呼び出すAPIエンドポイントを切替"""
    if is_child_page:
        # サブページの場合は /v1/pages エンドポイントを使用
        url = f"https://api.notion.com/v1/pages/{item_id}"
    else:
        # 通常ブロックの場合は /v1/blocks エンドポイントを使用
        url = f"https://api.notion.com/v1/blocks/{item_id}"

    res = requests.patch(url, headers=HEADERS, json={"archived": True})
    return res.status_code == 200


def clean_page_items(page_id, company_name):
    """ページ内のブロックを走査して対象アイテムをアーカイブ"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return

    blocks = res.json().get("results", [])
    deleted_count = 0

    for block in blocks:
        block_id = block["id"]
        block_type = block.get("type")
        should_delete = False
        is_subpage = False

        # 1. サブページ (child_page)
        if block_type == "child_page":
            title = block.get("child_page", {}).get("title", "")
            if is_target_title(title):
                should_delete = True
                is_subpage = True

        # 2. 直貼りテキスト (paragraph)
        elif block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            text_content = "".join([t.get("plain_text", "") for t in rich_text])
            if is_target_title(text_content):
                should_delete = True

        # 削除処理の実行
        if should_delete:
            if delete_item(block_id, is_child_page=is_subpage):
                deleted_count += 1

    if deleted_count > 0:
        print(
            f"【削除成功】{company_name}: {deleted_count}件のサブページ/ブロックを削除しました"
        )


def main():
    print(
        f"--- Notion上の「{TARGET_KEYWORD}」関連サブページ/ブロックを削除します ---"
    )
    pages = get_all_pages()
    print(f"対象企業数: {len(pages)} 件")

    for pid, props in pages:
        name = "不明"
        for k, v in props.items():
            if v.get("type") == "title" and v.get("title"):
                name = v["title"][0].get("plain_text", "不明")
                break

        clean_page_items(pid, name)

    print("--- 削除処理が完了しました ---")


if __name__ == "__main__":
    main()
