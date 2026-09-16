import os
import requests
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# 環境変数の読み込み
EDINET_API_KEY = os.environ.get("EDINET_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

def create_bs_pl_chart(bs_pl_data, output_path="financial_chart.png"):
    """
    財務数値(BS/PL)から比例縮尺のブロック図を描画して画像として保存する
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # 総資産の値を基準（100%）として各ブロックの高さを計算
    total_assets = bs_pl_data.get("total_assets", 1)
    if total_assets <= 0:
        total_assets = 1

    # 各項目の高さ計算 (0~100)
    ca_h = (bs_pl_data.get("current_assets", 0) / total_assets) * 100 # 流動資産
    fa_h = (bs_pl_data.get("fixed_assets", 0) / total_assets) * 100    # 固定資産
    cl_h = (bs_pl_data.get("current_liab", 0) / total_assets) * 100   # 流動負債
    fl_h = (bs_pl_data.get("fixed_liab", 0) / total_assets) * 100   # 固定負債
    eq_h = (bs_pl_data.get("equity", 0) / total_assets) * 100       # 純資産

    # PL項目
    sales_h = (bs_pl_data.get("sales", 0) / total_assets) * 100      # 売上高
    op_h = (bs_pl_data.get("op_profit", 0) / total_assets) * 100     # 営業利益

    # --- 左側：貸借対照表 (BS) 描画 ---
    # 資産の部 (x: 5~35)
    ax.add_patch(patches.Rectangle((5, 100 - ca_h), 30, ca_h, facecolor='#add8e6', edgecolor='black', label='流動資産'))
    ax.add_patch(patches.Rectangle((5, 0), 30, fa_h, facecolor='#6897bb', edgecolor='black', label='固定資産'))
    
    # 負債・純資産の部 (x: 35~65)
    ax.add_patch(patches.Rectangle((35, 100 - cl_h), 30, cl_h, facecolor='#f08080', edgecolor='black', label='流動負債'))
    ax.add_patch(patches.Rectangle((35, 100 - cl_h - fl_h), 30, fl_h, facecolor='#cd5c5c', edgecolor='black', label='固定負債'))
    ax.add_patch(patches.Rectangle((35, 0), 30, eq_h, facecolor='#90ee90', edgecolor='black', label='純資産'))

    # --- 右側：損益計算書 (PL) 描画 ---
    # 売上高・営業利益 (x: 75~95)
    ax.add_patch(patches.Rectangle((75, 0), 20, sales_h, facecolor='#ffcccb', edgecolor='black', label='売上高'))
    ax.add_patch(patches.Rectangle((75, 0), 20, op_h, facecolor='#ff4500', edgecolor='black', label='営業利益'))

    # レイアウトと見栄えの調整
    ax.set_xlim(0, 100)
    ax.set_ylim(-10, 110)
    plt.axis('off')
    plt.title(f"{bs_pl_data.get('company_name', '企業')} 財務分析図解 (BS / PL)", fontsize=16)

    # 画像として保存
    plt.savefig(output_path, bbox_inches='tight', dpi=200)
    plt.close()
    print(f"財務図解画像を生成しました: {output_path}")

def append_image_to_notion(page_id, image_url):
    """
    Notionページに生成された財務図解画像を挿入する処理
    """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    payload = {
        "children": [
            {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {
                        "url": image_url
                    }
                }
            }
        ]
    }
    res = requests.patch(url, headers=headers, json=payload)
    if res.status_code == 200:
        print("Notionページに画像を正常に追加しました！")
    else:
        print(f"Notion画像追加失敗: {res.text}")

if __name__ == "__main__":
    print("財務図解生成スクリプト待機中。")
