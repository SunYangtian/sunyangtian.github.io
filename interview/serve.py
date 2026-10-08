#!/usr/bin/env python3
"""Local static preview. No third-party Python packages are required."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys
import threading
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?', 1)[0] == '/metrics.json':
            self.send_metrics()
            return
        super().do_GET()

    def send_metrics(self):
        """Read public Scholar/GitHub metrics at request time for the browser."""
        config = json.loads((ROOT / 'content.json').read_text(encoding='utf-8'))
        fallback = {
            'scholar': {'citations': config.get('scholar', {}).get('citations', 0)},
            'repositories': {key: {'stars': value.get('stars', 0)} for key, value in config.get('repositories', {}).items()},
        }
        result = json.loads(json.dumps(fallback))
        headers = {'User-Agent': 'Yang-Tian-Sun-interview-metrics/1.0', 'Accept': 'application/vnd.github+json'}

        def read(url):
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                return response.read()

        try:
            scholar_html = read(config['scholar']['url']).decode('utf-8', errors='replace')
            values = re.findall(r'<td[^>]*class="gsc_rsb_std"[^>]*>\s*([\d,]+)', scholar_html)
            if values:
                result['scholar']['citations'] = int(values[0].replace(',', ''))
        except Exception as exc:
            print(f'动态读取 Google Scholar 失败，使用本地快照：{exc}', file=sys.stderr)

        def github_metric(item):
            key, repo = item
            payload = json.loads(read(f"https://api.github.com/repos/{repo['name']}").decode('utf-8'))
            return key, payload.get('stargazers_count')

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(github_metric, item) for item in config.get('repositories', {}).items()]
            for future in as_completed(futures):
                try:
                    key, stars = future.result()
                    if isinstance(stars, int):
                        result['repositories'][key]['stars'] = stars
                except Exception as exc:
                    print(f'动态读取 GitHub stars 失败，使用本地快照：{exc}', file=sys.stderr)

        body = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

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
