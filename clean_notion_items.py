import os
import requests

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")
TARGET_KEYWORD = os.environ.get("TARGET_KEYWORD", "CF比較")

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def get_all_pages():
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


def scan_and_clean_page(page_id, company_name):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        print(f"[{company_name}] ブロック取得失敗: {res.text}")
        return

    blocks = res.json().get("results", [])
    if not blocks:
        return

    print(f"\n▼ 企業ページ: 【{company_name}】 (ブロック数: {len(blocks)})")

    for block in blocks:
        block_id = block["id"]
        block_type = block.get("type")
        title_text = ""

        # 各種ブロックからテキスト抽出
        if block_type == "child_page":
            title_text = block.get("child_page", {}).get("title", "")
        elif block_type == "paragraph":
            rt = block.get("paragraph", {}).get("rich_text", [])
            title_text = "".join([t.get("plain_text", "") for t in rt])
        elif block_type == "link_to_page":
            title_text = f"[ページリンク: {block.get('link_to_page')}]"
        elif block_type == "child_database":
            title_text = (
                f"[DB: {block.get('child_database', {}).get('title', '')}]"
            )
        else:
            title_text = f"[{block_type} ブロック]"

        # ログに出力して実体を確認
        print(f"  ・ Type: {block_type:<15} | 内容: {title_text}")

        # 無条件で関連しそうなものを削除試行
        should_delete = False
        if (
            "CF" in title_text.upper()
            or "比較" in title_text
            or "競合" in title_text
        ):
            should_delete = True

        if should_delete:
            del_url = f"https://api.notion.com/v1/blocks/{block_id}"
            del_res = requests.patch(
                del_url, headers=HEADERS, json={"archived": True}
            )
            if del_res.status_code == 200:
                print(f"    └ ➔ 【削除成功】 {title_text}")
            else:
                print(f"    └ ➔ 【削除失敗】 {del_res.text}")


def main():
    print(
        f"--- Notionページの全ブロック詳細スキャン＆削除を開始します ---"
    )
    pages = get_all_pages()
    print(f"取得できた全企業ページ数: {len(pages)} 件")

    for pid, props in pages:
        name = "不明"
        for k, v in props.items():
            if v.get("type") == "title" and v.get("title"):
                name = v["title"][0].get("plain_text", "不明")
                break

        scan_and_clean_page(pid, name)

    print("\n--- スキャン・削除処理が完了しました ---")


if __name__ == "__main__":
    main()
