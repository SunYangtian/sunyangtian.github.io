"""Offline tests: synthetic Scholar HTML, never substitute test values into the site."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('update_scholar', Path(__file__).resolve().parents[1] / 'scripts/update_scholar.py')
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)
URL = 'https://scholar.google.com/citations?hl=en&user=a4GKTmsAAAAJ'
NOW = datetime(2026, 10, 27, 4, 27, tzinfo=timezone.utc)


def profile(count='1,600'):
    return f'''<html><head><link rel="canonical" href="{URL.replace('&', '&amp;')}"></head>
      <body><div id="gsc_prf_in">Test Author</div>
      <table id="gsc_rsb_st"><tr><th></th><th>All</th><th>Since 2021</th></tr>
      <tr><td><a>Citations</a></td><td class="gsc_rsb_std">{count}</td><td>900</td></tr>
      <tr><td>h-index</td><td>20</td><td>18</td></tr>
      <tr><td>i10-index</td><td>40</td><td>38</td></tr></table>
      <table><tr><td>Citations</td><td>99999</td></tr></table></body></html>'''


def seed():
    return {'schema_version': 1, 'scholar': {'url': URL, 'citations': 1530, 'updated_at': None, 'source': 'local-fallback'}}


class ParserTests(unittest.TestCase):
    def test_total_not_recent_or_h_index(self):
        self.assertEqual(updater.parse_citations(profile(), URL, URL), 1600)

    def test_quotes_attribute_order_and_nested_text(self):
        html = profile('1234').replace('id="gsc_rsb_st"', "class='stats' id='gsc_rsb_st'")
        html = html.replace('1234</td>', '<span>1234</span></td>')
        self.assertEqual(updater.parse_citations(html, URL, URL), 1234)

    def test_real_zero_is_valid(self):
        self.assertEqual(updater.parse_citations(profile('0'), URL, URL), 0)

    def test_missing_or_malformed_data(self):
        for value in ('', '1,2,3', '-1', '1.5', 'NaN', '1 234', str(2**53)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                updater.parse_citations(profile(value), URL, URL)
        for html in ('', '<html>blocked</html>', profile().replace('Citations', 'Unknown'),
                     profile().replace('All', 'Recent'), profile().replace('gsc_prf_in', 'other')):
            with self.subTest(html=html[:40]), self.assertRaises(ValueError):
                updater.parse_citations(html, URL, URL)

    def test_captcha_is_not_a_metric(self):
        for banner in ('unusual traffic', '<div class="g-recaptcha">', 'not a robot'):
            with self.subTest(banner=banner), self.assertRaises(ValueError):
                updater.parse_citations(profile() + banner, URL, URL)

    def test_reordered_columns_and_ambiguous_rows(self):
        html = profile().replace('<th>All</th><th>Since 2021</th>', '<th>Since 2021</th><th>All</th>')
        self.assertEqual(updater.parse_citations(html, URL, URL), 900)
        duplicate = '<tr><td>Citations</td><td>2000</td><td>1000</td></tr>'
        with self.assertRaises(ValueError):
            updater.parse_citations(profile().replace('</table>', duplicate + '</table>', 1), URL, URL)

    def test_wrong_profile_or_redirect(self):
        wrong = URL.replace('a4GKTmsAAAAJ', 'otherUserAAA')
        with self.assertRaises(ValueError):
            updater.parse_citations(profile(), URL, wrong)
        with self.assertRaises(ValueError):
            updater.parse_citations(profile().replace('a4GKTmsAAAAJ', 'otherUserAAA'), URL, URL)
        for url in ('http://scholar.google.com/citations?user=a4GKTmsAAAAJ',
                    'https://example.com/citations?user=a4GKTmsAAAAJ', URL + '&user=otherUserAAA'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                updater.profile_user(url)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='scholar-test-')
        self.addCleanup(self.folder.cleanup)
        self.config = Path(self.folder.name) / 'content.json'
        self.output = Path(self.folder.name) / 'metrics.json'
        self.config.write_text(json.dumps({'scholar': {'url': URL}}))
        self.output.write_text(json.dumps(seed()) + '\n')

    def update(self, count='1600', **kwargs):
        return updater.update(self.config, self.output, now=NOW,
                              fetcher=lambda url, timeout: (profile(count), URL), **kwargs)

    def test_success_updates_timestamp_and_preserves_other_fields(self):
        old = seed()
        old['unrelated'] = {'keep': True}
        self.output.write_text(json.dumps(old))
        self.update()
        saved = json.loads(self.output.read_text())
        self.assertEqual(saved['scholar']['citations'], 1600)
        self.assertEqual(saved['scholar']['updated_at'], '2026-10-27T04:27:00Z')
        self.assertEqual(saved['scholar']['source'], 'google-scholar')
        self.assertEqual(saved['unrelated'], {'keep': True})

    def test_same_count_is_still_successfully_checked(self):
        self.update('1530')
        self.assertEqual(json.loads(self.output.read_text())['scholar']['updated_at'], '2026-10-27T04:27:00Z')

    def test_legitimate_decrease_and_zero(self):
        for count in ('1500', '0'):
            self.update(count)
            self.assertEqual(json.loads(self.output.read_text())['scholar']['citations'], int(count))

    def test_parse_failure_preserves_bytes_and_timestamp(self):
        self.update()
        before = self.output.read_bytes()
        with self.assertRaises(ValueError):
            self.update('not available')
        self.assertEqual(self.output.read_bytes(), before)

    def test_network_failure_preserves_bytes(self):
        before = self.output.read_bytes()
        def fail(url, timeout):
            raise TimeoutError('test timeout')
        with self.assertRaises(TimeoutError):
            updater.update(self.config, self.output, fetcher=fail, now=NOW)
        self.assertEqual(self.output.read_bytes(), before)

    def test_atomic_replace_failure_preserves_old_snapshot(self):
        before = self.output.read_bytes()
        with patch.object(updater.os, 'replace', side_effect=OSError('test disk failure')), self.assertRaises(OSError):
            self.update()
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.output.parent.iterdir()), ['content.json', 'metrics.json'])

    def test_dry_run_does_not_modify_snapshot(self):
        before = self.output.read_bytes()
        result = self.update(dry_run=True)
        self.assertEqual(result['scholar']['citations'], 1600)
        self.assertEqual(self.output.read_bytes(), before)

    def test_corrupted_snapshot_is_not_replaced(self):
        self.output.write_text('{broken')
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual(self.output.read_text(), '{broken')

    def test_invalid_schema_version_is_not_replaced(self):
        for version in (True, 1.0, '1', 99):
            old = seed()
            old['schema_version'] = version
            self.output.write_text(json.dumps(old))
            before = self.output.read_bytes()
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.update()
            self.assertEqual(self.output.read_bytes(), before)

    def test_symlink_output_does_not_change_target(self):
        alias = self.output.parent / 'alias.json'
        alias.symlink_to(self.output)
        before = self.output.read_bytes()
        with self.assertRaises(ValueError):
            updater.update(self.config, alias, now=NOW, fetcher=lambda url, timeout: (profile(), URL))
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.output.read_bytes(), before)

    def test_content_cannot_be_output(self):
        before = self.config.read_bytes()
        with self.assertRaises(ValueError):
            updater.update(self.config, self.config)
        self.assertEqual(self.config.read_bytes(), before)

    def test_transport_http_errors_and_timeout(self):
        for error in ('403', '429'):
            result = subprocess.CompletedProcess([], 22, '', f'HTTP {error}')
            with patch.object(updater.subprocess, 'run', return_value=result), self.assertRaises(RuntimeError):
                updater.fetch_profile(URL, 5)
        with patch.object(updater.subprocess, 'run', side_effect=subprocess.TimeoutExpired('curl', 10)), self.assertRaises(subprocess.TimeoutExpired):
            updater.fetch_profile(URL, 5)

    def test_transport_validates_final_url_and_total_deadline(self):
        def transport(command, **kwargs):
            self.assertIn('--max-time', command)
            self.assertEqual(command[command.index('--max-time') + 1], '5')
            self.assertEqual(kwargs['timeout'], 10)
            Path(command[command.index('--output') + 1]).write_text(profile())
            return subprocess.CompletedProcess(command, 0, URL, '')
        with patch.object(updater.subprocess, 'run', side_effect=transport):
            html, final_url = updater.fetch_profile(URL, 5)
        self.assertEqual(updater.parse_citations(html, URL, final_url), 1600)


if __name__ == '__main__':
    unittest.main()
