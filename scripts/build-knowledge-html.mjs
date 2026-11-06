#!/usr/bin/env node
/**
 * 由 knowledge/index.html 的卡片清单 + knowledge/*.md 生成 HTML 内容页。
 *
 * 用法：
 *   node scripts/build-knowledge-html.mjs           # 生成页面并改写首页链接
 *   node scripts/build-knowledge-html.mjs --no-index # 只生成页面，不改 index.html
 *
 * 输出：knowledge/html/<模块名>.html
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const knowledgeDir = join(root, 'knowledge');
const htmlDir = join(knowledgeDir, 'html');
const indexPath = join(knowledgeDir, 'index.html');
const rewriteIndex = !process.argv.includes('--no-index');

/* ---------------------------------------------------------------- 工具 */

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const unesc = (s) => String(s)
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'").replace(/&amp;/g, '&');

function plainText(s) {
  return String(s)
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/(^|[\s（(【:：])\*([^*\n]+)\*/g, '$1$2')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ------------------------------------------------------- 清单：读 index.html */

function parseManifest(html) {
  const sections = [];
  const secRe = /<section class="sec module-section" id="([^"]+)" data-cat="([^"]+)">([\s\S]*?)\n      <\/section>/g;
  let sm;
  while ((sm = secRe.exec(html)) !== null) {
    const [, id, cat, inner] = sm;
    const num = (inner.match(/<div class="sec-num">([^<]*)<\/div>/) || [, ''])[1].trim();
    const title = unesc((inner.match(/<h2>([^<]*)<\/h2>/) || [, ''])[1].trim());
    const desc = unesc((inner.match(/<h2>[^<]*<\/h2>\s*<p>([\s\S]*?)<\/p>/) || [, ''])[1].trim());
    const mods = [];
    const cardRe = /<article class="card" id="([^"]+)" data-type="([^"]+)"[\s\S]*?<\/article>/g;
    let cm;
    while ((cm = cardRe.exec(inner)) !== null) {
      const block = cm[0];
      const kind = unesc((block.match(/<span class="kind">([^<]*)<\/span>/) || [, ''])[1].trim());
      const lines = unesc((block.match(/<span class="lines">([^<]*)<\/span>/) || [, ''])[1].trim());
      const h3 = block.match(/<h3><a href="([^"]+)">([\s\S]*?)<\/a><\/h3>/);
      const summary = unesc((block.match(/<h3>[\s\S]*?<\/h3>\s*<p>([\s\S]*?)<\/p>/) || [, ''])[1].trim());
      const tags = [...block.matchAll(/<span class="tag">([\s\S]*?)<\/span>/g)].map((t) => unesc(t[1].trim()));
      const foot = unesc((block.match(/<div class="card-foot"><span>([\s\S]*?)<\/span>/) || [, ''])[1].trim());
      if (!h3) throw new Error(`卡片缺少 h3 链接：${cm[1]}`);
      // 兼容已改写过的首页（href="html/x.html"）：还原为源 md 名
      let md = h3[1];
      if (/^html\/.+\.html$/.test(md)) md = md.slice('html/'.length).replace(/\.html$/, '.md');
      mods.push({
        id: cm[1],
        type: cm[2],
        md,
        html: md.replace(/\.md$/, '.html'),
        title: unesc(h3[2].trim()),
        kind,
        lines,
        summary,
        tags,
        foot,
      });
    }
    sections.push({ id, cat, num, title, desc, mods });
  }
  return sections;
}

/* ------------------------------------------------------------- 链接重写 */

