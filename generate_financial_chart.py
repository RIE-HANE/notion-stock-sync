import os
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import japanize_matplotlib

# 環境変数
EDINET_API_KEY = os.environ.get("EDINET_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

def get_notion_pages():
    """Notionから登録企業一覧を取得"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    res = requests.post(url, headers=headers)
    pages = []
    if res.status_code == 200:
        for page in res.json().get("results", []):
            props = page.get("properties", {})
            # 企業名と証券コードを取得
            title_list = props.get("銘柄名", {}).get("title", [])
            name = title_list[0]["plain_text"] if title_list else "不明"
            
            code_list = props.get("証券コード", {}).get("rich_text", [])
            ticker = code_list[0]["plain_text"] if code_list else None
            
            pages.append({"page_id": page["id"], "name": name, "ticker": ticker})
    return pages

def create_financial_chart(company_name, financial_data, output_path="chart.png"):
    """BS/PL図解画像を生成"""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    total_assets = financial_data.get("total_assets", 100)
    ca_h = (financial_data.get("current_assets", 40) / total_assets) * 100
    fa_h = (financial_data.get("fixed_assets", 60) / total_assets) * 100
    cl_h = (financial_data.get("current_liab", 30) / total_assets) * 100
    fl_h = (financial_data.get("fixed_liab", 20) / total_assets) * 100
    eq_h = (financial_data.get("equity", 50) / total_assets) * 100

    sales_h = (financial_data.get("sales", 80) / total_assets) * 100
    op_h = (financial_data.get("op_profit", 10) / total_assets) * 100

    # 貸借対照表 (BS)
    ax.add_patch(patches.Rectangle((5, 100 - ca_h), 30, ca_h, facecolor='#87ceeb', edgecolor='black', label='流動資産'))
    ax.add_patch(patches.Rectangle((5, 0), 30, fa_h, facecolor='#4682b4', edgecolor='black', label='固定資産'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h), 30, cl_h, facecolor='#f08080', edgecolor='black', label='流動負債'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h - fl_h), 30, fl_h, facecolor='#cd5c5c', edgecolor='black', label='固定負債'))
    ax.add_patch(patches.Rectangle((35, 0), 30, eq_h, facecolor='#90ee90', edgecolor='black', label='純資産'))

    # 損益計算書 (PL)
    ax.add_patch(patches.Rectangle((75, 0), 20, sales_h, facecolor='#ffcccb', edgecolor='black', label='売上高'))
    ax.add_patch(patches.Rectangle((75, 0), 20, op_h, facecolor='#ff4500', edgecolor='black', label='営業利益'))

    ax.set_xlim(0, 100)
    ax.set_ylim(-10, 110)
    plt.axis('off')
    plt.title(f"{company_name} 財務構造分析図 (BS / PL)", fontsize=16)
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close()

if __name__ == "__main__":
    print("Notionから企業一覧を読み込んでいます...")
    companies = get_notion_pages()
    print(f"対象企業数: {len(companies)} 件")
    
    for comp in companies:
        print(f"処理中: {comp['name']} (コード: {comp['ticker']})")
        # デモ用サンプル構造
        sample_bs_pl = {
            "total_assets": 1000,
            "current_assets": 450,
            "fixed_assets": 550,
            "current_liab": 250,
            "fixed_liab": 200,
            "equity": 550,
            "sales": 900,
            "op_profit": 120
        }
        create_financial_chart(comp["name"], sample_bs_pl)
    
    print("全企業の財務図解生成テストが完了しました。")
