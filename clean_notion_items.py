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
    """データベース内のすべての企業ページIDを漏れなく全件取得 (100件制限の回避)"""
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
    """全角・半角・大小文字を考慮して削除対象かどうか判定"""
    if not text:
        return False
    if TARGET_KEYWORD == "ALL_SUBPAGES":
        return True

    # 検索用表記ゆれ変換（全角→半角、小文字化）
    normalized_text = (
        text.replace("ＣＦ", "CF").replace("ｃｆ", "cf").lower()
    )
    normalized_target = TARGET_KEYWORD.replace("ＣＦ", "CF").lower()

    return (
        normalized_target in normalized_text or "競合比較" in normalized_text
    )


def clean_page_subpages(page_id, company_name):
    """指定したキーワードを含むサブページ/直貼りブロックを削除 (アーカイブ)"""
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

        # 1. サブページ (child_page) の判定
        if block_type == "child_page":
            title = block.get("child_page", {}).get("title", "")
            if is_target_title(title):
                should_delete = True

        # 2. 直貼りテキスト (paragraph) の判定
        elif block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            text_content = "".join([t.get("plain_text", "") for t in rich_text])
            if is_target_title(text_content):
                should_delete = True

        # 削除実行 (archived: True に更新)
        if should_delete:
            del_url = f"https://api.notion.com/v1/blocks/{block_id}"
            del_res = requests.patch(
                del_url, headers=HEADERS, json={"archived": True}
            )
            if del_res.status_code == 200:
                deleted_count += 1

    if deleted_count > 0:
        print(
            f"【削除完了】{company_name}: {deleted_count}件の対象を削除しました"
        )


def main():
    print(
        f"--- Notion上の「{TARGET_KEYWORD}」関連サブページ/ブロックを全件スキャンして削除します ---"
    )
    pages = get_all_pages()
    print(f"取得できた全企業ページ数: {len(pages)} 件")

    for pid, props in pages:
        name = "不明"
        for k, v in props.items():
            if v.get("type") == "title" and v.get("title"):
                name = v["title"][0].get("plain_text", "不明")
                break

        clean_page_subpages(pid, name)

    print("--- 削除処理が完了しました ---")


if __name__ == "__main__":
    main()