function makeHrefMapper(mdSet) {
  return function mapHref(href) {
    if (/^(https?:|mailto:|#)/.test(href)) return href;
    const hashAt = href.indexOf('#');
    const path = hashAt === -1 ? href : href.slice(0, hashAt);
    const hash = hashAt === -1 ? '' : href.slice(hashAt);
    if (!path) return href;
    if (path.startsWith('../')) return '../../' + path.slice(3) + hash;
    const b = basename(path);
    if (/\.md$/i.test(path)) {
      return mdSet.has(b) ? b.replace(/\.md$/i, '.html') + hash : '../' + b + hash;
    }
    return path + hash;
  };
}

/* ------------------------------------------------------------- 行内解析 */

function inline(text, mapHref) {
  const codes = [];
  let s = String(text).replace(/`([^`]+)`/g, (_, c) => {
    codes.push(c);
    return `\u0000${codes.length - 1}\u0000`;
  });
  s = esc(s);
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, h) => {
    const href = esc(mapHref(unesc(h)));
    const ext = /^https?:/.test(href) ? ' target="_blank" rel="noopener"' : '';
    return `<a href="${href}"${ext}>${t}</a>`;
  });
  s = s.replace(/(^|[\s（(【>：:])(https?:\/\/[^\s<）)】。，；]+)/g, (_, p, u) => {
    const trimmed = u.replace(/[。，；、）)]+$/, '');
    return `${p}<a href="${trimmed}" target="_blank" rel="noopener">${trimmed}</a>${u.slice(trimmed.length)}`;
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|[\s（(【:：])\*([^*\n]+)\*(?=$|[\s）)】。，；：！？.,;:!?])/g, '$1<em>$2</em>');
  s = s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[Number(i)])}</code>`);
  return s;
}

/* ------------------------------------------------------------- 块级解析 */

function splitCells(line) {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1);
  const out = [];
  let cur = '';
  let inCode = false;
  for (const ch of s) {
    if (ch === '`') { inCode = !inCode; cur += ch; continue; }
    if (ch === '|' && !inCode) { out.push(cur.trim()); cur = ''; continue; }
    cur += ch;
  }
  out.push(cur.trim());
  return out;
}

const isDelimRow = (l) => typeof l === 'string' && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l) && l.includes('-');

function alignOf(cell) {
  const t = cell.trim();
  if (/^:.*:$/.test(t)) return 'center';
  if (/:$/.test(t)) return 'right';
  if (/^:/.test(t)) return 'left';
  return null;
}

const LIST_RE = /^(\s*)([-+]|\d+\.)\s+(.*)$/;

function parseList(lines, start) {
  const items = [];
  let j = start;
  while (j < lines.length) {
    const l = lines[j];
    if (l.trim() === '') {
      const nxt = lines[j + 1];
      if (nxt !== undefined && (LIST_RE.test(nxt) || /^\s{2,}\S/.test(nxt))) { j += 1; continue; }
      break;
    }
    const m = l.match(LIST_RE);
    if (m) {
      items.push({ indent: m[1].replace(/\t/g, '  ').length, ordered: /^\d/.test(m[2]), text: [m[3]] });
      j += 1;
      continue;
    }
    if (/^\s{2,}\S/.test(l) && items.length) { items[items.length - 1].text.push(l.trim()); j += 1; continue; }
    break;
  }
  return { items, next: j };
}

function renderList(items, mapHref) {
  if (!items.length) return '';
  const base = Math.min(...items.map((i) => i.indent));
  const tag = items.find((i) => i.indent === base)?.ordered ? 'ol' : 'ul';
  let out = `<${tag}>`;
  let k = 0;
  while (k < items.length) {
    if (items[k].indent > base) { k += 1; continue; }
    const text = inline(items[k].text.join(' '), mapHref);
    k += 1;
    const kids = [];
    while (k < items.length && items[k].indent > base) { kids.push(items[k]); k += 1; }
    out += `<li>${text}${kids.length ? renderList(kids, mapHref) : ''}</li>`;
  }
  return `${out}</${tag}>`;
}

