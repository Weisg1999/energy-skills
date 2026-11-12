import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const POLICY_DIR = 'knowledge';
const HOSTS = ['gov.cn', 'ndrc.gov.cn', 'nea.gov.cn', 'mee.gov.cn'];
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36';

const norm = (s) => s
  .replace(/<[^>]+>/g, '')
  .replace(/&nbsp;|&emsp;|&#\d+;/g, '')
  .replace(/\s+/g, '')
  .replace(/[〔【\[]/g, '〔')
  .replace(/[〕】\]]/g, '〕');

const loose = (s) => norm(s).replace(/[《》〈〉（）()、，,。."'“”‘’·—－-]/g, '');

function isPolicyFile(md) {
  const head = md.split('\n').slice(0, 30).join('\n');
  return /^layout:\s*policy\s*$/m.test(head);
}

function collectRows(md) {
  const rows = [];
  for (const line of md.split('\n')) {
    if (!/^\s*\|/.test(line)) continue;
    const cells = line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((s) => s.trim());
    if (cells.length < 7) continue;
    const link = cells[cells.length - 1].match(/\[([^\]]+)\]\((https?:[^)]+)\)/);
    if (!link) continue;
    rows.push({
      no: cells[0],
      title: cells[1],
      org: cells[cells.length - 4] ?? '',
      date: cells[cells.length - 3] ?? '',
      status: cells[cells.length - 2] ?? '',
      linkText: link[1],
      url: link[2],
    });
  }
  return rows;
}

async function fetchText(url) {
  const res = await fetch(url, {
    redirect: 'follow',
    headers: { 'User-Agent': UA },
    signal: AbortSignal.timeout(30000),
  });
  const buf = await res.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let text = new TextDecoder('utf-8').decode(bytes);
  if (/charset=["']?(gb2312|gbk|gb18030)/i.test(text.slice(0, 2000))) {
    text = new TextDecoder('gb18030').decode(bytes);
  }
  return { status: res.status, finalUrl: res.url, type: res.headers.get('content-type') || '', text };
}

function pickTitle(html) {
  const m = html.match(/<meta[^>]+(?:ArticleTitle|name="title")[^>]+content="([^"]+)"/i)
    || html.match(/<meta[^>]+content="([^"]+)"[^>]+(?:ArticleTitle|name="title")/i)
    || html.match(/<title>([\s\S]*?)<\/title>/i);
  return m ? m[1].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim() : '';
}

async function checkNdcArticle(url) {
  const id = new URL(url).searchParams.get('articleId');
  const res = await fetch(`https://yyglxxbsgw.ndrc.gov.cn/public/submission-service/column/getArticleDetail?articleId=${id}`, {
    headers: { 'User-Agent': UA },
    signal: AbortSignal.timeout(30000),
  });
  const json = await res.json();
  const data = json?.data || {};
  return {
    status: res.status,
    title: String(data.articleTitle || data.title || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' '),
    body: norm(`${data.articleTitle || ''} ${data.articleContent || ''} ${JSON.stringify(data)}`),
    type: 'application/json',
  };
}

function docVariants(row) {
  const out = new Set();
  if (row.no && row.no !== '—') {
    out.add(norm(row.no));
    const decree = norm(row.no).match(/令第(\d+)号/);
    if (decree) {
      out.add(`第${decree[1]}号令`);
      out.add(`${decree[1]}号令`);
    }
  }
  const inner = (row.title.match(/《([^》]+)》/) || [])[1] || row.title;
  const titleKey = loose(inner);
  out.add(titleKey);
  if (titleKey.length >= 12) out.add(titleKey.slice(0, 8));
  out.add(loose(row.title.replace(/^关于印发/, '').replace(/的通知$/, '')));
  return [...out].filter((v) => v.length >= 8);
}

let bad = 0;
let unreachable = 0;
let total = 0;
const files = readdirSync(POLICY_DIR).filter((f) => f.endsWith('.md'));

for (const file of files) {
  const md = readFileSync(join(POLICY_DIR, file), 'utf8');
  if (!isPolicyFile(md)) continue;
  const rows = collectRows(md);
  console.log(`\n## ${file} (${rows.length})`);
  for (const r of rows) {
    total += 1;
    const host = new URL(r.url).hostname;
    const hostOk = HOSTS.some((h) => host === h || host.endsWith('.' + h));
    let status = 0;
    let body = '';
    let title = '';
    let isPdf = false;
    let extra = '';
    let networkError = false;
    try {
      if (host === 'yyglxxbsgw.ndrc.gov.cn' && /article\.html\?articleId=/.test(r.url)) {
        const got = await checkNdcArticle(r.url);
        ({ status, title } = got);
        body = got.body;
      } else {
        const got = await fetchText(r.url);
        status = got.status;
        title = pickTitle(got.text);
        isPdf = /application\/pdf/i.test(got.type) || /\.pdf(?:$|\?)/i.test(got.finalUrl);
        body = isPdf ? '' : norm(`${got.text} ${title}`);
        if (got.finalUrl !== r.url) extra = got.finalUrl;
      }
    } catch (e) {
      extra = e.message;
      networkError = true;
    }
    const bodyLoose = loose(body);
    const hasDoc = isPdf
      ? true
      : docVariants(r).some((v) => body.includes(v) || bodyLoose.includes(v));
    const ok = status === 200 && hostOk && hasDoc;
    if (networkError || status === 0) {
      unreachable += 1;
      console.log(`WARN 0 network-unverifiable | ${r.no} | ${extra}`);
      console.log(`     ${r.url}`);
      console.log('     transport-layer failure is not evidence of a broken link; re-check with curl before editing the ledger.');
    } else {
      if (!ok) bad += 1;
      const mark = [status, hostOk ? 'host' : 'HOST!', isPdf ? 'pdf' : hasDoc ? 'match' : 'NO-MATCH'];
      console.log(`${ok ? 'OK ' : 'BAD'} ${mark.join(' ')} | ${r.no} | ${title.slice(0, 50)}${extra ? ' | ' + extra : ''}`);
      if (!ok) {
        console.log(`     ${r.url}`);
        console.log(`     variants: ${docVariants(r).map((v) => v.slice(0, 30)).join(' / ')}`);
      }
    }
    await new Promise((res) => setTimeout(res, 350));
  }
}

console.log(`\n${total} links, ${bad} bad, ${unreachable} network-unverifiable`);
process.exit(bad ? 1 : 0);
