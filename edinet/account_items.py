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

# 3. 親テーブル（account_items）に基本科目を登録
# (既に存在する場合はスキップされるように INSERT OR IGNORE を使用)
initial_items = [
    (1, '流動資産'),
    (2, '固定資産'),
    (3, '流動負債'),
    (4, '固定負債'),
    (5, '売上高'),
    (6, '純資産'),
    (7, '当期純利益'),
    (8, '総資産'),
    (9, '営業CF'),
    (10, '投資CF'),
    (11, '財務CF')
]

cursor.executemany("""
INSERT OR IGNORE INTO account_items (item_id, item_name) VALUES (?, ?);
""", initial_items)

conn.commit()
conn.close()

print("Database and parent table items initialized successfully.")
