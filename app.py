"""Web server tĩnh phục vụ trang tải về trong thư mục web/.

Đây KHÔNG phải autoclicker. File autoclicker.py là app desktop, chạy trên
máy người dùng, không bao giờ chạy trên server. File này chỉ phục vụ trang
HTML giới thiệu và link tải.

Dùng thuần thư viện chuẩn của Python — không cần cài gì thêm.
"""

import functools
import http.server
import os
import socketserver

PORT = int(os.environ.get("PORT", 8080))
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def guess_type(self, path):
        # Không khai báo charset thì một số trình duyệt đoán sai bảng mã và
        # tiếng Việt hiển thị thành ký tự lạ.
        ctype = super().guess_type(path)
        if ctype in ("text/html", "text/css", "application/javascript", "text/javascript"):
            return ctype + "; charset=utf-8"
        return ctype

    def log_message(self, fmt, *args):
        # Ghi log ra stdout để vibehost đọc được
        print(f"{self.address_string()} {fmt % args}", flush=True)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    handler = functools.partial(Handler, directory=WEB_DIR)
    with Server(("0.0.0.0", PORT), handler) as httpd:
        print(f"Đang phục vụ {WEB_DIR} tại cổng {PORT}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
