#!/usr/bin/env node
/**
 * 知识中心构建器。
 *
 * 单一事实源：
 *   knowledge/*.md 的 frontmatter（id、section、order、level、title、summary、tags、cutoff、related、search、foot，
 *     以及可信度声明 confidence / examples / historical）
 *   knowledge/*.md 里已有的结构化登记（快照 §5 C 级工单表、INDEX_EN §4 Open items、政策状态列、算例章节标题）
 *   scripts/knowledge.config.mjs（分区、导航、固定文案）
 *   knowledge/index.template.html（首页静态骨架）
 *
 * 生成物（禁止手改）：knowledge/index.html、knowledge/html/**、knowledge/credibility.json、
 *   knowledge/english-digest.json、knowledge/search-index.js
 *
 * 用法：
 *   node scripts/build-knowledge-html.mjs            # 生成 index.html 与 knowledge/html/*.html
 *   node scripts/build-knowledge-html.mjs --check    # 只校验生成物是否最新，不写文件
 *   node scripts/build-knowledge-html.mjs --no-index # 只生成内容页，不覆盖首页
 */
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { nav, sectionTitlesEn, sections, site, skillDocs } from './knowledge.config.mjs';
import { buildIndex, serializeIndex } from './credibility.mjs';
import { CURATED_ARCH_IDS, renderCuratedArchitecture } from './architecture-diagrams.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const knowledgeDir = join(root, 'knowledge');
const htmlDir = join(knowledgeDir, 'html');
const indexPath = join(knowledgeDir, 'index.html');
const credibilityPath = join(knowledgeDir, 'credibility.json');
const englishDigestPath = join(knowledgeDir, 'english-digest.json');
const searchIndexPath = join(knowledgeDir, 'search-index.js');
const templatePath = join(knowledgeDir, 'index.template.html');
const tokensPath = join(knowledgeDir, 'assets', 'tokens.css');
const checkMode = process.argv.includes('--check');
const rewriteIndex = !process.argv.includes('--no-index') && !checkMode;

if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(site.repository || '')) {
  throw new Error('knowledge.config.mjs: site.repository 必须是有效的 GitHub 仓库地址');
}

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
for (const meta of skillDocs) {
  if (!Array.isArray(meta.modules) || !meta.modules.length) throw new Error(`knowledge.config.mjs: 技能 ${meta.slug} 缺少 modules 关联`);
  for (const id of meta.modules) {
    if (!byId.has(id)) throw new Error(`knowledge.config.mjs: 技能 ${meta.slug} 关联了不存在的模块 ${id}`);
  }
}
const skillsByModuleId = new Map();
for (const meta of skillDocs) {
  for (const id of meta.modules) {
    if (!skillsByModuleId.has(id)) skillsByModuleId.set(id, []);
    skillsByModuleId.get(id).push(meta);
  }
}
const total = manifest.length;
const totalLines = manifest.reduce((sum, d) => sum + d.lines, 0);
const coreCount = manifest.filter((d) => d.level === 'core').length;
const researchCount = manifest.filter((d) => d.level === 'research').length;
const cutoff = manifest.map((d) => d.cutoff || '').filter((d) => /^\d{4}-\d{2}/.test(d)).sort().at(-1) || '';

/* --------------------------------------------------------------- 技能清单 */

const skillSection = { id: 'skill', cat: 'skill', num: '04 / SKILLS', title: '配套技能' };

if (!Array.isArray(skillDocs) || !skillDocs.length) throw new Error('knowledge.config.mjs: skillDocs 不能为空');
if (skillDocs.length !== site.skills) throw new Error(`skillDocs 有 ${skillDocs.length} 项，与 site.skills=${site.skills} 不一致`);

function stripFrontmatter(raw, file) {
  const normalized = raw.replace(/\r\n?/g, '\n');
  if (!normalized.startsWith('---\n')) return normalized;
  const end = normalized.indexOf('\n---\n', 4);
  if (end === -1) throw new Error(`${file}: frontmatter 未闭合`);
  return normalized.slice(end + 5);
}

const SKILL_FOOT = {
  zh: '可执行流程与配套工具；正文与 SKILL.md 同步。',
  en: 'Executable workflow and tools; synced with SKILL.md.',
};

const skillManifest = skillDocs.flatMap((meta) => {
  const variants = [
    { suffix: '', lang: 'zh-CN', file: 'SKILL.md', title: meta.title, summary: meta.summary, tags: meta.tags, foot: SKILL_FOOT.zh, kind: '技能' },
    { suffix: '-en', lang: 'en', file: 'SKILL_EN.md', title: meta.titleEn, summary: meta.summaryEn, tags: meta.tagsEn, foot: SKILL_FOOT.en, kind: 'Skill' },
  ];
  return variants.map((v) => {
    const rel = `skills/${meta.slug}/${v.file}`;
    const abs = join(root, rel);
    if (!existsSync(abs)) throw new Error(`缺少技能文件：${rel}`);
    const raw = readFileSync(abs, 'utf8').replace(/\r\n?/g, '\n');
    const body = stripFrontmatter(raw, rel);
    return {
      id: `skill-${meta.slug}${v.suffix}`,
      section: 'skill',
      order: meta.order,
      level: 'tool',
      kind: v.kind,
      title: v.title,
      summary: v.summary,
      tags: v.tags,
      foot: v.foot,
      related: [],
      modules: meta.modules,
      md: rel,
      srcHref: `../../${rel}`,
      html: `skill-${meta.slug}${v.suffix}.html`,
      download: `download/skills/skill-${meta.slug}${v.suffix}.txt`,
      downloadName: `${v.title}-SKILL.txt`,
      slug: meta.slug,
      lang: v.lang,
      hidden: v.lang === 'en',
      body,
      raw: body,
      txt: raw,
      lines: countLines(body),
      cutoff: cutoffOf(body),
    };
  });
});

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
let activeMapHref = mapHref;

