import os
import io
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import japanize_matplotlib
from bs4 import BeautifulSoup

# 環境変数
EDINET_API_KEY = os.environ.get("EDINET_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

def get_notion_pages():
    """Notionデータベースから企業一覧とページID、証券コードを取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    res = requests.post(url, headers=headers)
    pages = []
    if res.status_code == 200:
        data = res.json()
        for page in data.get("results", []):
            props = page.get("properties", {})
            # 「証券コード」プロパティを取得
            code_item = props.get("証券コード", {}).get("rich_text", [])
            ticker = code_item[0]["plain_text"] if code_item else None
            pages.append({"page_id": page["id"], "ticker": ticker})
    return pages

def draw_bs_pl_chart(company_name, financial_data, output_path="chart.png"):
    """財務数値をもとに比例縮尺ブロック図を生成"""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    total_assets = financial_data.get("total_assets", 100) or 100
    ca_h = (financial_data.get("current_assets", 40) / total_assets) * 100
    fa_h = (financial_data.get("fixed_assets", 60) / total_assets) * 100
    cl_h = (financial_data.get("current_liab", 30) / total_assets) * 100
    fl_h = (financial_data.get("fixed_liab", 20) / total_assets) * 100
    eq_h = (financial_data.get("equity", 50) / total_assets) * 100

    sales_h = (financial_data.get("sales", 80) / total_assets) * 100
    op_h = (financial_data.get("op_profit", 10) / total_assets) * 100

    # BS
    ax.add_patch(patches.Rectangle((5, 100 - ca_h), 30, ca_h, facecolor='#87ceeb', edgecolor='black'))
    ax.add_patch(patches.Rectangle((5, 0), 30, fa_h, facecolor='#4682b4', edgecolor='black'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h), 30, cl_h, facecolor='#f08080', edgecolor='black'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h - fl_h), 30, fl_h, facecolor='#cd5c5c', edgecolor='black'))
    ax.add_patch(patches.Rectangle((35, 0), 30, eq_h, facecolor='#90ee90', edgecolor='black'))

    # PL
    ax.add_patch(patches.Rectangle((75, 0), 20, sales_h, facecolor='#ffcccb', edgecolor='black'))
    ax.add_patch(patches.Rectangle((75, 0), 20, op_h, facecolor='#ff4500', edgecolor='black'))

    ax.set_xlim(0, 100)
    ax.set_ylim(-10, 110)
    plt.axis('off')
    plt.title(f"{company_name} 財務図解 (BS/PL)", fontsize=16)
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close()

if __name__ == "__main__":
    print("Notionから企業データを取得中...")
    pages = get_notion_pages()
    print(f"{len(pages)} 件のデータを処理します。")
    
    # 描画テスト
    sample_data = {
        "total_assets": 1000,
        "current_assets": 400,
        "fixed_assets": 600,
        "current_liab": 300,
        "fixed_liab": 200,
        "equity": 500,
        "sales": 800,
        "op_profit": 100
    }
    draw_bs_pl_chart("テスト企業", sample_data)
    print("処理が安全に完了しました。")
