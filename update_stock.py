import os
import re
from urllib.parse import quote
from bs4 import BeautifulSoup
import requests
import yfinance as yf

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def search_ticker_from_yahoo(company_name):
    """Yahoo!ファイナンスで企業名を検索し、証券コード（4桁文字列）を取得"""
    try:
        encoded_name = quote(company_name)
        url = f"https://finance.yahoo.co.jp/search/?query={encoded_name}"
        search_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        res = requests.get(url, headers=search_headers, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")

        # ページのリンク構造から証券コードを抽出
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            match = re.search(r"/quote/(\d{4})", href)
            if match:
                return match.group(1)
    except Exception as e:
        print(f"  └ 検索エラー ({company_name}): {e}")

    return None


def get_clean_stock_code(page_properties):
    """「証券コード」列または「名前（タイトル）」から4桁の数字を抽出する"""
    # 1. まず「証券コード」列の値を確認
    code_prop = page_properties.get("証券コード", {})
    if code_prop.get("type") == "number" and code_prop.get("number"):
        return str(code_prop.get("number"))

    rich_text = code_prop.get("rich_text", [])
    if rich_text:
        raw_code = rich_text[0].get("plain_text", "")
        match = re.search(r"\d{4}", raw_code)
        if match:
            return match.group(0)

    # 2. 「名前（タイトル）」から4桁数字を検索（例: 【8031】が含まれている場合など）
    title_prop = page_properties.get("名前", {})
    title_text = title_prop.get("title", [])
    if title_text:
        raw_title = title_text[0].get("plain_text", "")
        match = re.search(r"\d{4}", raw_title)
        if match:
            return match.group(0)

    return None


def update_notion_code_and_price(page_id, code, price):
    """Notionの「証券コード」列と「株価」列をまとめて更新"""
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "証券コード": {"rich_text": [{"text": {"content": str(code)}}]},
            "株価": {"number": price},
        }
    }
    requests.patch(url, headers=headers, json=payload)


def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=headers)
    return res.json().get("results", [])


def get_page_blocks(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    res = requests.get(url, headers=headers)
    return res.json().get("results", [])


def append_notebook_template(page_id, code, info):
    # 指標データの整形
    mcap = info.get("marketCap")
    mcap_str = f"{mcap / 100000000:,.1f} 億円" if mcap else "-"
    per = round(info.get("trailingPE"), 2) if info.get("trailingPE") else "-"
    pbr = round(info.get("priceToBook"), 2) if info.get("priceToBook") else "-"

    # 日本版Yahoo!ファイナンスのURL生成
    yahoo_top_url = f"https://finance.yahoo.co.jp/quote/{code}.T"
    yahoo_financial_url = f"https://finance.yahoo.co.jp/quote/{code}.T/financials"

    # Notionブロックの組み立て
    blocks = [
        # --- 企業概要・リンク ---
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "🏢 企業概要"}}]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"証券コード : {code}"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Yahoo!ファイナンス : "}},
                    {
                        "type": "text",
                        "text": {
                            "content": "トップページ",
                            "link": {"url": yahoo_top_url},
                        },
                    },
                    {"type": "text", "text": {"content": " / "}},
                    {
                        "type": "text",
                        "text": {
                            "content": "業績詳細",
                            "link": {"url": yahoo_financial_url},
                        },
                    },
                ]
            },
        },
        {"object": "block", "type": "divider", "divider": {}},
        # --- 業績・指標チェック ---
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "📊 業績・指標チェック"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"時価総額 : {mcap_str}"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": f"PER / PBR : (連){per}倍 / (連){pbr}倍"
                        },
                    }
                ]
            },
        },
        {"object": "block", "type": "divider", "divider": {}},
        # --- 投資メモ・アクション ---
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [
                    {"type": "text", "text": {"content": "🎯 投資メモ・アクション"}}
                ]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": "成長シナリオ（追い風） : "}}
                ]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": "リスク（向かい風） : "}}
                ]
            },
        },
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": "自分のアクション : "}}
                ]
            },
        },
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

        # 1. ページ内・タイトルから4桁コードを探す
        code = get_clean_stock_code(props)

        # 2. なければ企業名でYahoo!ファイナンスから自動検索
        if not code:
            title_prop = props.get("名前", {}).get("title", [])
            if title_prop:
                company_name = title_prop[0].get("plain_text", "").strip()
                print(
                    f"🔍 {company_name} の証券コードをYahoo!ファイナンスから自動検索中..."
                )
                code = search_ticker_from_yahoo(company_name)

        # それでも見つからない場合のみスキップ
        if not code:
            print(f"スキップ: ページID {page_id} の証券コードが見つかりませんでした")
            continue

        print(f"Processing: {code}...")

        try:
            ticker = yf.Ticker(f"{code}.T")
            info = ticker.info

            price = info.get("currentPrice") or info.get("regularMarketPrice")

            # ★証券コード（4桁数字）と株価をNotionへ同時に書き込み・補完
            update_notion_code_and_price(page_id, code, price)

            # ページの既存ブロック（本文）を取得
            existing_blocks = get_page_blocks(page_id)
            print(f"{code} の既存ブロック数: {len(existing_blocks)}")

            if len(existing_blocks) <= 2:
                print("-> テンプレートを挿入します")
                append_notebook_template(page_id, code, info)
                print(f"Notebook template added for {code}")
            else:
                print("-> 本文が存在するためスキップされました")
        except Exception as e:
            print(f"Error processing {code}: {e}")


if __name__ == "__main__":
    main()