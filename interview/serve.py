#!/usr/bin/env python3
"""Serve the same static Interview Slides files as GitHub Pages."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    # metrics.json is a persisted snapshot, not a live scraping endpoint.
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description='启动本地面试展示')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    address = f'http://127.0.0.1:{args.port}/'
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(ROOT)))
    except OSError as exc:
        try:
            with urllib.request.urlopen(address + 'content.json', timeout=1) as response:
                existing = response.read()
            if existing == (ROOT / 'content.json').read_bytes():
                print(f'展示已运行：{address}', flush=True)
                if not args.no_browser:
                    webbrowser.open(address)
                return
        except Exception:
            pass
        print(f'无法使用端口 {args.port}：{exc}\n可改用：python3 serve.py --port 8766', file=sys.stderr)
        sys.exit(1)
    print(f'本地展示：{address}\n仅本机可访问。按 Control+C 停止服务。', flush=True)
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n展示服务已停止。')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
