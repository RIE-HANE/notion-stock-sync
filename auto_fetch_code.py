import re
import urllib.parse
from notion_client import Client
import requests
from bs4 import BeautifulSoup

# 1. アクセストークンとデータベースID
NOTION_TOKEN = "ntn_nX464811020bEJSuYhIeUadAjlQmTXDNm6ZqjK20riQ1Hf"
DATABASE_ID = "3d801bb4740c8025b1a8efc2cf1d1595"

notion = Client(auth=NOTION_TOKEN)


def fetch_ticker_from_wikipedia(company_name):
    """Wikipediaの企業ページから4桁の証券コードを自動スクレイピング"""
    # 全角英数を半角に変換などの簡易クレンジング
    clean_name = company_name.strip()
    encoded_name = urllib.parse.quote(clean_name)
    url = f"https://ja.wikipedia.org/wiki/{encoded_name}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # 右側の基本情報テーブル（infobox）を取得
        infobox = soup.find("table", class_="infobox")
        if not infobox:
            return None

        # テキストの中から「東証... 4桁の数字」のパターンを探す
        text = infobox.get_text()
        match = re.search(r"(?:東証|名証|札証|福岡|PRM|STD|GRT)\s*[:：]?\s*(\d{4})", text)
        if match:
            return match.group(1)

        # パターンで見つからない場合、数字4桁単体を探索
        match_fallback = re.search(r"\b(\d{4})\b", text)
        if match_fallback:
            return match_fallback.group(1)

    except Exception as e:
        print(f"  └ Wikipedia取得エラー ({company_name}): {e}")

    return None


def update_notion_ticker_codes():
    print("🚀 Wikipediaから証券コードの自動取得を開始します...\n")

    response = notion.search(filter={"value": "page", "property": "object"})
    results = response.get("results", [])

    db_pages = [
        page
        for page in results
        if page.get("parent", {}).get("database_id", "").replace("-", "")
        == DATABASE_ID
    ]

    for page in db_pages:
        page_id = page["id"]
        properties = page.get("properties", {})
        title_prop = properties.get("名前", {}).get("title", [])

        if not title_prop:
            continue

        company_name = title_prop[0].get("text", {}).get("content", "").strip()

        # Wikipediaから証券コードを自動検索
        code = fetch_ticker_from_wikipedia(company_name)

        if code:
            # Notionの「証券コード」プロパティを更新
            notion.pages.update(
                page_id=page_id, properties={"証券コード": {"rich_text": [{"text": {"content": code}}]}}
            )
            print(f"✅ {company_name}: 証券コード「{code}」を取得して更新しました")
        else:
            print(f"ℹ️ {company_name}: Wikipediaから証券コードが見つかりませんでした")

    print("\n🎉 証券コードの自動更新が完了しました！")


if __name__ == "__main__":
    update_notion_ticker_codes()