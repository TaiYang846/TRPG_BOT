"""
極簡 HTTP 服務（給 Render 的 Web Service 用）
------------------------
為什麼需要這個檔案：
Render 的 Web Service 要求程式必須開一個網頁埠口，否則會判定部署失敗。
Discord 機器人本身不需要網頁，所以這裡只開一個最簡單的服務，
任何人（或定時戳的工具）訪問網址時，只會回覆「OK」。

另外，Render 的免費 Web Service 閒置 15 分鐘沒收到外來請求就會休眠，
所以需要用外部服務（例如 cron-job.org、UptimeRobot）定時訪問這個網址，
機器人才不會跟著睡著。

使用方式（在 bot.py 裡，放在 client.run(TOKEN) 之前）：
    import web_server
    web_server.start()
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _PingHandler(BaseHTTPRequestHandler):
    def _reply_ok(self, include_body: bool):
        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self):
        self._reply_ok(include_body=True)

    def do_HEAD(self):
        # 有些監控服務（例如 UptimeRobot）預設用 HEAD 請求，所以也要處理
        self._reply_ok(include_body=False)

    def log_message(self, format, *args):
        # 定時戳每幾分鐘就來一次，不把每筆請求都印到日誌，避免洗版
        pass


def start() -> None:
    """在背景執行緒啟動 HTTP 服務，不會卡住機器人本身的運作"""
    # Render 會自動設定 PORT 環境變數；本機測試沒有設定時就用 10000
    port = int(os.getenv("PORT", "10000"))

    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), _PingHandler)
    except OSError as e:
        print(f"⚠️ 無法在埠口 {port} 啟動 HTTP 服務，這不影響機器人本身運作：{e}")
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"🌐 HTTP 服務已啟動，監聽埠口 {port}")
