#!/usr/bin/env node
/**
 * 知识中心构建器。
 *
 * 单一事实源：
 *   knowledge/*.md 的 frontmatter（id、section、order、level、title、summary、tags、cutoff、related、search、foot）
 *   scripts/knowledge.config.mjs（分区、导航、固定文案）
 *   knowledge/index.template.html（首页静态骨架）
 *
 * 用法：
 *   node scripts/build-knowledge-html.mjs            # 生成 index.html 与 knowledge/html/*.html
 *   node scripts/build-knowledge-html.mjs --check    # 只校验生成物是否最新，不写文件
 *   node scripts/build-knowledge-html.mjs --no-index # 只生成内容页，不覆盖首页
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { nav, sections, site } from './knowledge.config.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const knowledgeDir = join(root, 'knowledge');
const htmlDir = join(knowledgeDir, 'html');
const indexPath = join(knowledgeDir, 'index.html');
const templatePath = join(knowledgeDir, 'index.template.html');
const checkMode = process.argv.includes('--check');
const rewriteIndex = !process.argv.includes('--no-index') && !checkMode;

/* ---------------------------------------------------------------- 工具 */

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const unesc = (s) => String(s)
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const fmt = (n) => n.toLocaleString('en-US');

function plainText(s) {
  return String(s)
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/(^|[\s（(【:：])\*([^*\n]+)\*/g, '$1$2')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
function cnNum(n) {
  if (n === 2) return '两';
  if (n <= 9) return CN_DIGITS[n];
  if (n === 10) return '十';
  if (n < 20) return `十${CN_DIGITS[n - 10]}`;
  return String(n);
}

function countLines(text) {
  if (!text) return 0;
  const breaks = (text.match(/\n/g) || []).length;
  return text.endsWith('\n') ? breaks : breaks + 1;
}

/* ------------------------------------------------------------ frontmatter */

const REQUIRED = ['id', 'section', 'order', 'level', 'kind', 'title', 'summary', 'tags', 'foot'];
const LEVELS = new Set(['core', 'research', 'tool']);

function parseDoc(raw, file) {
  const normalized = raw.replace(/\r\n?/g, '\n');
  if (!normalized.startsWith('---\n')) throw new Error(`${file}: 缺少 frontmatter（文件必须以 --- 开头）`);
  const end = normalized.indexOf('\n---\n', 4);
  if (end === -1) throw new Error(`${file}: frontmatter 未闭合`);
  const fm = normalized.slice(4, end);
  const body = normalized.slice(end + 5);
  const data = {};
  let key = null;
  for (const line of fm.split('\n')) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    if (key && /^\s+/.test(line)) { data[key] += ' ' + line.trim(); continue; }
    const at = line.indexOf(':');
    if (at === -1) throw new Error(`${file}: frontmatter 行无法解析 -> ${line}`);
    key = line.slice(0, at).trim();
    let value = line.slice(at + 1).trim();
    if (value.startsWith('[') || value.startsWith('"')) {
      try { value = JSON.parse(value); } catch { throw new Error(`${file}: ${key} 需要是 JSON 数组或字符串`); }
    }
    data[key] = value;
  }
  for (const field of REQUIRED) {
    if (data[field] === undefined || data[field] === '') throw new Error(`${file}: frontmatter 缺少 ${field}`);
  }
  if (!Array.isArray(data.tags)) throw new Error(`${file}: tags 需要是数组`);
  if (!Array.isArray(data.related)) throw new Error(`${file}: related 需要是数组`);
  if (!LEVELS.has(data.level)) throw new Error(`${file}: level 必须是 core / research / tool`);
  if (!/^\d+$/.test(String(data.order))) throw new Error(`${file}: order 必须是整数`);
  return { data, body, lines: countLines(body) };
}

function cutoffOf(text) {
  const head = text.split('\n').slice(0, 30).join('\n');
  const m = head.match(/(?:数据截止|Data cutoff)\D{0,6}(\d{4}-\d{2}(?:-\d{2})?)/);
  return m ? m[1] : '';
}

/* --------------------------------------------------------------- 模块清单 */

const sectionById = new Map(sections.map((s) => [s.id, s]));
if (sectionById.size !== sections.length) throw new Error('knowledge.config.mjs: section id 重复');