function makeSkillHrefMapper(doc) {
  return function mapSkillHref(href) {
    if (/^(https?:|mailto:|#)/.test(href)) return href;
    const hashAt = href.indexOf('#');
    const path = hashAt === -1 ? href : href.slice(0, hashAt);
    const hash = hashAt === -1 ? '' : href.slice(hashAt);
    if (!path) return href;
    const clean = path.replace(/\\/g, '/');
    if (/\.md$/i.test(clean)) {
      const b = basename(clean);
      if (/^SKILL_EN\.md$/i.test(b)) return `skill-${doc.slug}-en.html${hash}`;
      if (/^SKILL\.md$/i.test(b)) {
        const sib = clean.match(/(?:^|\/)(?:\.\.\/)?([^/]+)\/SKILL(_EN)?\.md$/i);
        if (sib && sib[1] !== doc.slug) return `skill-${sib[1]}${sib[2] ? '-en' : ''}.html${hash}`;
        return `skill-${doc.slug}${sib?.[2] ? '-en' : ''}.html${hash}`;
      }
      const kn = clean.match(/(?:^|\/)knowledge\/([^/]+\.md)$/i) || (/^[^./][^/]*\.md$/i.test(clean) ? [null, clean] : null);
      if (kn) return `${kn[1].replace(/\.md$/i, '.html')}${hash}`;
    }
    if (/^\.\.\/\.\.\//.test(clean)) return clean + hash;
    if (/^\.\.\//.test(clean)) return `../../skills/${clean.slice(3)}${hash}`;
    return `../../skills/${doc.slug}/${clean}${hash}`;
  };
}

/* ------------------------------------------------------------- 行内解析 */

function inline(text) {
  const codes = [];
  let s = String(text).replace(/`([^`]+)`/g, (_, c) => {
    codes.push(c);
    return `\u0000${codes.length - 1}\u0000`;
  });
  s = esc(s);
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, t, h) => {
    const href = esc(activeMapHref(unesc(h)));
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

/* 长列表项的领起词加粗：只改善呈现，不改原文 */
function emphasizeLead(text) {
  if (text.length < 60 || text.includes('**')) return text;
  const idx = text.indexOf('：');
  if (idx < 2 || idx > 22) return text;
  const lead = text.slice(0, idx);
  if (/[。；，、？！%]/.test(lead) || /[\[\]*_`]/.test(lead)) return text;
  if (/^[\d\s./\-年月日]+$/.test(lead)) return text;
  return `**${lead}**${text.slice(idx)}`;
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

function renderList(items, options = {}) {
  if (!items.length) return '';
  const base = Math.min(...items.map((i) => i.indent));
  const tag = items.find((i) => i.indent === base)?.ordered ? 'ol' : 'ul';
  let out = `<${tag}>`;
  let k = 0;
  while (k < items.length) {
    if (items[k].indent > base) { k += 1; continue; }
    const raw = items[k].text.join(' ');
    const special = options.special ? options.special(raw) : null;
    if (special) {
      out += `<li class="list-figure">${special}</li>`;
      k += 1;
      continue;
    }
    const text = inline(emphasizeLead(raw));
    k += 1;
    const kids = [];
    while (k < items.length && items[k].indent > base) { kids.push(items[k]); k += 1; }
    out += `<li>${text}${kids.length ? renderList(kids) : ''}</li>`;
  }
  return `${out}</${tag}>`;
}

/* ------------------------------------------------------------ 政策列表 */

function policyGroupCounts(lines) {
  const counts = [];
  let cur = -1;
  for (const line of lines) {
    if (/^##\s+/.test(line)) { counts.push(0); cur += 1; continue; }
    if (cur >= 0 && /^\s*\|/.test(line) && !isDelimRow(line) && !/^\s*\|\s*文号\s*\|/.test(line)) counts[cur] += 1;
  }
  return counts;
}

const STATUS_BADGE = { 现行: 'ok', 即将施行: 'soon', 已被取代: 'old', 草案: 'draft', 参考: 'ref' };

function renderPolicyCard(row, cols) {
  const link = (row[cols.link] || '').match(/\[([^\]]+)\]\((https?:[^)]+)\)/);
  if (!link) throw new Error(`政策表行缺少官方原文链接：${row[cols.title] || row[0]}`);
  const status = (row[cols.status] || '').trim();
  const statusKey = status.replace(/[（(].*$/, '').trim() || '其他';
  const badge = STATUS_BADGE[statusKey] || 'ref';
  const no = (row[cols.no] || '').trim();
  const title = (row[cols.title] || '').trim();
  const note = (row[cols.note] || '').trim();
  const org = (row[cols.org] || '').trim();
  const date = (row[cols.date] || '').trim();
  const search = plainText([no, title, note, org, date, status].join(' ')).toLowerCase();
  const html = `<a class="policy" href="${esc(link[2])}" target="_blank" rel="noopener" data-status="${esc(statusKey)}" data-search="${esc(search)}">
  <span class="policy-body">
    <span class="policy-head"><span class="policy-no">${esc(no)}</span><span class="badge badge-${badge}">${esc(status)}</span></span>
    <span class="policy-title">${inline(title)}</span>
    ${note ? `<span class="policy-note">${inline(note)}</span>` : ''}
    <span class="policy-meta">${esc(org)}${org && date ? ' · ' : ''}${esc(date)}</span>
  </span>
  <span class="policy-go" aria-hidden="true">↗</span>
</a>`;
  return { html, status: statusKey };
}

function renderPolicyBar(policy) {
  const order = ['现行', '即将施行', '草案', '已被取代', '参考'];
  const chips = order.filter((k) => policy.stats[k])
    .map((k) => `<button class="pchip" type="button" data-status="${k}">${k}<b>${policy.stats[k]}</b></button>`)
    .join('');
  return `<div class="policy-bar" data-policy-bar>
      <div class="policy-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
        <input id="policySearch" type="search" placeholder="检索文号、标题、机关或关键词，例如：136 / 储能 / 发改委" autocomplete="off" aria-label="检索政策">
        <button type="button" class="policy-clear" id="policyClear" aria-label="清空检索" hidden>×</button>
      </div>
      <div class="policy-chips" role="group" aria-label="按状态筛选">
        <button class="pchip on" type="button" data-status="all">全部<b>${policy.count}</b></button>
        ${chips}
      </div>
      <p class="policy-count" id="policyCount" aria-live="polite">共 ${policy.count} 条 · 点击卡片查看官方原文</p>
    </div>`;
}

/* ------------------------------------------------------------ 结构图 */

const DIAGRAM_GLYPHS = /[─│┌┐└┘├┤┬┴┼→←↔▲▼◀▶]/;

function splitDiagramText(raw) {
  const text = String(raw || '').trim();
  let m = text.match(/^(.{1,32}?)[：:]\s*(.+)$/);
  if (m) return { title: m[1].trim(), detail: m[2].trim() };
  m = text.match(/^(.{1,24}?)\s*(?:→|⟶|──>|->)\s*(.+)$/);
  if (m) return { title: m[1].trim(), detail: m[2].trim() };
  m = text.match(/^(.{1,24}?)\s{2,}(.+)$/);
  if (m) return { title: m[1].trim(), detail: m[2].trim() };
  return { title: text.replace(/[：:]$/, '').trim(), detail: '' };
}

function renderTreeChildren(children) {
  if (!children.length) return '';
  return `<ul class="tree-children">${children.map((node) => `<li>
    <span class="tree-child-title">${inline(node.title)}</span>
    ${node.detail ? `<span class="tree-child-detail">${inline(node.detail)}</span>` : ''}
    ${renderTreeChildren(node.children)}
  </li>`).join('')}</ul>`;
}

function renderTreeDiagram(body, isEn) {
  const lines = body.split('\n').map((line) => line.replace(/\s+$/, '')).filter((line) => line.trim());
  const branches = lines.filter((line) => /[├└]/.test(line));
  if (branches.length < 2) return null;
  if (lines.some((line) => /[┌┐]/.test(line) || /[▲▼◀▶]/.test(line) || /─{3,}/.test(line))) return null;

  const groups = [];
  let current = null;
  for (const line of lines) {
    const m = line.match(/^([ \t│]*)([├└])(?:[─-]+)?\s*(.*)$/);
    if (!m) {
      current = { root: { ...splitDiagramText(line.trim()), children: [] }, flat: [] };
      groups.push(current);
      continue;
    }
    if (!current) {
      current = { root: { title: isEn ? 'Structure' : '结构一览', detail: '', children: [] }, flat: [] };
      groups.push(current);
    }
    const prefix = m[1].replace(/\t/g, '    ');
    current.flat.push({ rawLevel: Math.ceil(prefix.length / 4), ...splitDiagramText(m[3]), children: [] });
  }

  for (const group of groups) {
    if (!group.flat.length) continue;
    const min = Math.min(...group.flat.map((node) => node.rawLevel));
    for (const node of group.flat) node.level = node.rawLevel - min + 1;
    const stack = [{ level: 0, children: group.root.children }];
    for (const node of group.flat) {
      while (stack.length && stack[stack.length - 1].level >= node.level) stack.pop();
      const parent = stack[stack.length - 1] || stack[0];
      parent.children.push(node);
      stack.push(node);
    }
  }

  const treeGroups = groups.filter((group) => group.root.children.length);
  if (!treeGroups.length) return null;
  const notes = groups.filter((group) => !group.root.children.length)
    .map((group) => [group.root.title, group.root.detail].filter(Boolean).join('：'))
    .filter(Boolean);
  const renderCards = (nodes) => nodes.map((node, idx) => `<article class="tree-node">
    <div class="tree-node-head">
      <span class="tree-node-index" aria-hidden="true">${String(idx + 1).padStart(2, '0')}</span>
      <span class="tree-node-copy">
        <span class="tree-node-title">${inline(node.title)}</span>
        ${node.detail ? `<span class="tree-node-detail">${inline(node.detail)}</span>` : ''}
      </span>
    </div>
    ${renderTreeChildren(node.children)}
  </article>`).join('');

  const multi = treeGroups.length > 1;
  const main = treeGroups[0];
  const title = multi ? (isEn ? 'Structure overview' : '结构总览') : main.root.title;
  const detail = multi ? '' : main.root.detail;
  const branchCount = treeGroups.reduce((sum, group) => sum + group.root.children.length, 0);
  const meta = multi
    ? `${treeGroups.length} ${isEn ? 'parts' : '个部分'}`
    : `${branchCount} ${isEn ? (branchCount === 1 ? 'branch' : 'branches') : '个一级分支'}`;
  const grid = multi
    ? `<div class="tree-groups">${treeGroups.map((group, idx) => `<section class="tree-group">
      <div class="tree-group-head">
        <span class="tree-group-index" aria-hidden="true">${String(idx + 1).padStart(2, '0')}</span>
        <span class="tree-group-title">${inline(group.root.title)}</span>
        ${group.root.detail ? `<span class="tree-group-detail">${inline(group.root.detail)}</span>` : ''}
      </div>
      <div class="tree-grid">${renderCards(group.root.children)}</div>
    </section>`).join('')}</div>`
    : `<div class="tree-grid">${renderCards(main.root.children)}</div>`;

  return `<figure class="tree-diagram" aria-label="${esc(title)}${isEn ? ' structure map' : '结构图'}">
    <figcaption class="diagram-head">
      <span class="diagram-head-row">
        <span class="diagram-kicker">${isEn ? 'System map · STRUCTURE' : '结构图 · STRUCTURE'}</span>
        <span class="diagram-meta">${meta}</span>
      </span>
      <span class="tree-root-title">${inline(title)}</span>
      ${detail ? `<span class="tree-root-detail">${inline(detail)}</span>` : ''}
    </figcaption>
    ${grid}
    ${notes.length ? `<p class="diagram-note">${notes.map((note) => inline(note)).join('；')}</p>` : ''}
  </figure>`;
}

function renderFlowFigure(steps, isEn, note = '', options = {}) {
  const notes = (Array.isArray(note) ? note : String(note || '').split('；'))
    .map((item) => item.trim())
    .filter(Boolean);
  const variant = options.variant ? ` is-${options.variant}` : '';
  const title = options.title ? `<span class="diagram-title">${inline(options.title)}</span>` : '';
  return `<figure class="flow-diagram${variant}" aria-label="${esc(options.title || (isEn ? 'Process flow' : '流程示意'))}">
    <figcaption class="diagram-head">
      <span class="diagram-head-row">
        <span class="diagram-kicker">${esc(options.kicker || (isEn ? 'Step flow · FLOW' : '流程 · FLOW'))}</span>
        <span class="diagram-meta">${steps.length} ${isEn ? 'steps' : '个步骤'}</span>
      </span>
      ${title}
    </figcaption>
    <ol class="flow-steps">${steps.map((step, idx) => `<li>
      <span class="flow-index" aria-hidden="true">${String(idx + 1).padStart(2, '0')}</span>
      <span class="flow-text">${inline(step.title)}</span>
      ${step.points.length ? `<ul class="flow-points">${step.points.map((point) => `<li>${inline(point)}</li>`).join('')}</ul>` : ''}
    </li>`).join('')}</ol>
    ${notes.length ? `<div class="flow-note">${notes.map((item) => `<span class="flow-note-item">${inline(item)}</span>`).join('')}</div>` : ''}
  </figure>`;
}

function renderFlowDiagram(body, isEn) {
  const lines = body.split('\n').map((line) => line.trim()).filter(Boolean);
  if (lines.length !== 1) return null;
  const parts = lines[0].split(/\s*(?:→|⟶|──>|->)\s*/).map((part) => part.trim()).filter(Boolean);
  if (parts.length < 3) return null;
  return renderFlowFigure(parts.map((title) => ({ title, points: [] })), isEn);
}

function renderVerticalFlow(body, isEn) {
  if (/[┌┐└┘├┤┬┴┼─]/.test(body)) return null;
  const rawLines = body.split('\n').map((line) => line.trim()).filter(Boolean);
  if (rawLines.length < 3) return null;
  const arrowLead = rawLines.slice(1).every((line) => /^(?:→|⟶|──>|->)/.test(line));
  const hasDown = rawLines.some((line) => /^[│\s]*[↓▲▼]/.test(line));
  if (!arrowLead && !hasDown) return null;
  const arrowCount = (body.match(/[→⟶↓▲▼]/g) || []).length;
  if (arrowCount < 2) return null;

  const steps = [];
  let pending = [];
  const pushText = (text) => {
    const parts = text.split(/\s*(?:→|⟶|──>|->)\s*/).map((part) => part.trim()).filter(Boolean);
    for (const part of parts) {
      steps.push({ title: part, points: pending });
      pending = [];
    }
  };
  for (const line of rawLines) {
    if (/^[│\s]*[↓▲▼]\s*(.*)$/.test(line) || /^│/.test(line)) {
      const note = line.replace(/^[│\s]*[↓▲▼]?\s*/, '').replace(/^[│\s]+/, '').trim();
      if (note) pending.push(note);
      continue;
    }
    pushText(line.replace(/^(?:→|⟶|──>|->)\s*/, ''));
  }
  if (steps.length < 3) return null;
  return renderFlowFigure(steps, isEn, pending.join(' '));
}

function renderColumnFlow(body, isEn) {
  if (/[┌┐]/.test(body)) return null;
  const lines = body.split('\n').map((line) => line.trim()).filter(Boolean);
  if (lines.length < 3) return null;
  const head = lines[0].split(/\s{2,}/).map((part) => part.trim()).filter(Boolean);
  if (head.length < 3) return null;
  const pure = (line) => /^[\s│─┼┬┴┐┘└]+$/.test(line);
  const content = lines.slice(1).filter((line) => !pure(line));
  const rows = [];
  const notes = [];
  for (const line of content) {
    const cols = line.split(/\s{2,}/).map((part) => part.trim()).filter(Boolean);
    if (cols.length === head.length) rows.push(cols);
    else if (cols.length === 1) notes.push(cols[0]);
    else return null;
  }
  if (!rows.length) return null;
  const steps = head.map((title, idx) => ({
    title,
    points: rows.map((row) => row[idx]).filter(Boolean),
  }));
  const note = notes.join(' ')
    .replace(/^[└┌─\s]+/, '')
    .replace(/[─┘┐\s]+$/, '')
    .trim();
  return renderFlowFigure(steps, isEn, note);
}

function renderDiagramBlueprint(body, isEn) {
  const decorated = esc(body).replace(/[─│┌┐└┘├┤┬┴┼→←↔▲▼◀▶]/g, (char) => {
    const kind = /[→←↔▲▼◀▶]/.test(char) ? 'd-arrow' : 'd-line';
    return `<span class="${kind}">${char}</span>`;
  });
  return `<figure class="diagram-blueprint">
    <figcaption class="diagram-head">
      <span class="diagram-head-row">
        <span class="diagram-kicker">${isEn ? 'Schematic · DIAGRAM' : '结构示意 · DIAGRAM'}</span>
        <span class="diagram-meta">${isEn ? 'Scroll horizontally' : '可横向滚动'}</span>
      </span>
    </figcaption>
    <div class="diagram-canvas" tabindex="0" role="group" aria-label="${isEn ? 'Schematic diagram' : '结构示意图'}">
      <pre>${decorated}</pre>
    </div>
  </figure>`;
}

function renderAsciiDiagram(body, isEn) {
  if (!DIAGRAM_GLYPHS.test(body)) return null;
  const tree = renderTreeDiagram(body, isEn);
  if (tree) return tree;
  const columnFlow = renderColumnFlow(body, isEn);
  if (columnFlow) return columnFlow;
  const flow = renderFlowDiagram(body, isEn);
  if (flow) return flow;
  const verticalFlow = renderVerticalFlow(body, isEn);
  if (verticalFlow) return verticalFlow;
  return renderDiagramBlueprint(body, isEn);
}

/* ------------------------------------------------------------ 落地路径 */

function splitMilestoneText(raw) {
  const text = String(raw || '').trim();
  let m = text.match(/^(.{1,32}?)[：:]\s*(.+)$/);
  if (m) return { title: m[1].trim(), detail: m[2].trim() };
  m = text.match(/^(.{1,24}?)[，,]\s*(.+)$/);
  if (m) return { title: m[1].trim(), detail: m[2].trim() };
  return { title: text, detail: '' };
}

function renderMilestoneFigure(steps, kind, isEn) {
  const isGrid = kind === 'grid';
  return `<figure class="milestone-diagram" aria-label="${isEn ? (isGrid ? 'Grid connection milestones' : 'Market entry roadmap') : (isGrid ? '并网流程' : '市场进入路径')}">
    <figcaption class="diagram-head">
      <span class="diagram-head-row">
        <span class="diagram-kicker">${isEn ? (isGrid ? 'Grid connection · MILESTONES' : 'Market entry · ROADMAP') : (isGrid ? '并网流程 · MILESTONES' : '进入路径 · ROADMAP')}</span>
        <span class="diagram-meta">${steps.length} ${isEn ? 'steps' : '个步骤'}</span>
      </span>
    </figcaption>
    <ol class="milestone-list">${steps.map((step, idx) => `<li class="milestone-step">
      <span class="milestone-node" aria-hidden="true">${String(idx + 1).padStart(2, '0')}</span>
      <div class="milestone-card">
        <span class="milestone-title">${inline(step.title)}</span>
        ${step.detail ? `<span class="milestone-detail">${inline(step.detail)}</span>` : ''}
        ${step.tracks && step.tracks.length ? `<div class="milestone-tracks">${step.tracks.map((track) => `<div class="milestone-track"><span class="milestone-track-label">${inline(track.label)}</span><span>${inline(track.text)}</span></div>`).join('')}</div>` : ''}
        ${step.metaLabel && step.metaValue ? `<div class="milestone-meta" data-meta="${esc(step.metaLabel)}"><span class="milestone-meta-label">${inline(step.metaLabel)}</span><span>${inline(step.metaValue)}</span></div>` : ''}
      </div>
    </li>`).join('')}</ol>
  </figure>`;
}

function renderMilestoneTable(header, rows, isEn, kind) {
  if (header[0] !== '步骤' || rows.length < 3 || header.length < 2) return null;
  const isTrackTable = header.length === 3 && header[1] !== '内容';
  const steps = rows.map((row) => {
    let stepLabel = (row[0] || '').replace(/^\d+\s*[.、)）]?\s*/, '').trim();
    if (isTrackTable) {
      return {
        title: stepLabel || row[0],
        detail: '',
        tracks: [{ label: header[1], text: row[1] || '' }, { label: header[2], text: row[2] || '' }],
      };
    }
    const content = (row[1] || '').trim();
    const parsed = /^\d+$/.test(stepLabel) || !stepLabel ? splitMilestoneText(content) : { title: stepLabel, detail: content };
    return {
      title: parsed.title,
      detail: parsed.detail,
      metaLabel: header[2] || '',
      metaValue: row[2] || '',
    };
  });
  return renderMilestoneFigure(steps, kind, isEn);
}

function renderMilestoneList(items, isEn) {
  const steps = items.map((item) => {
    const parsed = splitMilestoneText(item.text.join(' '));
    return { title: parsed.title, detail: parsed.detail };
  });
  return renderMilestoneFigure(steps, 'entry', isEn);
}

/* ------------------------------------------------ 安全链 / 应急 / 状态 */

function renderInlineChain(raw, options, isEn) {
  const at = raw.search(/[：:]/);
  if (at < 0) return null;
  const parts = raw.slice(at + 1).trim().split(/\s*→\s*/).map((part) => part.trim()).filter(Boolean);
  if (parts.length < 3) return null;
  let note = '';
  let last = parts.pop();
  const tail = last.match(/^(.+?)[；。]\s*(.+)$/);
  if (tail) {
    last = tail[1].trim();
    note = tail[2].trim();
  } else {
    last = last.replace(/。\s*$/, '');
  }
  parts.push(last);
  return renderFlowFigure(parts.map((title) => ({ title, points: [] })), isEn, note, options);
}

function renderSpecialFlowItem(raw, h2, h3, isEn) {
  const plain = raw.replace(/\*\*/g, '').trim();
  if (/安全：从电芯到站级/.test(h2)) {
    if (/^链式反应[：:]/.test(plain)) {
      return renderInlineChain(raw, { title: '热失控链式反应', kicker: isEn ? 'Cause chain · CAUSE' : '因果链 · CAUSE', variant: 'chain' }, isEn);
    }
    if (/^传播路径[：:]/.test(plain)) {
      return renderInlineChain(raw, { title: '热蔓延路径', kicker: isEn ? 'Spread chain · SPREAD' : '传播链 · SPREAD', variant: 'chain' }, isEn);
    }
    if (/^处置顺序（原则）[：:]/.test(plain)) {
      return renderInlineChain(raw, { title: '应急处置顺序', kicker: isEn ? 'Emergency response · RESPONSE' : '应急流程 · RESPONSE' }, isEn);
    }
  }
  if (/核查实操/.test(h2) && /^三阶段八步[：:]/.test(plain)) {
    return renderInlineChain(raw, { title: '核查：三阶段八步', kicker: isEn ? 'Verification · PROCESS' : '核查流程 · PROCESS' }, isEn);
  }
  if (/CCER项目开发/.test(h2) && /^七步[：:]/.test(plain)) {
    return renderInlineChain(raw, { title: 'CCER 项目：七步', kicker: isEn ? 'Project cycle · PROCESS' : '项目流程 · PROCESS' }, isEn);
  }
  if (/碳资产管理与碳金融/.test(h2) && /^PAS 2060/.test(plain) && /[：:]/.test(plain)) {
    return renderInlineChain(raw, { title: 'PAS 2060：碳中和七步', kicker: isEn ? 'Carbon neutrality · PATHWAY' : '碳中和路径 · PATHWAY' }, isEn);
  }
  return null;
}

function renderStateTable(header, rows, isEn) {
  if (header[0] !== '阶段' || header.length < 3 || rows.length < 3) return null;
  const states = rows.map((row) => ({
    title: row[0],
    actions: (row[1] || '').split(/\s*→\s*/).map((item) => item.trim()).filter(Boolean),
    roleLabel: header[2],
    role: row[2] || '',
  }));
  return `<figure class="state-diagram" aria-label="${isEn ? 'Operating states' : '运行状态场景'}">
    <figcaption class="diagram-head">
      <span class="diagram-head-row">
        <span class="diagram-kicker">${isEn ? 'Operating states · STATES' : '运行状态 · STATES'}</span>
        <span class="diagram-meta">${states.length} ${isEn ? 'states' : '个场景'}</span>
      </span>
    </figcaption>
    <div class="state-grid">${states.map((state, idx) => `<article class="state-card">
      <span class="state-index" aria-hidden="true">${String(idx + 1).padStart(2, '0')}</span>
      <span class="state-title">${inline(state.title)}</span>
      <ol class="state-actions">${state.actions.map((action) => `<li>${inline(action)}</li>`).join('')}</ol>
      ${state.role ? `<div class="state-role"><span class="state-role-label">${inline(state.roleLabel)}</span><span>${inline(state.role)}</span></div>` : ''}
    </article>`).join('')}</div>
  </figure>`;
}

function convert(md, options = {}) {
  const lines = md.replace(/\r\n?/g, '\n').split('\n');
  const isEn = options.lang === 'en';
  const isSkillPage = !!options.isSkill;
  const policy = options.layout === 'policy';
  const policyCounts = policy ? policyGroupCounts(lines) : [];
  let policyGroupIdx = 0;
  let policyGroupOpen = false;
  let policyTotal = 0;
  const policyStats = new Map();
  const out = [];
  const headings = [];
  let h1 = '';
  let h2 = '';
  let h3 = '';
  let entryTableConverted = false;
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
      const lang = line.replace(/^\s*```/, '').trim();
      const buf = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i += 1; }
      i += 1;
      codeCount += 1;
      const body = buf.join('\n');
      const curated = !lang ? renderCuratedArchitecture(body) : null;
      const diagram = curated || ((!lang || /^(diagram|arch|tree|flow)$/i.test(lang)) ? renderAsciiDiagram(body, isEn) : null);
      if (diagram) {
        out.push(diagram);
        seenBlock = true;
        lastBlock = 'diagram';
      } else {
        out.push(`<pre tabindex="0"><code>${esc(body)}</code></pre>`);
        seenBlock = true;
        lastBlock = 'code';
      }
      continue;
    }

    if (line.trim() === '') { i += 1; continue; }

    if (/^\s*<!--.*-->\s*$/.test(line)) { i += 1; continue; }

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
      if (level === 2) { h2 = plainText(text); h3 = ''; entryTableConverted = false; }
      else if (level === 3) h3 = plainText(text);
      if (level === 1 && !h1) { h1 = text; i += 1; continue; }
      if (level === 1) { out.push(`<h2>${inline(text)}</h2>`); i += 1; seenBlock = true; lastBlock = 'heading'; continue; }
      if (policy && level === 2) {
        if (policyGroupOpen) out.push('</section>');
        policyGroupOpen = false;
        const groupCount = policyCounts[policyGroupIdx] ?? 0;
        policyGroupIdx += 1;
        const id = `s${(seq += 1)}`;
        headings.push({ level: 2, id, text: plainText(text) });
        if (groupCount > 0) {
          out.push(`<section class="policy-group"><h2 id="${id}">${inline(text)}<span class="policy-group-count">${groupCount}</span></h2>`);
          policyGroupOpen = true;
        } else {
          out.push(`<h2 id="${id}">${inline(text)}</h2>`);
        }
        i += 1;
        seenBlock = true;
        lastBlock = 'heading';
        continue;
      }
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
      if (!isSkillPage && /孤岛、GFM 与黑启动/.test(h3) && header[0] === '阶段') {
        const states = renderStateTable(header, rows, isEn);
        if (states) {
          out.push(states);
          tableCount += 1;
          i = j;
          seenBlock = true;
          lastBlock = 'diagram';
          continue;
        }
      }
      const milestoneKind = !isSkillPage && (/并网流程/.test(h3) ? 'grid' : (/中国主体进入路径/.test(h2) ? 'entry' : null));
      if (milestoneKind && header[0] === '步骤' && rows.length >= 3) {
        const milestone = renderMilestoneTable(header, rows, isEn, milestoneKind);
        if (milestone) {
          out.push(milestone);
          tableCount += 1;
          if (milestoneKind === 'entry') entryTableConverted = true;
          i = j;
          seenBlock = true;
          lastBlock = 'diagram';
          continue;
        }
      }
      if (policy && header.some((c) => c.includes('文号'))) {
        const col = (name) => header.findIndex((c) => c.includes(name));
        const cols = { no: col('文号'), title: col('文件'), note: col('要点'), org: col('机关'), date: col('日期'), status: col('状态'), link: col('原文') };
        if (Object.values(cols).some((k) => k === -1)) throw new Error('政策表缺少必需列（文号/文件/要点/机关/日期/状态/原文）');
        const cards = rows.map((r) => {
          const card = renderPolicyCard(r, cols);
          policyTotal += 1;
          policyStats.set(card.status, (policyStats.get(card.status) || 0) + 1);
          return card.html;
        });
        out.push(`<div class="policy-list">\n${cards.join('\n')}\n</div>`);
        i = j;
        seenBlock = true;
        lastBlock = 'table';
        continue;
      }
      const cell = (tag, val, k) => {
        const a = align[k];
        const style = a && a !== 'left' ? ` style="text-align:${a}"` : '';
        return `<${tag}${style}>${inline(val)}</${tag}>`;
      };
      let html = '<div class="table-wrap" tabindex="0" role="group" aria-label="可横向滚动的表格"><table><thead><tr>';
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
      if (!isSkillPage && !entryTableConverted && /中国主体进入路径/.test(h2) && /(落地顺序|开发顺序)/.test(h3)
        && items.length >= 3 && items.every((item) => item.ordered)) {
        out.push(renderMilestoneList(items, isEn));
        i = next;
        seenBlock = true;
        lastBlock = 'diagram';
        continue;
      }
      const special = isSkillPage ? null : (raw) => renderSpecialFlowItem(raw, h2, h3, isEn);
      out.push(renderList(items, special ? { special } : {}));
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

  if (policyGroupOpen) out.push('</section>');

  return {
    h1,
    body: out.join('\n'),
    headings,
    tableCount,
    codeCount,
    policy: policy ? { count: policyTotal, stats: Object.fromEntries(policyStats) } : undefined,
  };
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
    const badge = count === undefined ? '' : `<span class="count">${count}</span>`;
    return `      <a href="${item.href}"${active}><span class="n">${item.n}</span><span>${esc(item.label)}</span>${badge}</a>`;
  }).join('\n');
}

function renderCard(doc) {
  const href = `html/${doc.html}`;
  const search = [doc.search, doc.title, doc.summary, ...doc.tags].filter(Boolean).join(' ');
  const minutes = readingTime(doc.raw || doc.body || '');
  const cutoffLabel = doc.cutoff ? `截止 ${esc(doc.cutoff)}` : `约 ${minutes} 分钟`;
  return `          <article class="card" id="${esc(doc.id)}" data-type="${esc(doc.level)}" data-search="${esc(search)}">
            <div class="card-top"><span class="kind">${esc(doc.kind)}</span><span class="card-meta">约 ${minutes} 分钟</span></div>
            <h3><a class="card-link" href="${href}">${esc(doc.title)}</a></h3>
            <p>${esc(doc.summary)}</p>
            <div class="card-foot"><span>${cutoffLabel}</span><span class="card-cta" aria-hidden="true">阅读 →</span></div>
          </article>`;
}

function sectionCounts() {
  const counts = new Map();
  for (const d of manifest) counts.set(d.section, (counts.get(d.section) || 0) + 1);
  return counts;
}

function renderCategoryFilters() {
  const counts = sectionCounts();
  return [
    `<button class="cat-chip on" type="button" data-cat="all" aria-pressed="true">全部分类<b>${total}</b></button>`,
    ...sections.map((s) => `<button class="cat-chip" type="button" data-cat="${s.id}" aria-pressed="false">${esc(s.navLabel)}<b>${counts.get(s.id) || 0}</b></button>`),
  ].join('\n            ');
}

function renderCategoryOptions() {
  return [
    '<option value="all">全部分类</option>',
    ...sections.map((s) => `<option value="${s.id}">${esc(s.navLabel)}</option>`),
  ].join('\n              ');
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
  const tokensCss = readFileSync(tokensPath, 'utf8').replace(/\r\n?/g, '\n').trim();
  const template = readFileSync(templatePath, 'utf8')
    .replace(/\r\n?/g, '\n')
    .replace('/* @@TOKENS@@ */', tokensCss);
  const tokens = {
    metaDescription: `energy-skills 知识库总览：${total} 个模块，覆盖${site.coverage}。数据截止 ${cutoff}。`,
    brandLine: `${total} 个模块<br>数据截止 ${cutoff}`,
    sidebarNav: renderSidebarNav(),
    heroEyebrow: `Knowledge Hub · ${cutoff} · ${total} 模块`,
    heroLede: `把 ${total} 份主题笔记、政策索引与调研底稿，收进一张可检索、可跳转的知识地图。每个模块都有对应的 HTML 阅读页，文字与数字取自 Markdown 原文。`,
    heroStats: `
              <div class="stat"><b>${total}</b><span>知识模块</span></div>
              <div class="stat"><b>${coreCount}</b><span>核心模块</span></div>
              <div class="stat"><b>${researchCount}</b><span>调研底稿</span></div>
              <div class="stat"><b>${site.skills}</b><span>配套技能</span></div>
            `,
    resultDefault: `${total} / ${total} 个模块`,
    categoryFilters: renderCategoryFilters(),
    categoryOptions: renderCategoryOptions(),
    repositoryUrl: site.repository,
    repositoryLabel: site.repository.replace(/^https?:\/\//, ''),
    moduleSections: renderModuleSections(),
    footerLine: `数据截止 ${cutoff} · ${total} 个模块 · ${cnNum(site.skills)}项技能`,
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

const CHROME = {
  zh: {
    skip: '跳到正文',
    progress: '阅读进度',
    hub: '知识库',
    back: '返回知识库',
    themeDark: '切换到深色模式',
    more: '更多',
    source: '.md 源文件',
    method: '使用与口径',
    langSwitch: 'English',
    tocToggle: '目录',
    current: '当前分类',
    others: '其他分类',
    toc: '本页目录',
    tocEmpty: '本文无分节标题',
    tocMore: '展开 {n} 个小节',
    tocLess: '收起小节',
    related: '相关模块',
    relationSame: '同区延伸',
    relationCross: '跨区对照',
    relationIndex: '查证入口',
    moreRelated: '更多关联',
    pairedSkills: '配套技能',
    skillModules: '适用知识模块',
    prev: '← 上一篇',
    next: '下一篇 →',
    download: '下载 TXT',
    downloadNote: '完整技能文档，约 {n} KB，含 frontmatter',
    footer: '本页由 {source} 构建，内容与源文件同步；若两者不一致，以 .md 为准。除另有说明外，算例均为合成数据。',
    returnHub: '返回知识库总览 →',
    titleSuffix: 'energy-skills 知识库',
  },
  en: {
    skip: 'Skip to content',
    progress: 'Reading progress',
    hub: 'Knowledge hub',
    back: 'Back to knowledge hub',
    themeDark: 'Switch to dark mode',
    more: 'More',
    source: 'Source .md',
    method: 'Method & caliber',
    langSwitch: '中文',
    tocToggle: 'Contents',
    current: 'Current section',
    others: 'Other sections',
    toc: 'On this page',
    tocEmpty: 'No section headings',
    tocMore: 'Show {n} subsections',
    tocLess: 'Hide subsections',
    related: 'Related modules',
    relationSame: 'Same section',
    relationCross: 'Cross-section',
    relationIndex: 'Verification entry',
    moreRelated: 'More links',
    pairedSkills: 'Paired skills',
    skillModules: 'Applicable knowledge modules',
    prev: '← Previous',
    next: 'Next →',
    download: 'Download TXT',
    downloadNote: 'Full skill document, about {n} KB, frontmatter included',
    footer: 'Built from {source}; the Markdown source remains authoritative if the two differ. Worked examples are synthetic unless stated otherwise.',
    returnHub: 'Back to knowledge hub →',
    titleSuffix: 'energy-skills Knowledge Base',
  },
};

const copyFor = (lang) => CHROME[lang === 'en' ? 'en' : 'zh'];
const docTitle = (doc, lang) => (lang === 'en' && doc.title_en ? doc.title_en : doc.title);
const docSummary = (doc, lang) => (lang === 'en' && doc.summary_en ? doc.summary_en : doc.summary);
const KIND_EN = {
  '知识模块': 'Knowledge note',
  '索引': 'Index',
  '教材笔记': 'Book note',
  '主题笔记': 'Thematic note',
  '算法底稿': 'Algorithm note',
  '口径字典': 'Glossary',
  '调研底稿': 'Research record',
  '问答集': 'Q&A',
};
const kindLabel = (doc, lang) => (lang === 'en' ? KIND_EN[doc.kind] || doc.kind : doc.kind);

function buildPage(doc) {
  const isSkill = doc.section === 'skill';
  const sec = isSkill ? skillSection : sectionById.get(doc.section);
  const lang = doc.lang || (/^INDEX_EN/i.test(doc.md) ? 'en' : 'zh-CN');
  const copy = copyFor(lang);
  const secTitle = isSkill
    ? (lang === 'en' ? 'Paired skills' : '配套技能')
    : (lang === 'en' ? sectionTitlesEn[sec.id] || sec.title : sec.title);
  const policyBar = doc.layout === 'policy' && doc.policy?.count ? renderPolicyBar(doc.policy) : '';
  const sourceHref = doc.srcHref || `../${doc.md}`;
  const sourceLabel = doc.srcHref ? doc.md : `knowledge/${doc.md}`;
  const languageLink = isSkill
    ? `<a class="src" href="skill-${doc.slug}${lang === 'en' ? '' : '-en'}.html" hreflang="${lang === 'en' ? 'zh-CN' : 'en'}">${esc(copy.langSwitch)}</a>`
    : '';
  const isHistorical = doc.historical === true || doc.historical === 'true';
  const historicalBanner = isHistorical
    ? `<aside class="historical-banner" role="note">
      <strong>${lang === 'en' ? 'Historical note — data is not current' : '史料笔记 — 数据不可作现行引用'}</strong>
      <span>${lang === 'en'
        ? 'Figures in this note date from the book / historical snapshot. Use them as historical evidence only; principles and formulas remain applicable, but verify every number against current rules before quoting.'
        : '本页规模、价格与政策节点均为成书期／历史时点数据，只能作史料引用；原理与公式部分仍适用，引用任何数字前须按现行规则复核。'}</span>
    </aside>`
    : '';
  const repositoryLabel = site.repository.replace(/^https?:\/\//, '');
  const downloadSize = Math.max(1, Math.round((doc.txt || '').length / 1024));
  const downloadBlock = isSkill
    ? `<p class="doc-actions"><a class="dl-btn" href="${esc(doc.download)}" download="${esc(doc.downloadName)}">${esc(copy.download)}</a><span>${esc(copy.downloadNote.replace('{n}', String(downloadSize)))}</span></p>`
    : '';
  const h2s = doc.headings.filter((h) => h.level === 2);
  const h3s = doc.headings.filter((h) => h.level === 3);
  const toc = h2s.length ? h2s : doc.headings.filter((h) => h.level <= 3).slice(0, 12);
  const tocAll = h2s.length ? doc.headings.filter((h) => h.level === 2 || h.level === 3) : toc;
  const tocOpen = h2s.length > 0 && h2s.length <= 2 && h3s.length > 0 && h3s.length <= 16;
  const tocMobileItems = tocOpen ? tocAll : toc;
  const pageCutoff = cutoffOf(doc.raw) || doc.cutoff || '';
  const minutes = readingTime(doc.raw);
  const chars = (doc.raw.replace(/\s/g, '').length / 1000).toFixed(1);

  const tocItems = tocAll.map((h) => `<li class="lv${h.level}"><a href="#${h.id}">${h.text}</a></li>`).join('\n            ');
  const tocMobile = tocMobileItems.map((h) => `<li class="lv${h.level}"><a href="#${h.id}">${h.text}</a></li>`).join('\n            ');
  const tocMore = h3s.length
    ? `<button class="toc-more" type="button" aria-expanded="${tocOpen}" data-count="${h3s.length}" data-more-label="${esc(copy.tocMore.replace('{n}', String(h3s.length)))}" data-less-label="${esc(copy.tocLess)}">${tocOpen ? esc(copy.tocLess) : esc(copy.tocMore.replace('{n}', String(h3s.length)))}</button>`
    : '';

  const sideDocs = isSkill
    ? skillManifest.filter((m) => m.lang === lang)
    : manifest.filter((m) => m.section === sec.id);
  const sideList = sideDocs
    .map((m) => `<li${m.id === doc.id ? ' class="on" aria-current="page"' : ''}><a href="${m.html}">${esc(docTitle(m, lang))}</a></li>`).join('\n              ');
  const others = sections.filter((s) => isSkill || s.id !== sec.id)
    .map((s) => {
      const label = lang === 'en' ? sectionTitlesEn[s.id] || s.title : s.title;
      return `<li><a href="../index.html#${s.id}"><b>${esc(s.num.split('·')[0].trim())}</b>${esc(label)}</a></li>`;
    }).join('\n              ');

  const idx = sideDocs.findIndex((d) => d.id === doc.id);
  const prev = sideDocs[idx - 1];
  const next = sideDocs[idx + 1];
  const pager = [
    prev ? `<a class="prev" href="${prev.html}"><span class="dir">${esc(copy.prev)}</span><span class="ttl">${esc(docTitle(prev, lang))}</span></a>` : '<span class="spacer"></span>',
    next ? `<a class="next" href="${next.html}"><span class="dir">${esc(copy.next)}</span><span class="ttl">${esc(docTitle(next, lang))}</span></a>` : '<span class="spacer"></span>',
  ].join('\n          ');

  const relationLabel = (target) => {
    if (target.section === 'index') return copy.relationIndex;
    return target.section === doc.section ? copy.relationSame : copy.relationCross;
  };
  const renderRelatedCard = (target, label) => `<a class="related-card" href="${target.html}">
          <span class="related-type">${esc(label)}</span>
          <b>${esc(docTitle(target, lang))}</b>
          <span>${esc(docSummary(target, lang))}</span>
        </a>`;
  const related = doc.related.map((id) => byId.get(id));
  const relatedLead = related.slice(0, 4);
  const relatedRest = related.slice(4);
  const relatedBlock = related.length ? `<section class="related" aria-labelledby="related-title">
      <div class="related-head"><h2 id="related-title">${esc(copy.related)}</h2><span>${related.length}</span></div>
      <div class="related-grid">
        ${relatedLead.map((r) => renderRelatedCard(r, relationLabel(r))).join('\n        ')}
      </div>
      ${relatedRest.length ? `<p class="related-rest"><b>${esc(copy.moreRelated)}</b>${relatedRest.map((r) => `<a href="${r.html}">${esc(docTitle(r, lang))}</a>`).join('')}</p>` : ''}
    </section>` : '';

  const pairedSkills = !isSkill ? (skillsByModuleId.get(doc.id) || []) : [];
  const skillModules = isSkill ? doc.modules.map((id) => byId.get(id)) : [];
  const pairedSkillsBlock = pairedSkills.length ? `<section class="related" aria-labelledby="paired-skills-title">
      <div class="related-head"><h2 id="paired-skills-title">${esc(copy.pairedSkills)}</h2><span>${pairedSkills.length}</span></div>
      <div class="related-grid">
        ${pairedSkills.map((s) => `<a class="related-card skill-pair" href="skill-${s.slug}.html">
          <span class="related-type">${esc(s.summary)}</span>
          <b>${esc(s.title)}</b>
          <span>${esc(s.tags.join(' · '))}</span>
        </a>`).join('\n        ')}
      </div>
    </section>` : '';
  const skillModulesBlock = skillModules.length ? `<section class="related" aria-labelledby="skill-modules-title">
      <div class="related-head"><h2 id="skill-modules-title">${esc(copy.skillModules)}</h2><span>${skillModules.length}</span></div>
      <div class="related-grid">
        ${skillModules.slice(0, 4).map((r) => renderRelatedCard(r, copy.relationCross)).join('\n        ')}
      </div>
      ${skillModules.length > 4 ? `<p class="related-rest"><b>${esc(copy.moreRelated)}</b>${skillModules.slice(4).map((r) => `<a href="${r.html}">${esc(docTitle(r, lang))}</a>`).join('')}</p>` : ''}
    </section>` : '';

  const meta = [
    `<span>${lang === 'en' ? `approx. ${chars}k characters` : `约 ${chars}k 字`}</span>`,
    `<span>${lang === 'en' ? `${minutes} min read` : `阅读约 ${minutes} 分钟`}</span>`,
    `<span>${lang === 'en' ? `${toc.length} sections` : `${toc.length} 节`}</span>`,
    pageCutoff ? `<span>${lang === 'en' ? 'Data cutoff' : '数据截止'} ${esc(pageCutoff)}</span>` : '',
  ].filter(Boolean).join('');
  const footerCopy = copy.footer.split('{source}');

  const pageHtml = `<!doctype html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>${esc(doc.title)} | ${esc(copy.titleSuffix)}</title>
<meta name="description" content="${esc(doc.summary)}">
<link rel="icon" type="image/svg+xml" href="../assets/logo-book-favicon.svg">
<script>
(function(){try{var t=localStorage.getItem('es-theme');if(t!=='dark'&&t!=='light'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
</script>
<link rel="stylesheet" href="../assets/tokens.css">
<link rel="stylesheet" href="../assets/knowledge.css">
</head>
<body data-cat="${esc(sec.cat)}" id="top">
<a class="skip" href="#main">${esc(copy.skip)}</a>
<div class="progress" id="progress" aria-hidden="true"></div>
<div class="scrim"></div>

<header class="topbar">
  <a class="back" href="../index.html" data-home-link aria-label="${esc(copy.back)}"><span aria-hidden="true">←</span><span class="back-label">${esc(copy.hub)}</span></a>
  <div class="crumb">
    <span class="crumb-cat">${esc(sec.num)}</span>
    <span class="crumb-sep">/</span>
    <span class="crumb-doc">${esc(doc.title)}</span>
  </div>
  <div class="topbar-act">
    <button class="theme-toggle" type="button" data-theme-toggle aria-label="${esc(copy.themeDark)}" title="${esc(copy.themeDark)}">
      <svg class="ico-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"/></svg>
      <svg class="ico-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    </button>
    <details class="more">
      <summary class="more-btn" aria-label="${esc(copy.more)}" title="${esc(copy.more)}"><span class="more-label">${esc(copy.more)}</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></svg></summary>
      <div class="more-menu">
        <a class="src" href="${esc(sourceHref)}">${esc(copy.source)}<small>${esc(sourceLabel)}</small></a>
        ${languageLink}
        <a class="src" href="../index.html#method">${esc(copy.method)}</a>
      </div>
    </details>
    <button class="toc-toggle" type="button" id="navToggle" aria-expanded="false" aria-controls="nav">${esc(copy.tocToggle)}</button>
  </div>
</header>

<div class="shell">
  <aside class="sidebar" id="nav">
    <div class="nav-kicker">${esc(copy.current)}</div>
    <div class="nav-num">${esc(sec.num)}</div>
    <h2 class="nav-cat"><a href="../index.html#${isSkill ? 'skills' : esc(sec.id)}">${esc(secTitle)}</a></h2>
    <ul class="nav-list">
              ${sideList}
    </ul>
    <div class="nav-others">
      <div class="nav-kicker">${esc(copy.others)}</div>
      <ul>
              ${others}
      </ul>
    </div>
  </aside>

  <main class="main" id="main">
    <header class="doc-head">
      <div class="kicker">${esc(sec.num)}<i>${esc(kindLabel(doc, lang))}</i></div>
      <h1 class="doc-title">${esc(doc.h1 || docTitle(doc, lang))}</h1>
      <p class="lede">${esc(docSummary(doc, lang))}</p>
      ${doc.foot ? `<p class="hook">${esc(doc.foot)}</p>` : ''}
      ${doc.tags.length ? `<div class="tags">${doc.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
      <div class="doc-meta">${meta}</div>${downloadBlock ? `\n      ${downloadBlock}` : ''}
    </header>

    ${historicalBanner ? `    ${historicalBanner}\n\n` : ''}${tocMobileItems.length ? `<details class="toc-mobile">
      <summary>${esc(lang === 'en' ? `On this page (${tocMobileItems.length})` : `本页目录（${tocMobileItems.length}）`)}</summary>
      <ol>
            ${tocMobile}
      </ol>
    </details>` : ''}

${policyBar ? `    ${policyBar}\n\n` : ''}    <article class="prose">
${doc.body}
    </article>

${doc.layout === 'policy' ? '    <div class="policy-empty" id="policyEmpty" hidden>没有匹配的政策。试试文号、标题关键词，或切回「全部」。</div>\n\n' : ''}    ${relatedBlock}
${skillModulesBlock ? `\n${skillModulesBlock}` : ''}${pairedSkillsBlock ? `\n${pairedSkillsBlock}` : ''}

    <nav class="pager" aria-label="${lang === 'en' ? 'Previous and next' : '上下篇'}">
          ${pager}
    </nav>

    <footer class="doc-foot">
      <div class="lic">${esc(footerCopy[0])}<a href="${esc(sourceHref)}">${esc(sourceLabel)}</a>${esc(footerCopy[1] || '')}</div>
      <div class="doc-foot-links">
        <a href="${esc(site.repository)}" target="_blank" rel="noopener">${lang === 'en' ? 'GitHub repository' : 'GitHub 仓库'}：${esc(repositoryLabel)} ↗</a>
        <span aria-hidden="true"> · </span>
        <a href="../index.html" data-home-link>${esc(copy.returnHub)}</a>
      </div>
    </footer>
  </main>

  <aside class="toc${tocOpen ? ' expanded' : ''}" aria-label="${esc(copy.toc)}">
    <div class="toc-title">${esc(copy.toc)}</div>
    ${tocAll.length ? `<ol>
            ${tocItems}
    </ol>${tocMore}` : `<div class="toc-empty">${esc(copy.tocEmpty)}</div>`}
  </aside>
</div>

<nav class="page-aux" aria-label="${lang === 'en' ? 'Page utilities' : '页面辅助'}">
  <a class="to-top" href="#top" aria-label="${lang === 'en' ? 'Back to top' : '回到顶部'}">↑</a>
</nav>
<script src="../assets/doc.js"></script>
<script src="../assets/theme.js"></script>
</body>
</html>
`;
  return pageHtml.replace(/^[ \t]+$/gm, '');
}

/* ----------------------------------------------------------- 全文检索索引 */

function htmlText(html) {
  return unesc(String(html)
    .replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<[^>]+>/g, ' '))
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildSearchIndex(pageItems) {
  const searchText = (html) => htmlText(html)
    .replace(/[─│┌┐└┘├┤┬┴┼▲▼◀▶]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const records = pageItems.map(({ doc }) => {
    const section = sectionById.get(doc.section);
    const headingRe = /<h([23])\s+id="([^"]+)"[^>]*>([\s\S]*?)<\/h\1>/g;
    const heads = [];
    let match;
    while ((match = headingRe.exec(doc.body))) {
      heads.push({
        level: Number(match[1]),
        id: match[2],
        title: htmlText(match[3]),
        start: match.index,
        end: headingRe.lastIndex,
      });
    }
    const chunks = [];
    const intro = searchText(doc.body.slice(0, heads[0]?.start ?? doc.body.length));
    if (intro) chunks.push({ h: doc.title, a: '', x: intro });
    heads.forEach((head, i) => {
      const text = searchText(doc.body.slice(head.end, heads[i + 1]?.start ?? doc.body.length));
      chunks.push({ h: head.title, a: head.id, x: text, l: head.level });
    });
    return {
      id: doc.id,
      title: doc.title,
      summary: doc.summary,
      tags: doc.tags,
      cat: doc.section,
      catTitle: section?.title || '',
      catNum: section?.num || '',
      type: doc.level,
      html: `html/${doc.html}`,
      cutoff: doc.cutoff || '',
      keywords: [doc.search, doc.title, doc.summary, ...doc.tags].filter(Boolean).join(' '),
      chunks,
    };
  });
  if (records.length !== docs.length) throw new Error(`全文索引模块数 ${records.length} 与清单 ${docs.length} 不一致`);
  const payload = JSON.stringify({ schema: 1, cutoff, docs: records })
    .replace(/</g, '\\u003c')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
  return `/* 生成物：运行 node scripts/build-knowledge-html.mjs 重建；不要手改。 */
window.__ES_SEARCH_INDEX__ = ${payload};
`;
}

/* ---------------------------------------------------------------- 主流程 */

if (!existsSync(templatePath)) throw new Error('缺少 knowledge/index.template.html');

mkdirSync(htmlDir, { recursive: true });

function convertDoc(doc) {
  activeMapHref = doc.section === 'skill' ? makeSkillHrefMapper(doc) : mapHref;
  const lang = doc.lang || (/^INDEX_EN/i.test(doc.md) ? 'en' : 'zh-CN');
  try {
    return convert(doc.body, { layout: doc.layout, lang, isSkill: doc.section === 'skill' });
  } finally {
    activeMapHref = mapHref;
  }
}

const pages = manifest.map((doc) => {
  const converted = convertDoc(doc);
  const merged = { ...doc, ...converted };
  return { doc: merged, html: buildPage(merged) };
});

const skillPages = skillManifest.map((doc) => {
  const converted = convertDoc(doc);
  const merged = { ...doc, ...converted, h1: doc.title };
  return { doc: merged, html: buildPage(merged) };
});

const allPages = [...pages, ...skillPages];
const archHits = new Map();
for (const page of allPages) {
  for (const match of page.html.matchAll(/data-arch-id="([^"]+)"/g)) {
    archHits.set(match[1], (archHits.get(match[1]) || 0) + 1);
  }
}
for (const id of CURATED_ARCH_IDS) {
  if (archHits.get(id) !== 1) throw new Error(`核心架构图 ${id} 应恰好出现 1 次，实际 ${archHits.get(id) || 0} 次；检查源图指纹`);
}
for (const id of archHits.keys()) {
  if (!CURATED_ARCH_IDS.includes(id)) throw new Error(`未登记的核心架构图：${id}`);
}
const downloadDir = join(htmlDir, 'download', 'skills');
const downloadFiles = skillManifest.map((doc) => ({
  path: join(downloadDir, basename(doc.download)),
  content: doc.txt,
}));

const indexHtml = renderIndex();
const searchIndexJs = buildSearchIndex(pages);
const credibilityIndex = buildIndex(root);
const credibilityJson = serializeIndex(credibilityIndex);
const credByFile = new Map(credibilityIndex.modules.map((m) => [m.file, m]));
const englishDigestJson = `${JSON.stringify({
  schema: 1,
  description: 'English routing digest for the Chinese knowledge notes. Use it to decide which module to open and which figures are safe to quote; the full notes remain in Chinese.',
  note: 'A number needs a grade, a time point and a caliber. Filter gradeC by usable/banned before using any unverified figure. Full texts of policies are linked from the Chinese policy indexes.',
  generatedFrom: 'knowledge/*.md frontmatter (summary_en) + INDEX_EN structured tables + credibility register',
  summary: {
    modules: docs.length,
    withEnglishSummary: docs.filter((d) => d.summary_en).length,
    keyFigures: credibilityIndex.keyFigures.length,
    openItems: credibilityIndex.openItems.length,
    datedOpenItems: credibilityIndex.openItemDues.length,
    gradeCTickets: credibilityIndex.gradeC.length,
    pendingGradeC: credibilityIndex.summary.unverifiedGradeC,
  },
  modules: docs.map((d) => ({
    id: d.id,
    file: d.md,
    section: d.section,
    kind: d.kind,
    cutoff: d.cutoff || null,
    title: d.title,
    titleEn: d.title_en || null,
    summaryEn: d.summary_en || null,
    confidence: credByFile.get(d.md)?.confidence ?? null,
    historical: d.historical === true || d.historical === 'true',
    html: `html/${d.html}`,
  })),
  keyFigures: credibilityIndex.keyFigures,
  openItems: credibilityIndex.openItems,
  datedOpenItems: credibilityIndex.openItemDues,
  gradeC: credibilityIndex.gradeC.map((t) => ({
    n: t.n, figure: t.figure, status: t.status, usable: t.usable, banned: t.banned,
    pending: t.pending, nextReview: t.nextReview, conclusion: t.conclusion,
  })),
}, null, 2)}\n`;

function verifyLinks(baseDir, html, label, pending = new Set()) {
  const missing = [];
  for (const m of html.matchAll(/href="([^"]+)"/g)) {
    const href = unesc(m[1]);
    if (/^(https?:|mailto:|#)/.test(href)) continue;
    const path = href.split('#')[0].split('?')[0];
    if (!path) continue;
    const target = resolve(baseDir, decodeURIComponent(path));
    if (!existsSync(target) && !pending.has(target)) missing.push(href);
  }
  if (missing.length) throw new Error(`${label} 存在断链：${[...new Set(missing)].join('、')}`);
}

const pendingPages = new Set(allPages.map((p) => join(htmlDir, p.doc.html)));
for (const f of downloadFiles) pendingPages.add(f.path);
verifyLinks(knowledgeDir, indexHtml, 'knowledge/index.html', pendingPages);
for (const { doc, html } of allPages) verifyLinks(htmlDir, html, `knowledge/html/${doc.html}`, pendingPages);

if (checkMode) {
  const diffs = [];
  const same = (path, expected) => existsSync(path) && readFileSync(path, 'utf8').replace(/\r\n?/g, '\n') === expected;
  if (!same(indexPath, indexHtml)) diffs.push('knowledge/index.html 不是最新生成物');
  if (!same(searchIndexPath, searchIndexJs)) diffs.push('knowledge/search-index.js 不是最新生成物');
  if (!same(credibilityPath, credibilityJson)) diffs.push('knowledge/credibility.json 不是最新生成物');
  if (!same(englishDigestPath, englishDigestJson)) diffs.push('knowledge/english-digest.json 不是最新生成物');
  for (const { doc, html } of allPages) {
    if (!same(join(htmlDir, doc.html), html)) diffs.push(`knowledge/html/${doc.html} 不是最新生成物`);
  }
  for (const f of downloadFiles) {
    if (!same(f.path, f.content)) diffs.push(`knowledge/html/download/skills/${basename(f.path)} 不是最新生成物`);
  }
  const expected = new Set(allPages.map((p) => p.doc.html));
  for (const f of readdirSync(htmlDir).filter((f) => f.endsWith('.html'))) {
    if (!expected.has(f)) diffs.push(`knowledge/html/${f} 已无对应 Markdown（删除或重新生成）`);
  }
  const expectedTxt = new Set(downloadFiles.map((f) => basename(f.path)));
  if (existsSync(downloadDir)) {
    for (const f of readdirSync(downloadDir).filter((f) => f.endsWith('.txt'))) {
      if (!expectedTxt.has(f)) diffs.push(`knowledge/html/download/skills/${f} 已无对应技能（删除或重新生成）`);
    }
  }
  if (diffs.length) {
    console.error('生成物校验失败，请运行 node scripts/build-knowledge-html.mjs：');
    for (const d of diffs) console.error(`- ${d}`);
    process.exit(1);
  }
  console.log(`生成物校验通过：index.html + search-index.js + credibility.json + english-digest.json + ${pages.length} 个知识页 + ${skillPages.length} 个技能页 + ${downloadFiles.length} 个下载文件均为最新（${total} 个模块 / ${fmt(totalLines)} 行）。`);
  process.exit(0);
}

for (const { doc, html } of allPages) writeFileSync(join(htmlDir, doc.html), html, 'utf8');
writeFileSync(searchIndexPath, searchIndexJs, 'utf8');
writeFileSync(credibilityPath, credibilityJson, 'utf8');
writeFileSync(englishDigestPath, englishDigestJson, 'utf8');
mkdirSync(downloadDir, { recursive: true });
for (const f of downloadFiles) writeFileSync(f.path, f.content, 'utf8');
if (rewriteIndex) writeFileSync(indexPath, indexHtml, 'utf8');

const tables = pages.reduce((a, p) => a + p.doc.tableCount, 0);
const codes = pages.reduce((a, p) => a + p.doc.codeCount, 0);
const headings = pages.reduce((a, p) => a + p.doc.headings.length, 0);
console.log(`已生成 ${pages.length} 个知识页 + ${skillPages.length} 个技能页 + ${downloadFiles.length} 个 TXT → knowledge/html/`);
console.log(`模块 ${total} 个 / 正文 ${fmt(totalLines)} 行；章节 ${headings}，表格 ${tables}，代码/图块 ${codes}`);
if (rewriteIndex) console.log('已生成 knowledge/index.html（卡片、侧栏与计数来自 frontmatter）');
console.log(`已生成 knowledge/search-index.js（${pages.length} 个模块，全文懒加载）`);
const biggest = [...allPages].map((p) => ({ html: p.doc.html, kb: Math.round(p.html.length / 1024) })).sort((a, b) => b.kb - a.kb).slice(0, 3);
console.log(`最大页面：${biggest.map((b) => `${b.html} ${b.kb}KB`).join('，')}`);
