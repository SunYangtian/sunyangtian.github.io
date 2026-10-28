// Exercise the production metrics functions with network/DOM fixtures, not live APIs.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const app = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
const start = app.indexOf('  let scholarSnapshot =');
const end = app.indexOf('  function syncVideos(', start);
assert.ok(start !== -1 && end > start, 'Production metrics functions must be present');
const url = 'https://scholar.google.com/citations?hl=en&user=a4GKTmsAAAAJ';
const stamp = days => new Date(Date.now() - days * 86400000).toISOString().replace(/\.\d{3}Z$/, 'Z');
const snapshot = (count = 1600, days = 1) => ({schema_version: 1, scholar: {url, citations: count, updated_at: stamp(days), source: 'google-scholar'}});
const seed = {schema_version: 1, scholar: {url, citations: 1530, updated_at: null, source: 'local-fallback'}};

function harness(fetcher = async () => { throw new Error('offline'); }) {
  const elements = {number: {textContent: '1,530'}, status: {textContent: '', title: '', dataset: {}}, star: {dataset: {repository:'demo',compact:'true'},setAttribute(){}}};
  const listeners = {}, intervals = [], requests = [];
  const data = {scholar: {url, citations: 1530}, repositories: {demo: {name:'owner/repo',stars:101}}};
  const document = {hidden: false, querySelector: () => elements.number, querySelectorAll: () => [elements.star], addEventListener: (type, cb) => {listeners[type] = cb;}};
  const context = vm.createContext({
    data, URL, Date, AbortController, setTimeout, clearTimeout, document,
    $: () => elements.status,
    window: {addEventListener: (type, cb) => {listeners[type] = cb;}},
    setInterval: (cb, delay) => {intervals.push({cb,delay});},
    fetch: async (endpoint, options) => { requests.push({endpoint,options}); return fetcher(endpoint, options); },
  });
  vm.runInContext(app.slice(start, end) + '\nglobalThis.metrics = {applyScholarSnapshot, updateMetrics, refreshMetrics, refreshScholarSnapshot, watchScholarSnapshot};', context);
  return {api: context.metrics, context, data, elements, document, listeners, intervals, requests};
}

const response = value => ({ok: true, json: async () => value});

test('verified snapshot updates count and last successful date', () => {
  const h = harness(), s = snapshot();
  assert.equal(h.api.applyScholarSnapshot(s), true);
  h.api.updateMetrics();
  assert.equal(h.elements.number.textContent, '1,600');
  assert.ok(h.elements.status.textContent.includes(s.scholar.updated_at.slice(0,10)));
  assert.equal(h.elements.status.dataset.state, 'snapshot');
});

test('initial fallback never invents a success timestamp', () => {
  const h = harness();
  assert.equal(h.api.applyScholarSnapshot(seed), true);
  h.api.updateMetrics();
  assert.equal(h.elements.number.textContent, '1,530');
  assert.equal(h.elements.status.dataset.state, 'fallback');
  assert.match(h.elements.status.textContent, /等待首次自动更新/);
});

test('rejects wrong profile, schema, count and timestamp', () => {
  const h = harness();
  for (const changes of [
    {citations: -1}, {citations: 1.5}, {citations: true}, {citations: '1600'}, {citations: 2**53},
    {url: url.replace('a4GKTmsAAAAJ', 'otherUserAAA')}, {source: 'unknown'},
    {url: url + '&user=otherUserAAA'}, {url: url.replace('scholar.google.com', 'scholar.google.com:444')},
    {updated_at: 'not-a-date'}, {updated_at: '2026-02-31T00:00:00Z'},
    {updated_at: stamp(-1)}, {updated_at: null},
  ]) {
    const s = snapshot(); Object.assign(s.scholar, changes);
    assert.equal(h.api.applyScholarSnapshot(s), false, JSON.stringify(changes));
  }
  assert.equal(h.api.applyScholarSnapshot({...snapshot(), schema_version: 99}), false);
  assert.equal(h.api.applyScholarSnapshot(null), false);
  assert.equal(h.data.scholar.citations, 1530);
});

test('accepts a newer legitimate decrease or zero, never an older snapshot', () => {
  const h = harness();
  assert.equal(h.api.applyScholarSnapshot(snapshot(1600, 3)), true);
  assert.equal(h.api.applyScholarSnapshot(snapshot(1599, 2)), true);
  assert.equal(h.api.applyScholarSnapshot(snapshot(0, 1)), true);
  assert.equal(h.api.applyScholarSnapshot(snapshot(1700, 4)), false);
  assert.equal(h.data.scholar.citations, 0);
});

test('old snapshot shows stale state without pretending to refresh it', () => {
  const h = harness();
  h.api.applyScholarSnapshot(snapshot(1600, 10)); h.api.updateMetrics();
  assert.equal(h.elements.status.dataset.state, 'stale');
  assert.match(h.elements.status.textContent, /快照较旧/);
});

test('GitHub still updates independently when snapshot request fails', async () => {
  const h = harness(async endpoint => endpoint === 'metrics.json' ? {ok:false,status:404} : response({stargazers_count:250}));
  await h.api.refreshMetrics();
  assert.equal(h.data.repositories.demo.stars, 250);
  assert.equal(h.data.scholar.citations, 1530);
  assert.match(h.elements.status.textContent, /暂无法读取/);
  assert.deepEqual(h.requests.map(r => r.endpoint).sort(), ['https://api.github.com/repos/owner/repo', 'metrics.json']);
  assert.equal(h.requests[0].options.cache, 'no-store');
});

test('a later network failure retains the last successful number and date', async () => {
  let success = true;
  const s = snapshot();
  const h = harness(async () => { if (!success) throw new Error('offline'); return response(s); });
  await h.api.refreshScholarSnapshot();
  success = false;
  await h.api.refreshScholarSnapshot();
  assert.equal(h.data.scholar.citations, 1600);
  assert.ok(h.elements.status.textContent.includes(s.scholar.updated_at.slice(0,10)));
  assert.match(h.elements.status.textContent, /暂无法检查更新/);
});

test('invalid snapshot body does not clear fallback', async () => {
  const h = harness(async () => ({ok: true, json: async () => {throw new Error('invalid JSON');}}));
  await h.api.refreshScholarSnapshot();
  assert.equal(h.data.scholar.citations, 1530);
  assert.equal(h.elements.status.dataset.state, 'fallback');
});

test('periodic and foreground checks are throttled and never scrape Scholar', async () => {
  const h = harness(async () => response(seed));
  h.api.watchScholarSnapshot();
  assert.equal(h.intervals[0].delay, 3600000);
  h.document.hidden = true;
  h.intervals[0].cb(); assert.equal(h.requests.length, 0);
  h.document.hidden = false;
  await h.api.refreshScholarSnapshot();
  h.intervals[0].cb(); assert.equal(h.requests.length, 1);
  vm.runInContext('lastScholarCheck = 0', h.context);
  h.listeners.visibilitychange();
  assert.equal(h.requests.length, 2);
  assert.ok(h.requests.every(r => r.endpoint === 'metrics.json'));
});

test('overlapping snapshot refreshes share one in-flight request', async () => {
  let resolve;
  const h = harness(() => new Promise(done => {resolve = done;}));
  const a = h.api.refreshScholarSnapshot();
  const b = h.api.refreshScholarSnapshot();
  assert.equal(h.requests.length, 1);
  resolve(response(seed));
  await Promise.all([a,b]);
});
