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


def clean_subpages(page_id):
    """指定キーワードを含むサブページのみアーカイブ（削除）"""
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return

    blocks = res.json().get("results", [])

    for block in blocks:
        block_id = block["id"]
        block_type = block.get("type")

        # サブページ（child_page）の判定
        if block_type == "child_page":
            title = block.get("child_page", {}).get("title", "")

            # キーワード判定
            match = False
            if TARGET_KEYWORD == "ALL_SUBPAGES":
                match = True
            elif TARGET_KEYWORD in title:
                match = True

            if match:
                del_url = f"https://api.notion.com/v1/blocks/{block_id}"
                del_res = requests.patch(
                    del_url, headers=HEADERS, json={"archived": True}
                )
                if del_res.status_code == 200:
                    print(f" └ [削除完了] サブページ: 「{title}」")
                else:
                    print(
                        f" ⚠ [削除失敗] サブページ: 「{title}」 ({del_res.text})"
                    )


def main():
    print(
        f"=== Notion サブページ削除処理開始 (指定キーワード: '{TARGET_KEYWORD}') ==="
    )
    pages = get_all_pages()
    print(f"対象企業ページ数: {len(pages)} 件")

    for pid in pages:
        clean_subpages(pid)

    print("=== 削除処理完了 ===")


if __name__ == "__main__":
    main()
