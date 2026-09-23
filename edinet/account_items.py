import sqlite3
import os

# データベースファイルの保存先フォルダを作成（存在しない場合）
os.makedirs("db", exist_ok=True)

# データベース接続
conn = sqlite3.connect("db/financial_data.db")
cursor = conn.cursor()

# 1. 親テーブルの枠を作成（科目マスター）
cursor.execute("""
CREATE TABLE IF NOT EXISTS account_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL UNIQUE
);
""")

# 2. 子テーブルの枠を作成（XBRLタグ紐付け）
cursor.execute("""
CREATE TABLE IF NOT EXISTS xbrl_tag_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    company_code TEXT,
    xbrl_tag_id TEXT NOT NULL,
    source_company TEXT,
    accounting_standard TEXT,
    notes TEXT,
    FOREIGN KEY (item_id) REFERENCES account_items(item_id) ON DELETE CASCADE
);
""")

conn.commit()
conn.close()

print("Database and tables initialized successfully.")
