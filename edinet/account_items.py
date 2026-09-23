-- 1. 親テーブル（科目マスター）の作成
CREATE TABLE IF NOT EXISTS account_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT, -- 科目番号（主キー・自動採番）
    item_name TEXT NOT NULL UNIQUE             -- 科目名（例: 流動資産, 固定負債など）
);