const files = readdirSync(knowledgeDir).filter((f) => f.endsWith('.md')).sort();
const docs = files.map((md) => {
  const raw = readFileSync(join(knowledgeDir, md), 'utf8');
  const { data, body, lines } = parseDoc(raw, md);
  const section = sectionById.get(data.section);
  if (!section) throw new Error(`${md}: section "${data.section}" 未在 knowledge.config.mjs 中定义`);
  return {
    ...data,
    md,
    html: md.replace(/\.md$/, '.html'),
    order: Number(data.order),
    body,
    raw: body,
    lines,
  };
});

const ids = new Map();
for (const doc of docs) {
  if (ids.has(doc.id)) throw new Error(`id 重复：${doc.id}（${ids.get(doc.id)} 与 ${doc.md}）`);
  ids.set(doc.id, doc.md);
}
for (const doc of docs) {
  for (const rel of doc.related) {
    if (!ids.has(rel)) throw new Error(`${doc.md}: related 指向不存在的模块 ${rel}`);
    if (rel === doc.id) throw new Error(`${doc.md}: related 不能指向自己`);
  }
}

const manifest = sections.flatMap((section) => docs
  .filter((d) => d.section === section.id)
  .sort((a, b) => a.order - b.order || a.md.localeCompare(b.md, 'zh')));
if (manifest.length !== docs.length) throw new Error('存在未归入任何分区的模块');
for (const section of sections) {
  if (!manifest.some((d) => d.section === section.id)) throw new Error(`分区 ${section.id} 没有任何模块`);
}

const byId = new Map(manifest.map((d) => [d.id, d]));
const total = manifest.length;
const totalLines = manifest.reduce((sum, d) => sum + d.lines, 0);
const coreCount = manifest.filter((d) => d.level === 'core').length;
const researchCount = manifest.filter((d) => d.level === 'research').length;
const cutoff = manifest.map((d) => d.cutoff || '').filter((d) => /^\d{4}-\d{2}/.test(d)).sort().at(-1) || '';

/* ------------------------------------------------------------- 链接重写 */

const mdSet = new Set(docs.map((d) => d.md));

function makeHrefMapper() {
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

const mapHref = makeHrefMapper();

/* ------------------------------------------------------------- 行内解析 */

function inline(text) {
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

function renderList(items) {
  if (!items.length) return '';
  const base = Math.min(...items.map((i) => i.indent));
  const tag = items.find((i) => i.indent === base)?.ordered ? 'ol' : 'ul';
  let out = `<${tag}>`;
  let k = 0;
  while (k < items.length) {
    if (items[k].indent > base) { k += 1; continue; }
    const text = inline(items[k].text.join(' '));
    k += 1;
    const kids = [];
    while (k < items.length && items[k].indent > base) { kids.push(items[k]); k += 1; }
    out += `<li>${text}${kids.length ? renderList(kids) : ''}</li>`;
  }
  return `${out}</${tag}>`;
}

function convert(md) {
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  const headings = [];
  let h1 = '';
  let i = 0;
  let seq = 0;
  let seenBlock = false;
  let headNoteUsed = false;
  let lastBlock = '';
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
      lastBlock = 'code';
      continue;
    }

    if (line.trim() === '') { i += 1; continue; }

    if (/^\s*([-*_])\s*\1\s*\1[\s-*_]*$/.test(line)) {
      out.push('<hr>');
      i += 1;
      seenBlock = true;
      lastBlock = 'hr';
      continue;
    }

    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const level = h[1].length;
      const text = h[2].replace(/\s+#+\s*$/, '').trim();
      if (level === 1 && !h1) { h1 = text; i += 1; continue; }
      if (level === 1) { out.push(`<h2>${inline(text)}</h2>`); i += 1; seenBlock = true; lastBlock = 'heading'; continue; }
      const id = `s${(seq += 1)}`;
      headings.push({ level: Math.min(level, 4), id, text: plainText(text) });
      out.push(`<h${Math.min(level, 4)} id="${id}">${inline(text)}</h${Math.min(level, 4)}>`);
      i += 1;
      seenBlock = true;
      lastBlock = 'heading';
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
      const body = buf.filter((l) => l.trim() !== '').map((l) => `<p>${inline(l)}</p>`).join('');
      if (isHead) {
        out.push(`<aside class="note note-head">${body}</aside>`);
      } else if (lastBlock === 'headnote') {
        out[out.length - 1] = out[out.length - 1].replace(/<\/aside>$/, `${body}</aside>`);
      } else {
        out.push(`<aside class="note">${body}</aside>`);
      }
      lastBlock = (isHead || lastBlock === 'headnote') ? 'headnote' : 'note';
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
        return `<${tag}${style}>${inline(val)}</${tag}>`;
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
      lastBlock = 'table';
      continue;
    }

    if (LIST_RE.test(line)) {
      const { items, next } = parseList(lines, i);
      out.push(renderList(items));
      i = next;
      seenBlock = true;
      lastBlock = 'list';
      continue;
    }

    out.push(`<p>${inline(line)}</p>`);
    i += 1;
    seenBlock = true;
    lastBlock = 'p';
  }

  return { h1, body: out.join('\n'), headings, tableCount, codeCount };
}