function convert(md, mapHref) {
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  const headings = [];
  let h1 = '';
  let i = 0;
  let seq = 0;
  let seenBlock = false;
  let headNoteUsed = false;
  let tableCount = 0;
  let codeCount = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*```/.test(line)) {
      const buf = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i += 1; }
      i += 1;
      codeCount += 1;
      out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`);
      seenBlock = true;
      continue;
    }

    if (line.trim() === '') { i += 1; continue; }

    if (/^\s*([-*_])\s*\1\s*\1[\s-*_]*$/.test(line)) {
      out.push('<hr>');
      i += 1;
      seenBlock = true;
      continue;
    }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const level = h[1].length;
      const text = h[2].replace(/\s+#+\s*$/, '').trim();
      if (level === 1 && !h1) { h1 = text; i += 1; continue; }
      if (level === 1) { out.push(`<h2>${inline(text, mapHref)}</h2>`); i += 1; seenBlock = true; continue; }
      const id = `s${(seq += 1)}`;
      headings.push({ level: Math.min(level, 4), id, text: plainText(text) });
      out.push(`<h${Math.min(level, 4)} id="${id}">${inline(text, mapHref)}</h${Math.min(level, 4)}>`);
      i += 1;
      seenBlock = true;
      continue;
    }

    if (/^>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>/.test(lines[i])) {
        buf.push(lines[i].replace(/^>\s?/, ''));
        i += 1;
      }
      const isHead = !seenBlock && !headNoteUsed;
      if (isHead) headNoteUsed = true;
      const body = buf.filter((l) => l.trim() !== '').map((l) => `<p>${inline(l, mapHref)}</p>`).join('');
      out.push(`<aside class="${isHead ? 'note note-head' : 'note'}">${body}</aside>`);
      seenBlock = true;
      continue;
    }

    if (/^\s*\|/.test(line) && isDelimRow(lines[i + 1])) {
      const header = splitCells(line);
      const align = splitCells(lines[i + 1]).map(alignOf);
      const rows = [];
      let j = i + 2;
      while (j < lines.length && /^\s*\|/.test(lines[j]) && lines[j].trim() !== '') { rows.push(splitCells(lines[j])); j += 1; }
      const cell = (tag, val, k) => {
        const a = align[k];
        const style = a && a !== 'left' ? ` style="text-align:${a}"` : '';
        return `<${tag}${style}>${inline(val, mapHref)}</${tag}>`;
      };
      let html = '<div class="table-wrap"><table><thead><tr>';
      header.forEach((c, k) => { html += cell('th', c, k); });
      html += '</tr></thead><tbody>';
      rows.forEach((r) => {
        html += '<tr>';
        for (let k = 0; k < header.length; k += 1) html += cell('td', r[k] ?? '', k);
        html += '</tr>';
      });
      html += '</tbody></table></div>';
      out.push(html);
      tableCount += 1;
      i = j;
      seenBlock = true;
      continue;
    }

    if (LIST_RE.test(line)) {
      const { items, next } = parseList(lines, i);
      out.push(renderList(items, mapHref));
      i = next;
      seenBlock = true;
      continue;
    }

    out.push(`<p>${inline(line, mapHref)}</p>`);
    i += 1;
    seenBlock = true;
  }

  return { h1, body: out.join('\n'), headings, tableCount, codeCount };
}

/* ------------------------------------------------------------- 页面模板 */

function readingTime(md) {
  const cjk = (md.match(/[\u3400-\u9fff\u3040-\u30ff]/g) || []).length;
  const words = (md.replace(/[\u3400-\u9fff\u3040-\u30ff]/g, ' ').match(/[A-Za-z0-9]+/g) || []).length;
  return Math.max(1, Math.round(cjk / 400 + words / 200));
}

function cutoffOf(md) {
  const head = md.split(/\r?\n/).slice(0, 12).join('\n');
  const m = head.match(/(?:数据截止|Data cutoff)\D{0,4}(\d{4}-\d{2}(?:-\d{2})?)/);
  return m ? m[1] : '';
}

