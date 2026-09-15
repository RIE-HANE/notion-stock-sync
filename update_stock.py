from notion_client import Client
import yfinance as yf

# 1. アクセストークンとデータベースID
NOTION_TOKEN = "ntn_nX464811020bEJSuYhIeUadAjlQmTXDNm6ZqjK20riQ1Hf"
DATABASE_ID = "3d801bb4740c8025b1a8efc2cf1d1595"

notion = Client(auth=NOTION_TOKEN)


def get_stock_price(code_str):
    """証券コード（文字列）からYahoo Financeの株価を取得"""
    try:
        # 日本株のTickerシンボル（例: "6702.T"）を作成
        ticker_symbol = f"{code_str.strip()}.T"
        ticker = yf.Ticker(ticker_symbol)
        todays_data = ticker.history(period="1d")

        if not todays_data.empty:
            price = round(todays_data["Close"].iloc[-1], 2)
            return price
    except Exception as e:
        print(f"  └ 株価取得失敗 ({code_str}): {e}")
    return None


def update_notion_stocks():
    print(
        "🚀 Notionの「証券コード」を元に、最新株価の自動更新処理を開始します...\n"
    )

    # Notionから企業リストを取得
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

        # 1. 企業名の取得
        title_prop = properties.get("名前", {}).get("title", [])
        if not title_prop:
            continue
        company_name = title_prop[0].get("text", {}).get("content", "").strip()

        # 2. Notionから「証券コード」プロパティの文字列を取得
        code_prop = properties.get("証券コード", {}).get("rich_text", [])
        if not code_prop:
            print(
                f"ℹ️ {company_name}: 証券コードが未登録のためスキップします"
            )
            continue

        ticker_code = code_prop[0].get("text", {}).get("content", "").strip()

        if not ticker_code:
            print(
                f"ℹ️ {company_name}: 証券コードが空欄のためスキップします"
            )
            continue

        # 3. 株価を取得してNotionの「株価」プロパティを更新
        price = get_stock_price(ticker_code)

        if price is not None:
            notion.pages.update(
                page_id=page_id, properties={"株価": {"number": price}}
            )
            print(
                f"✅ {company_name} (コード: {ticker_code}) -> 株価: {price} 円 に更新しました"
            )
        else:
            print(
                f"⚠️ {company_name} (コード: {ticker_code}): 株価データの取得に失敗しました"
            )

    print("\n🎉 すべての更新処理が完了しました！")


if __name__ == "__main__":
    update_notion_stocks()