/* ----------------------------------------------------------- 首页渲染 */

function renderSidebarNav() {
  const counts = new Map();
  for (const d of manifest) counts.set(d.section, (counts.get(d.section) || 0) + 1);
  return nav.map((item) => {
    const count = item.count === 'total' ? total
      : item.count === 'section' ? counts.get(item.section) || 0
        : item.count === 'skills' ? site.skills
          : item.count;
    const active = item.href === '#top' ? ' class="active"' : '';
    return `      <a href="${item.href}"${active}><span class="n">${item.n}</span><span>${esc(item.label)}</span><span class="count">${count}</span></a>`;
  }).join('\n');
}

function renderCard(doc) {
  const href = `html/${doc.html}`;
  const search = [doc.search, ...doc.tags.filter((t) => !String(doc.search || '').includes(t))].filter(Boolean).join(' ');
  return `          <article class="card" id="${esc(doc.id)}" data-type="${esc(doc.level)}" data-search="${esc(search)}">
            <div class="card-top"><span class="kind">${esc(doc.kind)}</span><span class="lines">${fmt(doc.lines)} 行</span></div>
            <h3><a href="${href}">${esc(doc.title)}</a></h3>
            <p>${esc(doc.summary)}</p>
            <div class="tags">${doc.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>
            <div class="card-foot"><span>${esc(doc.foot)}</span><a href="${href}">进入模块 →</a></div>
          </article>`;
}

function renderModuleSections() {
  const blocks = sections.map((section) => {
    const mods = manifest.filter((d) => d.section === section.id);
    const desc = section.desc.replace('{n}', cnNum(mods.length));
    return `      <!-- ${section.comment} -->
      <section class="sec module-section" id="${section.id}" data-cat="${section.cat}">
        <div class="sec-head">
          <div class="sec-num">${section.num}</div>
          <div>
            <h2>${esc(section.title)}</h2>
            <p>${esc(desc)}</p>
          </div>
        </div>
        <div class="cards">
${mods.map(renderCard).join('\n')}
        </div>
      </section>`;
  });
  return blocks.join('\n\n');
}

function renderIndex() {
  const template = readFileSync(templatePath, 'utf8').replace(/\r\n?/g, '\n');
  const tokens = {
    metaDescription: `energy-skills 知识库总览：${total} 个模块，覆盖${site.coverage}。数据截止 ${cutoff}。`,
    brandLine: `${total} 个模块 · ${fmt(totalLines)} 行<br>数据截止 ${cutoff}`,
    sidebarNav: renderSidebarNav(),
    heroEyebrow: `Knowledge Hub · ${cutoff} · ${total} 模块 / ${fmt(totalLines)} 行`,
    heroLede: `把 ${total} 份主题笔记、政策索引与调研底稿，收进一张可检索、可跳转的知识地图。每个模块都有对应的 HTML 阅读页，文字与数字取自 Markdown 原文。`,
    heroStats: `
              <div class="stat"><b>${total}</b><span>知识模块</span></div>
              <div class="stat"><b>${coreCount}</b><span>核心模块</span></div>
              <div class="stat"><b>${researchCount}</b><span>调研底稿</span></div>
              <div class="stat"><b>${site.skills}</b><span>配套技能</span></div>
            `,
    resultDefault: `${total} / ${total} 个模块`,
    moduleSections: renderModuleSections(),
    footerLine: `数据截止 ${cutoff} · ${total} 个模块 / ${fmt(totalLines)} 行 · ${cnNum(site.skills)}项技能`,
  };
  let out = template;
  for (const [key, value] of Object.entries(tokens)) {
    out = out.split(`{{${key}}}`).join(value);
  }
  const left = out.match(/\{\{[a-zA-Z]+\}\}/g);
  if (left) throw new Error(`首页模板存在未替换的占位符：${[...new Set(left)].join('、')}`);

  const anchors = new Set();
  for (const m of out.matchAll(/href="#(m-[^"]+)"/g)) anchors.add(m[1]);
  const broken = [...anchors].filter((id) => !byId.has(id));
  if (broken.length) throw new Error(`首页锚点指向不存在的模块：${broken.join('、')}`);
  return out;
}

