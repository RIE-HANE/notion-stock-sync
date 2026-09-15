from notion_client import Client

# 1. 取得した内部統合トークン（アクセストークン）
NOTION_TOKEN = "ntn_nX464811020bEJSuYhIeUadAjlQmTXDNm6ZqjK20riQ1Hf"

# 2. 企業リストのデータベースID
DATABASE_ID = "3d801bb4740c8025b1a8efc2cf1d1595"

# Notionクライアントの初期化
notion = Client(auth=NOTION_TOKEN)


def test_connection():
    try:
        # Notion全体から該当データベース配下のページを検索取得
        response = notion.search(
            filter={"value": "page", "property": "object"}
        )
        results = response.get("results", [])

        # 該当のデータベースに所属するページだけを抽出
        db_pages = [
            page
            for page in results
            if page.get("parent", {}).get("database_id", "").replace("-", "")
            == DATABASE_ID
        ]

        print(
            f"✅ 接続成功！「企業リスト」から {len(db_pages)} 件のデータを取り出せました。\n"
        )

        # 各行から「名前（企業名）」を取得して表示
        for page in db_pages:
            properties = page.get("properties", {})
            title_property = properties.get("名前", {}).get("title", [])
            if title_property:
                company_name = title_property[0].get("text", {}).get("content")
                print(f"・{company_name}")

    except Exception as e:
        print(f"❌ エラーが発生しました:\n{e}")


if __name__ == "__main__":
    test_connection()