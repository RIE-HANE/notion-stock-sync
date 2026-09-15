import os
import tempfile
from flask import Flask, jsonify
from pyngrok import conf, ngrok
from sync_company_data import sync_company_data

app = Flask(__name__)

# セキュリティブロック（PermissionError）を回避するため一時フォルダを使用
temp_dir = os.path.join(tempfile.gettempdir(), "pyngrok")
os.makedirs(temp_dir, exist_ok=True)
conf.get_default().ngrok_path = os.path.join(temp_dir, "ngrok.exe")


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    print("\n🔔 Notionから更新リクエストを受信しました！")
    try:
        sync_company_data()
        return (
            jsonify(
                {"status": "success", "message": "Sync completed successfully"}
            ),
            200,
        )
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    try:
        # ポート5000を外部公開
        public_url = ngrok.connect(5000).public_url
        print("\n" + "=" * 50)
        print("🌐 【成功】外部公開URLが発行されました！")
        print(f"   Webhook URL: {public_url}/webhook")
        print("=" * 50 + "\n")
    except Exception as e:
        print(f"\n⚠️ ngrok接続エラー: {e}\n")

    print("📡 受信サーバーを起動中... (Port: 5000)")
    app.run(port=5000)