/* ------------------------------------------------------------- 页面模板 */

function readingTime(md) {
  const cjk = (md.match(/[\u3400-\u9fff\u3040-\u30ff]/g) || []).length;
  const words = (md.replace(/[\u3400-\u9fff\u3040-\u30ff]/g, ' ').match(/[A-Za-z0-9]+/g) || []).length;
  return Math.max(1, Math.round(cjk / 400 + words / 200));
}

function buildPage(doc) {
  const sec = sectionById.get(doc.section);
  const lang = /^INDEX_EN/i.test(doc.md) ? 'en' : 'zh-CN';
  const h2s = doc.headings.filter((h) => h.level === 2);
  const h3s = doc.headings.filter((h) => h.level === 3);
  const toc = h2s.length ? h2s : doc.headings.filter((h) => h.level <= 3).slice(0, 12);
  const tocAll = h2s.length ? doc.headings.filter((h) => h.level === 2 || h.level === 3) : toc;
  const pageCutoff = cutoffOf(doc.raw) || doc.cutoff || '';
  const minutes = readingTime(doc.raw);
  const chars = (doc.raw.replace(/\s/g, '').length / 1000).toFixed(1);

  const tocItems = tocAll.map((h) => `<li class="lv${h.level}"><a href="#${h.id}">${h.text}</a></li>`).join('\n            ');
  const tocMobile = toc.map((h) => `<li class="lv${h.level}"><a href="#${h.id}">${h.text}</a></li>`).join('\n            ');
  const tocMore = h3s.length
    ? `<button class="toc-more" type="button" aria-expanded="false" data-count="${h3s.length}">展开 ${h3s.length} 个小节</button>`
    : '';

  const sideList = manifest.filter((m) => m.section === sec.id)
    .map((m) => `<li${m.id === doc.id ? ' class="on" aria-current="page"' : ''}><a href="${m.html}">${esc(m.title)}</a></li>`).join('\n              ');
  const others = sections.filter((s) => s.id !== sec.id)
    .map((s) => `<li><a href="../index.html#${s.id}"><b>${esc(s.num.split('/')[0].trim())}</b>${esc(s.title)}</a></li>`).join('\n              ');

  const idx = manifest.findIndex((d) => d.id === doc.id);
  const prev = manifest[idx - 1];
  const next = manifest[idx + 1];
  const pager = [
    prev ? `<a class="prev" href="${prev.html}"><span class="dir">← 上一篇</span><span class="ttl">${esc(prev.title)}</span></a>` : '<span class="spacer"></span>',
    next ? `<a class="next" href="${next.html}"><span class="dir">下一篇 →</span><span class="ttl">${esc(next.title)}</span></a>` : '<span class="spacer"></span>',
  ].join('\n          ');

  const related = doc.related.map((id) => byId.get(id));
  const relatedBlock = related.length ? `<section class="related" aria-label="相关模块">
      <h2>相关模块</h2>
      <ul>
        ${related.map((r) => `<li><a href="${r.html}">${esc(r.title)}</a></li>`).join('\n        ')}
      </ul>
    </section>` : '';

  const meta = [
    `<span>${fmt(doc.lines)} 行</span>`,
    `<span>约 ${chars}k 字</span>`,
    `<span>阅读约 ${minutes} 分钟</span>`,
    `<span>${toc.length} 节</span>`,
    pageCutoff ? `<span>数据截止 ${esc(pageCutoff)}</span>` : '',
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
<a class="skip" href="#main">跳到正文</a>
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

    ${relatedBlock}

    <nav class="pager" aria-label="上下篇">
          ${pager}
    </nav>

    <footer class="doc-foot">
      <div class="lic">本页由 <a href="../${doc.md}">knowledge/${esc(doc.md)}</a> 构建，内容与源文件同步；若两者不一致，以 .md 为准。除另有说明外，算例均为合成数据。</div>
      <div><a href="../index.html">返回知识库总览 →</a></div>
    </footer>
  </main>

  <aside class="toc" aria-label="本页目录">
    <div class="toc-title">本页目录</div>
    ${tocAll.length ? `<ol>
            ${tocItems}
    </ol>${tocMore}` : '<div class="toc-empty">本文无分节标题</div>'}
  </aside>
</div>

<a class="to-top" href="#top" aria-label="回到顶部">↑</a>
<script src="../assets/doc.js"></script>
</body>
</html>
`;
}

/* ---------------------------------------------------------------- 主流程 */

if (!existsSync(templatePath)) throw new Error('缺少 knowledge/index.template.html');

mkdirSync(htmlDir, { recursive: true });

const pages = manifest.map((doc) => {
  const converted = convert(doc.body);
  const merged = { ...doc, ...converted };
  return { doc: merged, html: buildPage(merged) };
});

const indexHtml = renderIndex();

function verifyLinks(baseDir, html, label) {
  const missing = [];
  for (const m of html.matchAll(/href="([^"]+)"/g)) {
    const href = unesc(m[1]);
    if (/^(https?:|mailto:|#)/.test(href)) continue;
    const path = href.split('#')[0].split('?')[0];
    if (!path) continue;
    const target = resolve(baseDir, decodeURIComponent(path));
    if (!existsSync(target)) missing.push(href);
  }
  if (missing.length) throw new Error(`${label} 存在断链：${[...new Set(missing)].join('、')}`);
}

verifyLinks(knowledgeDir, indexHtml, 'knowledge/index.html');
for (const { doc, html } of pages) verifyLinks(htmlDir, html, `knowledge/html/${doc.html}`);

if (checkMode) {
  const diffs = [];
  const same = (path, expected) => existsSync(path) && readFileSync(path, 'utf8').replace(/\r\n?/g, '\n') === expected;
  if (!same(indexPath, indexHtml)) diffs.push('knowledge/index.html 不是最新生成物');
  for (const { doc, html } of pages) {
    if (!same(join(htmlDir, doc.html), html)) diffs.push(`knowledge/html/${doc.html} 不是最新生成物`);
  }
  const expected = new Set(pages.map((p) => p.doc.html));
  for (const f of readdirSync(htmlDir).filter((f) => f.endsWith('.html'))) {
    if (!expected.has(f)) diffs.push(`knowledge/html/${f} 已无对应 Markdown（删除或重新生成）`);
  }
  if (diffs.length) {
    console.error('生成物校验失败，请运行 node scripts/build-knowledge-html.mjs：');
    for (const d of diffs) console.error(`- ${d}`);
    process.exit(1);
  }
  console.log(`生成物校验通过：index.html + ${pages.length} 个内容页均为最新（${total} 个模块 / ${fmt(totalLines)} 行）。`);
  process.exit(0);
}

for (const { doc, html } of pages) writeFileSync(join(htmlDir, doc.html), html, 'utf8');
if (rewriteIndex) writeFileSync(indexPath, indexHtml, 'utf8');

const tables = pages.reduce((a, p) => a + p.doc.tableCount, 0);
const codes = pages.reduce((a, p) => a + p.doc.codeCount, 0);
const headings = pages.reduce((a, p) => a + p.doc.headings.length, 0);
console.log(`已生成 ${pages.length} 个内容页 → knowledge/html/`);
console.log(`模块 ${total} 个 / 正文 ${fmt(totalLines)} 行；章节 ${headings}，表格 ${tables}，代码/图块 ${codes}`);
if (rewriteIndex) console.log('已生成 knowledge/index.html（卡片、侧栏与计数来自 frontmatter）');
const biggest = [...pages].map((p) => ({ html: p.doc.html, kb: Math.round(p.html.length / 1024) })).sort((a, b) => b.kb - a.kb).slice(0, 3);
console.log(`最大页面：${biggest.map((b) => `${b.html} ${b.kb}KB`).join('，')}`);
