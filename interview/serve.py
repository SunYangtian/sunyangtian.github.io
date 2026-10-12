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


def parse_citations(text):
    """Return a positive all-time citation count from Scholar output, if present."""
    if not isinstance(text, str):
        return None
    patterns = (
        r'<td[^>]*class=["\'][^"\']*\bgsc_rsb_std\b[^"\']*["\'][^>]*>\s*([\d,]+)',
        r'(?:^|\n)\s*\|\s*Citations\s*\|\s*([\d,]+)\s*(?:\||$)',
        r'(?:^|\n)\s*Citations\s*(?:\||:\s*|\s+)([\d,]+)\b',
        r'\bCitations\s+([\d,]+)\b',
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            citations = int(match.group(1).replace(',', ''))
            if citations > 0:
                return citations
    return None


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

        def read(url, timeout=8):
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()

        def scholar_metric():
            scholar_html = read(config['scholar']['url'], timeout=25).decode('utf-8', errors='replace')
            return parse_citations(scholar_html)

        def github_metric(item):
            key, repo = item
            payload = json.loads(read(f"https://api.github.com/repos/{repo['name']}").decode('utf-8'))
            return key, payload.get('stargazers_count')

        repository_items = list(config.get('repositories', {}).items())
        futures = {}
        worker_count = max(1, len(repository_items) + (1 if config.get('scholar', {}).get('url') else 0))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            if config.get('scholar', {}).get('url'):
                futures[pool.submit(scholar_metric)] = ('scholar', None)
            for item in repository_items:
                futures[pool.submit(github_metric, item)] = ('github', item[0])
            for future in as_completed(futures):
                kind, key = futures[future]
                try:
                    if kind == 'scholar':
                        citations = future.result()
                        if isinstance(citations, int) and citations > 0:
                            result['scholar']['citations'] = citations
                    else:
                        _, stars = future.result()
                        if isinstance(stars, int):
                            result['repositories'][key]['stars'] = stars
                except Exception as exc:
                    label = 'Google Scholar' if kind == 'scholar' else 'GitHub stars'
                    print(f'动态读取 {label} 失败，使用本地快照：{exc}', file=sys.stderr)

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
