import re
from urllib.parse import quote
from bs4 import BeautifulSoup
from notion_client import Client
import requests

NOTION_TOKEN = "ntn_nX464811020bEJSuYhIeUadAjlQmTXDNm6ZqjK20riQ1Hf"
DATABASE_ID = "3d801bb4740c8025b1a8efc2cf1d1595"

notion = Client(auth=NOTION_TOKEN)


def search_ticker_from_yahoo(company_name):
    """Yahoo!ファイナンスで企業名を検索し、証券コード（文字列）を取得"""
    try:
        encoded_name = quote(company_name)
        url = f"https://finance.yahoo.co.jp/search/?query={encoded_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")

        # ページのリンク構造から証券コードを抽出
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            match = re.search(r"/quote/(\d{4})", href)
            if match:
                return match.group(1)  # 文字列として返す

    except Exception as e:
        print(f"  └ 検索エラー ({company_name}): {e}")

    return None


def auto_fill_notion_tickers():
    print("🚀 Yahoo!ファイナンスからの証券コード自動検索を開始します...\n")

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

        # 企業名の取得
        title_prop = properties.get("名前", {}).get("title", [])
        if not title_prop:
            continue
        company_name = title_prop[0].get("text", {}).get("content", "").strip()

        # すでに証券コードが入っている場合はスキップ（rich_text対応）
        code_prop = properties.get("証券コード", {}).get("rich_text", [])
        if code_prop:
            existing_code = code_prop[0].get("text", {}).get("content", "")
            print(
                f"⏭️ {company_name}: 既に証券コード ({existing_code}) が設定されています"
            )
            continue

        # Yahoo!ファイナンスで自動検索
        code = search_ticker_from_yahoo(company_name)

        if code:
            # Notionのテキスト（rich_text）プロパティへ書き込み
            notion.pages.update(
                page_id=page_id,
                properties={
                    "証券コード": {
                        "rich_text": [{"text": {"content": str(code)}}]
                    }
                },
            )
            print(
                f"✅ {company_name} -> 証券コード: {code} を自動取得・入力しました"
            )
        else:
            print(
                f"ℹ️ {company_name}: コードが見つかりませんでした（未上場など）"
            )

    print("\n🎉 処理が完了しました！")


if __name__ == "__main__":
    auto_fill_notion_tickers()