function buildPage(doc, manifest, sections) {
  const sec = doc.section;
  const lang = /^INDEX_EN/i.test(doc.md) ? 'en' : 'zh-CN';
  const tocLevels = doc.headings.filter((h) => h.level <= 3);
  const useH3 = tocLevels.length <= 46;
  const toc = tocLevels.filter((h) => (useH3 ? true : h.level === 2));
  const cutoff = cutoffOf(doc.raw);
  const minutes = readingTime(doc.raw);
  const chars = (doc.raw.replace(/\s/g, '').length / 1000).toFixed(1);

  const tocItems = toc.map((h) => `<li class="lv${h.level}"><a href="#${h.id}">${h.text}</a></li>`).join('\n            ');
  const tocMobile = toc.map((h) => `<li class="lv${h.level}"><a href="#${h.id}">${h.text}</a></li>`).join('\n            ');

  const sideList = sec.mods.map((m) => `<li${m.md === doc.md ? ' class="on"' : ''}><a href="${m.html}">${esc(m.title)}</a></li>`).join('\n              ');
  const others = sections.filter((s) => s.id !== sec.id).map((s) => `<li><a href="../index.html#${s.id}"><b>${esc(s.num.split('/')[0].trim())}</b>${esc(s.title)}</a></li>`).join('\n              ');

  const idx = manifest.indexOf(doc);
  const prev = manifest[idx - 1];
  const next = manifest[idx + 1];
  const pager = [
    prev ? `<a class="prev" href="${prev.html}"><span class="dir">← 上一篇</span><span class="ttl">${esc(prev.title)}</span></a>` : '<span class="spacer"></span>',
    next ? `<a class="next" href="${next.html}"><span class="dir">下一篇 →</span><span class="ttl">${esc(next.title)}</span></a>` : '<span class="spacer"></span>',
  ].join('\n          ');

  const meta = [
    doc.lines ? `<span>${esc(doc.lines)}</span>` : '',
    `<span>约 ${chars}k 字</span>`,
    `<span>阅读约 ${minutes} 分钟</span>`,
    `<span>${toc.filter((h) => h.level === 2).length} 节</span>`,
    cutoff ? `<span>数据截止 ${esc(cutoff)}</span>` : '',
  ].filter(Boolean).join('');

  return `<!doctype html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>${esc(doc.title)} | energy-skills 知识库</title>
<meta name="description" content="${esc(doc.summary)}">
<link rel="stylesheet" href="../assets/knowledge.css">
</head>
<body data-cat="${esc(sec.cat)}" id="top">
<div class="progress" id="progress"></div>
<div class="scrim"></div>

<header class="topbar">
  <a class="back" href="../index.html">← 知识库</a>
  <div class="crumb">
    <span class="crumb-cat">${esc(sec.num)}</span>
    <span class="crumb-sep">/</span>
    <span class="crumb-doc">${esc(doc.title)}</span>
  </div>
  <div class="topbar-act">
    <a class="src" href="../${doc.md}">.md 源文件</a>
    <button class="toc-toggle" type="button" id="navToggle" aria-expanded="false" aria-controls="nav">目录</button>
  </div>
</header>

<div class="shell">
  <aside class="sidebar" id="nav">
    <div class="nav-kicker">当前分类</div>
    <div class="nav-num">${esc(sec.num)}</div>
    <h2 class="nav-cat"><a href="../index.html#${esc(sec.id)}">${esc(sec.title)}</a></h2>
    <ul class="nav-list">
              ${sideList}
    </ul>
    <div class="nav-others">
      <div class="nav-kicker">其他分类</div>
      <ul>
              ${others}
      </ul>
    </div>
  </aside>

  <main class="main" id="main">
    <header class="doc-head">
      <div class="kicker">${esc(sec.num)}<i>${esc(doc.kind)}</i></div>
      <h1 class="doc-title">${esc(doc.h1 || doc.title)}</h1>
      <p class="lede">${esc(doc.summary)}</p>
      ${doc.foot ? `<p class="hook">${esc(doc.foot)}</p>` : ''}
      ${doc.tags.length ? `<div class="tags">${doc.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
      <div class="doc-meta">${meta}</div>
    </header>

    ${toc.length ? `<details class="toc-mobile">
      <summary>本页目录（${toc.length}）</summary>
      <ol>
            ${tocMobile}
      </ol>
    </details>` : ''}

    <article class="prose">
${doc.body}
    </article>

    <nav class="pager" aria-label="上下篇">
          ${pager}
    </nav>

    <footer class="doc-foot">
      <div class="lic">本页由 <a href="../${doc.md}">knowledge/${esc(doc.md)}</a> 构建，内容与源文件同步；若两者不一致，以 .md 为准。除另有说明外，算例均为合成数据。</div>
      <div><a href="../index.html">返回知识库总览 →</a></div>
    </footer>
  </main>

  <aside class="toc">
    <div class="toc-title">本页目录</div>
    ${toc.length ? `<ol>
            ${tocItems}
    </ol>` : '<div class="toc-empty">本文无分节标题</div>'}
  </aside>
</div>

<a class="to-top" href="#top" aria-label="回到顶部">↑</a>
<script src="../assets/doc.js"></script>
</body>
</html>
`;
}

/* ---------------------------------------------------------------- 主流程 */

const indexHtml = readFileSync(indexPath, 'utf8');
const sections = parseManifest(indexHtml);
const manifest = sections.flatMap((s) => s.mods.map((m) => ({ ...m, section: s })));

if (!manifest.length) throw new Error('未从 index.html 解析到任何模块卡片');

const mdSet = new Set(manifest.map((m) => m.md));
const mapHref = makeHrefMapper(mdSet);

mkdirSync(htmlDir, { recursive: true });

const onDisk = new Set(readdirSync(knowledgeDir).filter((f) => f.endsWith('.md')));
const missing = manifest.filter((m) => !onDisk.has(m.md)).map((m) => m.md);
const orphan = [...onDisk].filter((f) => !mdSet.has(f));
if (missing.length) throw new Error(`清单指向的 md 不存在：${missing.join('、')}`);

let totalHeadings = 0;
const report = [];
for (const doc of manifest) {
  const raw = readFileSync(join(knowledgeDir, doc.md), 'utf8');
  const { h1, body, headings, tableCount, codeCount } = convert(raw, mapHref);
  const page = buildPage({ ...doc, raw, h1, body, headings }, manifest, sections);
  writeFileSync(join(htmlDir, doc.html), page, 'utf8');
  totalHeadings += headings.length;
  report.push({ md: doc.md, html: doc.html, headings: headings.length, tableCount, codeCount, kb: Math.round(page.length / 1024) });
}

if (rewriteIndex) {
  let out = indexHtml;
  for (const m of manifest) {
    out = out.split(`href="${m.md}"`).join(`href="html/${m.html}"`);
  }
  out = out.split('阅读原文 →').join('进入模块 →');
  if (out !== indexHtml) writeFileSync(indexPath, out, 'utf8');
  else console.log('index.html 无需改写（链接已指向 html/）');
}

console.log(`已生成 ${report.length} 个内容页 → knowledge/html/`);
console.log(`章节标题合计 ${totalHeadings}，表格 ${report.reduce((a, r) => a + r.tableCount, 0)} 张，代码/图块 ${report.reduce((a, r) => a + r.codeCount, 0)} 个`);
if (orphan.length) console.log(`提示：knowledge/ 下未被首页收录的 md：${orphan.join('、')}`);
const biggest = [...report].sort((a, b) => b.kb - a.kb).slice(0, 3);
console.log(`最大页面：${biggest.map((b) => `${b.html} ${b.kb}KB`).join('，')}`);
