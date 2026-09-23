-- 2. 子テーブル（XBRLタグ紐付け）の作成
CREATE TABLE IF NOT EXISTS xbrl_tag_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,      -- 管理用ID（主キー・自動採番）
    item_id INTEGER NOT NULL,                  -- 科目番号（親テーブルを参照する外部キー）
    company_code TEXT,                         -- 証券コード（例: '6141', '6105'）
    xbrl_tag_id TEXT NOT NULL,                 -- EDINETで使われているXBRLタグID
    source_company TEXT,                       -- 参考・確認した企業名
    accounting_standard TEXT,                  -- 会計基準（IFRS / J-GAAP など）
    notes TEXT,                                -- 補足（タイポやContext情報など）
    FOREIGN KEY (item_id) REFERENCES account_items(item_id) ON DELETE CASCADE
);
