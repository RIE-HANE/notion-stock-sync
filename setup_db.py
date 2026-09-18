import sqlite3

DB_FILE = "financial_data.db"

def init_db():
    """データベースとテーブルの初期化"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS financial_metrics (
        ticker TEXT,
        year INTEGER,
        total_assets REAL,
        current_assets REAL,
        fixed_assets REAL,
        current_liab REAL,
        fixed_liab REAL,
        equity REAL,
        sales REAL,
        op_profit REAL,
        net_income REAL,
        PRIMARY KEY (ticker, year)
    )
    ''')
    conn.commit()
    conn.close()

def upsert_financial_data(ticker, year, data):
    """
    動的引数を受け取ってDBに登録・更新する汎用関数
    任意の証券コード(ticker)と年度(year)を変数として受け取ります。
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT OR REPLACE INTO financial_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        str(ticker).strip(),
        int(year),
        data.get("total_assets", 0),
        data.get("current_assets", 0),
        data.get("fixed_assets", 0),
        data.get("current_liab", 0),
        data.get("fixed_liab", 0),
        data.get("equity", 0),
        data.get("sales", 0),
        data.get("op_profit", 0),
        data.get("net_income", 0)
    ))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # 直接実行された場合は DB テーブルの初期化のみを行う
    init_db()
    print("データベースの初期化（テーブル作成）が完了しました。")
