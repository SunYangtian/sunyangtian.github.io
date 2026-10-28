#!/usr/bin/env python3
"""Fetch a public Scholar profile once; publish only a verified all-time total.

Requires Python 3.10+ and curl (available on GitHub's Ubuntu runners).
No proxy, cookies, API key or CAPTCHA bypass is used.
"""
import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_COUNT = 2**53 - 1


def profile_user(url):
    parts = urlsplit(url)
    users = parse_qs(parts.query).get('user', [])
    if (parts.scheme != 'https' or parts.netloc != 'scholar.google.com'
            or parts.path != '/citations' or len(users) != 1
            or not re.fullmatch(r'[A-Za-z0-9_-]{6,64}', users[0])):
        raise ValueError('Expected an HTTPS Google Scholar profile URL with one user ID')
    return users[0]


class ScholarPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.row = None
        self.cell = None
        self.rows = []
        self.has_profile = False
        self.canonical_urls = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get('id') == 'gsc_prf_in':
            self.has_profile = True
        if tag == 'link' and 'canonical' in attrs.get('rel', '').split():
            self.canonical_urls.append(attrs.get('href', ''))
        if tag == 'meta' and attrs.get('property') == 'og:url':
            self.canonical_urls.append(attrs.get('content', ''))
        if tag == 'table':
            if self.table_depth or attrs.get('id') == 'gsc_rsb_st':
                self.table_depth += 1
        if self.table_depth == 1:
            if tag == 'tr':
                self.row = []
            elif tag in ('td', 'th') and self.row is not None:
                self.cell = []

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            self.cell = None
        elif tag == 'table' and self.table_depth:
            self.table_depth -= 1


def parse_citations(html, expected_url, final_url):
    """Use the labelled All/Citations table, never publication or h-index totals."""
    user = profile_user(expected_url)
    if profile_user(final_url) != user:
        raise ValueError('Scholar redirected to a different profile')
    if re.search(r'unusual traffic|g-recaptcha|not a robot', html, re.I):
        raise ValueError('Scholar returned a verification page')
    page = ScholarPage()
    page.feed(html)
    if not page.has_profile:
        raise ValueError('Missing Scholar profile marker')
    for canonical in page.canonical_urls:
        if profile_user(canonical) != user:
            raise ValueError('Scholar page identifies a different profile')
    all_column = None
    totals = []
    for row in page.rows:
        if 'All' in row:
            all_column = row.index('All')
        if row and row[0].casefold() == 'citations':
            if all_column is None or all_column == 0 or all_column >= len(row):
                raise ValueError('Missing All column in citation table')
            value = row[all_column]
            if not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)', value):
                raise ValueError('Invalid all-time citation total')
            count = int(value.replace(',', ''))
            if count > MAX_COUNT:
                raise ValueError('Citation total exceeds the browser integer range')
            totals.append(count)
    if len(totals) != 1:
        raise ValueError('Expected exactly one all-time citation row')
    return totals[0]


def fetch_profile(url, timeout):
    user = profile_user(url)
    target = 'https://scholar.google.com/citations?' + urlencode({'hl': 'en', 'user': user})
    with tempfile.TemporaryDirectory(prefix='scholar-fetch-') as folder:
        body = Path(folder) / 'profile.html'
        command = [
            'curl', '--silent', '--show-error', '--fail', '--location',
            '--max-redirs', '3', '--proto', '=https', '--proto-redir', '=https',
            '--connect-timeout', '10', '--max-time', str(timeout),
            '--max-filesize', '2097152', '--header', 'Accept: text/html',
            '--user-agent', 'ScholarSnapshot/1.0 (public profile statistics)',
            '--output', str(body), '--write-out', '%{url_effective}', target,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 5)
        if result.returncode:
            raise RuntimeError(f'Scholar request failed (curl {result.returncode}): {result.stderr.strip()}')
        final_url = result.stdout.strip()
        if profile_user(final_url) != user:
            raise ValueError('Unexpected final Scholar URL')
        return body.read_text(encoding='utf-8'), final_url


def read_snapshot(output, url):
    if not output.exists():
        return {'schema_version': 1}
    snapshot = json.loads(output.read_text(encoding='utf-8'))
    if (not isinstance(snapshot, dict) or type(snapshot.get('schema_version')) is not int
            or snapshot['schema_version'] != 1):
        raise ValueError('Existing snapshot has an unsupported schema; leave it unchanged')
    scholar = snapshot.get('scholar', {})
    if (not isinstance(scholar, dict) or profile_user(scholar.get('url', '')) != profile_user(url)
            or type(scholar.get('citations')) is not int
            or not 0 <= scholar['citations'] <= MAX_COUNT):
        raise ValueError('Existing snapshot has invalid profile/count; leave it unchanged')
    stamp = scholar.get('updated_at')
    if scholar.get('source') == 'local-fallback' and stamp is None:
        return snapshot
    if scholar.get('source') != 'google-scholar' or not isinstance(stamp, str):
        raise ValueError('Existing snapshot has invalid success metadata')
    datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%SZ')
    return snapshot


def save_snapshot(output, snapshot):
    # Resolve and check the exact replacement target before the atomic move.
    if output.is_symlink():
        raise ValueError('Snapshot target must not be a symlink')
    target = output.resolve()
    if not target.parent.is_dir() or (target.exists() and not target.is_file()):
        raise ValueError('Snapshot output must be a file in an existing directory')
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                         prefix=f'.{target.name}.', suffix='.tmp', delete=False) as file:
            temporary = Path(file.name).resolve()
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o644)
        if temporary.parent != target.parent or output.resolve() != target or output.is_symlink():
            raise ValueError('Snapshot target changed during update')
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists() and temporary.parent == target.parent:
            temporary.unlink()


def update(content, output, timeout=25, dry_run=False, fetcher=fetch_profile, now=None):
    if content.resolve() == output.resolve():
        raise ValueError('Snapshot output must not overwrite content.json')
    config = json.loads(content.read_text(encoding='utf-8'))
    url = config['scholar']['url']
    profile_user(url)
    snapshot = read_snapshot(output, url)
    html, final_url = fetcher(url, timeout)
    count = parse_citations(html, url, final_url)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    snapshot['scholar'] = {'url': url, 'citations': count, 'updated_at': timestamp, 'source': 'google-scholar'}
    if not dry_run:
        save_snapshot(output, snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--content', type=Path, default=ROOT / 'content.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'metrics.json')
    parser.add_argument('--timeout', type=int, default=25)
    parser.add_argument('--dry-run', action='store_true', help='Fetch and validate without writing')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 60:
        parser.error('--timeout must be between 1 and 60 seconds')
    try:
        value = update(args.content, args.output, args.timeout, args.dry_run)['scholar']
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'Scholar update failed; previous snapshot unchanged: {exc}', file=sys.stderr)
        return 1
    action = 'Validated (dry run)' if args.dry_run else 'Saved'
    print(f"{action}: {value['citations']} citations; fetched {value['updated_at']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
