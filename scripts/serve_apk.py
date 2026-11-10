import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

APK_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "companion-app", "build", "GNDROiD_Companion.apk"))
if not os.path.exists(APK_PATH):
    APK_PATH = r"C:\Users\Reader-Branch\Desktop\GNDROiD_Companion.apk"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GNDROiD Link v2.5.0 Download</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: #0b0f19; color: #f8fafc; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; }
        .card { background: #131b2e; border: 1px solid #1e293b; border-radius: 16px; padding: 28px; max-width: 440px; width: 100%; text-align: center; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
        .badge { display: inline-block; background: #0284c7; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; margin-bottom: 16px; text-transform: uppercase; }
        h1 { font-size: 22px; margin-bottom: 8px; color: #ffffff; }
        p.sub { font-size: 13px; color: #94a3b8; margin-bottom: 24px; line-height: 1.5; }
        .btn-download { display: block; width: 100%; background: linear-gradient(135deg, #0284c7, #2563eb); color: #ffffff; text-decoration: none; padding: 14px 20px; border-radius: 10px; font-size: 16px; font-weight: bold; margin-bottom: 12px; box-shadow: 0 4px 14px rgba(2, 132, 199, 0.4); }
        .btn-download:hover { background: linear-gradient(135deg, #0369a1, #1d4ed8); }
        .btn-alt { display: block; width: 100%; background: #1e293b; color: #cbd5e1; text-decoration: none; padding: 12px 20px; border-radius: 10px; font-size: 13px; font-weight: 600; margin-bottom: 20px; border: 1px solid #334155; }
        .features { text-align: left; background: #0f172a; padding: 14px 18px; border-radius: 10px; font-size: 12px; color: #94a3b8; line-height: 1.6; }
        .features b { color: #38bdf8; }
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">v2.5.0 Universal</span>
        <h1>GNDROiD Link Companion</h1>
        <p class="sub">High-Speed LAN Screen Mirror &amp; Remote Display for Android Phones &amp; Android TV</p>

        <a href="/GNDROiD_Companion.apk" class="btn-download">📥 Download APK (66.5 KB)</a>
        <a href="https://github.com/gnonymous1/GNDROiD/releases/download/v2.2.2/GNDROiD_Companion.apk" class="btn-alt" target="_blank">🌐 Alternative: GitHub Direct Link</a>

        <div class="features">
            <b>⚡ What's New in v2.5.0:</b><br>
            • <b>Hardware H.264 Cast:</b> 60 FPS ultra-low latency.<br>
            • <b>Android TV Mode:</b> Full TV remote D-Pad &amp; OK control.<br>
            • <b>Peer-to-Peer Display:</b> Mirror phone-to-phone or phone-to-TV.<br>
            • <b>PC Typing &amp; Mouse Wheel:</b> Instant typing from computer keyboard.
        </div>
    </div>
</body>
</html>"""

class SmartAPKHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.serve(send_body=False)

    def do_GET(self):
        self.serve(send_body=True)

    def serve(self, send_body=True):
        path = self.path.split("?")[0].strip()
        lower_path = path.lower()

        # If requesting APK directly or shortcut
        if lower_path.endswith(".apk") or lower_path in ["/apk", "/download", "/app", "/companion"]:
            if not os.path.exists(APK_PATH):
                self.send_error(404, "APK file not found on disk")
                return

            size = os.path.getsize(APK_PATH)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Disposition", 'attachment; filename="GNDROiD_Companion.apk"')
            self.send_header("Content-Length", str(size))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()

            if send_body:
                with open(APK_PATH, "rb") as f:
                    while True:
                        buf = f.read(65536)
                        if not buf:
                            break
                        self.wfile.write(buf)
            return

        # Default Landing Page for root or anything else
        html_bytes = HTML_TEMPLATE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if send_body:
            self.wfile.write(html_bytes)

    def log_message(self, format, *args):
        print(f"[{self.headers.get('Host', '')}] {self.command} {self.path} - {args[1] if len(args) > 1 else ''}")

def run_server(port):
    server = HTTPServer(("0.0.0.0", port), SmartAPKHandler)
    print(f"[*] Smart APK Server listening on http://0.0.0.0:{port}")
    try:
        server.serve_forever()
    except Exception:
        pass

if __name__ == "__main__":
    ports = [8088, 8080]
    threads = []
    for p in ports:
        t = threading.Thread(target=run_server, args=(p,), daemon=True)
        t.start()
        threads.append(t)
    print(f"GNDROiD Multi-Port APK Web Server running on ports {ports}")
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        sys.exit(0)
