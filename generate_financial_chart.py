def sync_pending_images_to_notion(tasks):
    now_ts = int(time.time())
    for task in tasks:
        page_id = task['page_id']
        chart_list = task['chart_list']
        
        children_blocks = []
        for item in chart_list:
            filename = os.path.basename(item['rel_path'])
            # Raw URLにパラメータを付与してキャッシュを無効化
            image_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/main/images/{filename}?v={now_ts}"
            print(f"送信中の画像URL: {image_url}")
            
            children_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": f"▼ {item['year']}年度 財務構造 (BS/PL)"}}]
                }
            })
            children_blocks.append({
                "object": "block",
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": image_url}
                }
            })

        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        payload = {"children": children_blocks}
        res = requests.patch(url, headers=headers, json=payload)
        if res.status_code == 200:
            print(f"Notionへ {len(chart_list)}枚 の画像ブロックを追加しました。")
        else:
            print(f"Notion画像追加エラー: {res.text}")
