#!/usr/bin/env node
/**
 * 可信度层：把散在正文里的「C 级 / 待核实 / 草案 / 算例 / 未定事项」
 * 解析成机器可读的登记册，并提供内容级门禁规则。
 *
 * 设计约束（与仓库「单一事实源」铁律一致）：
 *   - 不再造第二份清单。事实源是已有的结构化内容：
 *       · 快照模块 §5「C 级数字待复核页」表格 → gradeC 工单
 *       · INDEX_EN §4「Open items」编号列表   → openItems
 *       · 快照模块 §3 事件日历表格            → events
 *       · 政策列表 / 省级政策列表 的状态列     → policyStatus
 *       · 各模块的算例章节标题                 → exampleSections
 *   - frontmatter 只新增「模块级声明」，不重复条目级内容：
 *       confidence: verified | mixed | draft | historical
 *       examples:   synthetic | documented | none
 *       historical: true | false
 *   - credibility.json 是生成物（与 index.html 同级），由构建器写入并纳入 --check。
 *
 * 用法：
 *   import { buildIndex, checkContent, serializeIndex } from './credibility.mjs';
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const norm = (s) => String(s).replace(/\r\n?/g, '\n');

export const CONFIDENCE = ['verified', 'mixed', 'draft', 'historical'];
export const EXAMPLE_MODES = ['synthetic', 'documented', 'none'];
export const POLICY_STATUS = ['现行', '即将施行', '草案', '征求意见稿', '已被取代', '参考'];
export const PRIORITIES = ['P0', 'P1', 'P2', 'P0（储能）'];
// 工单销项终态：已复核/已改口径/口径已确认 = 可用；已撤销/禁止引用 = 不可引用；待复核 = 未闭环。
export const TICKET_STATUS = ['待复核', '已复核', '已改口径', '口径已确认', '已撤销', '禁止引用'];
export const USABLE_STATUS = ['已复核', '已改口径', '口径已确认'];
export const BANNED_STATUS = ['已撤销', '禁止引用'];
export const TICKET_COLUMNS = 9;

const SNAPSHOT = '海外市场同口径快照与投决日历-2026-11.md';
const INDEX_EN = 'INDEX_EN-2026-11.md';
const GLOSSARY = '术语与口径字典-2026-11.md';
const POLICY_FILES = ['政策列表-2026-11.md', '省级政策列表-2026-11.md'];

const GRADE_C_RE = /C 级|（C）|\(C\)|待核实|待复核|grade C/i;
const DRAFT_RE = /草案|征求意见稿|征求意见/;
const EXAMPLE_HEAD_RE = /^#{2,4} .*(?:算例|示例|例题|worked example)[^\n]*$/im;
const EXAMPLE_MARKED_RE = /合成|synthetic|D 级|（D）|\(D\)|示例量级|仅演示|方法演示/i;
const HISTORY_DECL_RE = /数据时点|成书|出版|史料|历史数据|需更新|written ~|book published/i;

/** 极简 frontmatter 解析：只取标量 / 布尔 / JSON 数组，不做 Markdown 渲染。 */
export function parseFrontmatter(text) {
  const raw = norm(text);
  if (!raw.startsWith('---\n')) return null;
  const end = raw.indexOf('\n---\n', 4);
  if (end === -1) return null;
  const data = {};
  let key = null;
  for (const line of raw.slice(4, end).split('\n')) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    if (key && /^\s+/.test(line)) { data[key] += ' ' + line.trim(); continue; }
    const at = line.indexOf(':');
    if (at === -1) continue;
    key = line.slice(0, at).trim();
    let value = line.slice(at + 1).trim();
    if (value.startsWith('[') || value.startsWith('"')) {
      try { value = JSON.parse(value); } catch { /* 保留字符串，由规则报错 */ }
    }
    data[key] = value;
  }
  return data;
}

/** 表格行拆列（含首尾空列）。 */
const cells = (line) => norm(line).trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

/** 解析快照模块 §5 的 C 级工单表。 */
export function readGradeCLedger(root) {
  const path = join(root, 'knowledge', SNAPSHOT);
  if (!existsSync(path)) return { rows: [], error: `缺少登记册：knowledge/${SNAPSHOT}` };
  const text = norm(readFileSync(path, 'utf8'));
  const start = text.indexOf('## 5. C 级数字待复核页');
  if (start === -1) return { rows: [], error: '快照模块缺少 §5 C 级数字待复核页' };
  const seg = text.slice(start);
  const rows = [];
  for (const line of seg.split('\n')) {
    if (!/^\|\s*\d+\s*\|/.test(line)) continue;
    const c = cells(line);
    const conclusion = c[8] || '';
    const nextReview = conclusion.match(/下次复核\s*(\d{4}-\d{2}-\d{2})/)?.[1] ?? null;
    rows.push({
      n: Number(c[0]),
      figure: c[1] || '',
      module: c[2] || '',
      reason: c[3] || '',
      source: c[4] || '',
      priority: c[5] || '',
      status: c[6] || '',
      reviewedAt: c[7] || '',
      conclusion,
      nextReview,
      usable: USABLE_STATUS.includes(c[6]),
      banned: BANNED_STATUS.includes(c[6]),
      pending: c[6] === '待复核',
      columns: c.length,
    });
  }
  return { rows, error: null };
}

/** 解析快照模块 §1.4 空缺清单（20 个「待核实」格的补数节奏）。 */
export function readGaps(root) {
  const path = join(root, 'knowledge', SNAPSHOT);
  if (!existsSync(path)) return [];
  const text = norm(readFileSync(path, 'utf8'));
  const start = text.indexOf('### 1.4');
  if (start === -1) return [];
  const endMark = text.indexOf('\n### ', start + 4);
  const seg = text.slice(start, endMark === -1 ? undefined : endMark);
  const gaps = [];
  for (const line of seg.split('\n')) {
    if (!/^\|\s*P[012]\s*\|/.test(line)) continue;
    const c = cells(line);
    gaps.push({
      priority: c[0] || '',
      gap: c[1] || '',
      markets: c[2] || '',
      source: c[3] || '',
      target: c[4] || '',
      nextReview: c[5] || '',
      columns: c.length,
    });
  }
  return gaps;
}

/** 解析 INDEX_EN §2 的英文关键数字表（English digest 用）。 */
export function readKeyFigures(root) {
  const path = join(root, 'knowledge', INDEX_EN);
  if (!existsSync(path)) return [];
  const text = norm(readFileSync(path, 'utf8'));
  const start = text.indexOf('## 2.');
  if (start === -1) return [];
  const endMark = text.indexOf('\n## ', start + 4);
  const seg = text.slice(start, endMark === -1 ? undefined : endMark);
  const out = [];
  for (const line of seg.split('\n')) {
    if (!/^\|/.test(line) || /^\|\s*-/.test(line)) continue;
    const c = cells(line);
    if (c.length < 3 || /^(Topic|主题)/i.test(c[0])) continue;
    out.push({ topic: c[0], figures: c[1], grade: c[2] });
  }
  return out;
}

/** 解析 INDEX_EN §4.1 的未定事项到期登记册。 */
export function readOpenItemDues(root) {
  const path = join(root, 'knowledge', INDEX_EN);
  if (!existsSync(path)) return [];
  const text = norm(readFileSync(path, 'utf8'));
  const start = text.indexOf('### 4.1');
  if (start === -1) return [];
  const endMark = text.indexOf('\n## ', start + 4);
  const seg = text.slice(start, endMark === -1 ? undefined : endMark);
  const out = [];
  for (const line of seg.split('\n')) {
    if (!/^\|\s*\d+\s*\|/.test(line)) continue;
    const c = cells(line);
    out.push({ n: Number(c[0]), item: c[1] || '', due: c[2] || '', trigger: c[3] || '', source: c[4] || '', columns: c.length });
  }
  return out;
}

/** 解析术语字典：定义表中的缩写 + §7 受控缩写清单。 */
export function readGlossary(root) {
  const path = join(root, 'knowledge', GLOSSARY);
  if (!existsSync(path)) return { defined: [], controlled: [], error: `缺少术语字典：knowledge/${GLOSSARY}` };
  const text = norm(readFileSync(path, 'utf8'));
  const defined = [];
  for (const line of text.split('\n')) {
    if (!/^\|/.test(line) || /^\|\s*-/.test(line)) continue;
    const c = cells(line);
    if (c.length !== 6) continue;
    // 一行可能合并多个同族缩写（如 "GO / REGO / REC / LGC / NFC"），逐个登记。
    const terms = c[0].split(/[\/、,\s]+/).map((s) => s.trim()).filter((s) => s && s !== '—' && s !== '缩写' && s !== '-');
    for (const term of terms) defined.push({ term, definition: c[3], confusion: c[4], columns: c.length });
  }
  const controlled = [];
  const head = text.indexOf('## 7. 受控缩写清单');
  if (head !== -1) {
    const seg = text.slice(head);
    for (const line of seg.split('\n')) {
      const m = line.match(/^\|\s*([A-Za-z][A-Za-z0-9+/.-]*)\s*\|$/);
      if (m) controlled.push(m[1]);
    }
  }
  return { defined, controlled, error: null };
}

/** 解析 INDEX_EN §4 的 Open items 编号列表。 */
export function readOpenItems(root) {
  const path = join(root, 'knowledge', INDEX_EN);
  if (!existsSync(path)) return { items: [], error: `缺少登记册：knowledge/${INDEX_EN}` };
  const text = norm(readFileSync(path, 'utf8'));
  const start = text.indexOf('## 4. Open items');
  if (start === -1) return { items: [], error: 'INDEX_EN 缺少 §4 Open items' };
  const endMark = text.indexOf('\n## ', start + 4);
  const seg = text.slice(start, endMark === -1 ? undefined : endMark);
  const items = [];
  for (const line of seg.split('\n')) {
    const m = line.match(/^(\d+)\.\s+\*\*(.+?)\*\*:\s*(.+)$/);
    if (!m) continue;
    items.push({ n: Number(m[1]), topic: m[2].trim(), text: m[3].trim() });
  }
  return { items, error: null };
}

/** 解析快照模块 §3 事件日历。 */
export function readEvents(root) {
  const path = join(root, 'knowledge', SNAPSHOT);
  if (!existsSync(path)) return [];
  const text = norm(readFileSync(path, 'utf8'));
  const start = text.indexOf('## 3. 2026Q4–2027 事件日历');
  if (start === -1) return [];
  const endMark = text.indexOf('\n## ', start + 4);
  const seg = text.slice(start, endMark === -1 ? undefined : endMark);
  return seg.split('\n')
    .filter((l) => /^\|\s*(20\d\d|待公布)/.test(l))
    .map((l) => {
      const c = cells(l);
      return { date: c[0] || '', market: c[1] || '', event: c[2] || '', note: c[3] || '', grade: c[4] || '' };
    });
}

/** 解析政策状态列，找出草案条目。 */
export function readPolicyStatus(root) {
  const out = [];
  for (const name of POLICY_FILES) {
    const path = join(root, 'knowledge', name);
    if (!existsSync(path)) continue;
    for (const [i, line] of norm(readFileSync(path, 'utf8')).split('\n').entries()) {
      if (!/^\|/.test(line) || /^\|\s*-/.test(line)) continue;
      const c = cells(line);
      if (c.length < 7 || !c[5]) continue;
      if (c[0] === '文号' || c[5] === '状态') continue; // 分组重复的表头行
      out.push({ file: name, line: i + 1, doc: c[1], status: c[5], note: c[2], date: c[4] });
    }
  }
  return out;
}

/** 扫描一个模块正文的可信度标记，产出可用于过滤的计数与算例章节标题。 */
export function scanMarks(text) {
  const lines = norm(text).split('\n');
  const marks = { gradeC: 0, draft: 0, pending: 0, example: 0 };
  const exampleSections = [];
  for (const line of lines) {
    if (GRADE_C_RE.test(line)) marks.gradeC += 1;
    if (DRAFT_RE.test(line)) marks.draft += 1;
    if (/待核实|待复核|未定|待公布|to be verified/i.test(line)) marks.pending += 1;
    if (/算例|示例|例题|worked example/i.test(line)) marks.example += 1;
    if (EXAMPLE_HEAD_RE.test(line)) exampleSections.push(line.trim());
  }
  return { marks, exampleSections };
}

function inferConfidence(fm, marks, level) {
  if (fm?.confidence) return { value: fm.confidence, inferred: false };
  if (fm?.historical === true || fm?.historical === 'true') return { value: 'historical', inferred: true };
  if (level === 'research') return { value: 'historical', inferred: true };
  if (marks.draft > 0 || marks.pending > 0 || marks.gradeC > 0) return { value: 'mixed', inferred: true };
  return { value: 'verified', inferred: true };
}

/** 生成完整机器可读索引（幂等：不含时间戳）。 */
export function buildIndex(root) {
  const dir = join(root, 'knowledge');
  const ledger = readGradeCLedger(root);
  const open = readOpenItems(root);
  const events = readEvents(root);
  const policies = readPolicyStatus(root);
  const gaps = readGaps(root);
  const keyFigures = readKeyFigures(root);
  const openItemDues = readOpenItemDues(root);
  const glossary = readGlossary(root);
  const modules = [];
  for (const file of readdirSync(dir).filter((f) => f.endsWith('.md')).sort()) {
    const text = norm(readFileSync(join(dir, file), 'utf8'));
    const fm = parseFrontmatter(text) || {};
    const body = text.slice(text.indexOf('\n---\n', 4) + 5);
    const { marks, exampleSections } = scanMarks(body);
    const confidence = inferConfidence(fm, marks, fm.level);
    modules.push({
      id: fm.id || '',
      file,
      title: fm.title || '',
      level: fm.level || '',
      kind: fm.kind || '',
      cutoff: fm.cutoff || '',
      confidence: confidence.value,
      confidenceInferred: confidence.inferred,
      examples: fm.examples || null,
      historical: fm.historical === true || fm.historical === 'true',
      summaryEn: fm.summary_en || null,
      titleEn: fm.title_en || null,
      marks,
      exampleSections,
    });
  }
  return {
    schema: 1,
    description: 'Machine-readable credibility register. Filter modules by confidence/examples/historical before injecting into a model; gradeC and openItems carry the unverified figures and undecided items.',
    summary: {
      modules: modules.length,
      gradeCItems: ledger.rows.length,
      openItems: open.items.length,
      events: events.length,
      draftPolicies: policies.filter((p) => /草案|征求意见/.test(p.status)).length,
      mixedModules: modules.filter((m) => m.confidence === 'mixed').length,
      historicalModules: modules.filter((m) => m.confidence === 'historical').length,
      unverifiedGradeC: ledger.rows.filter((r) => r.pending).length,
      verifiedTickets: ledger.rows.filter((r) => r.usable).length,
      bannedTickets: ledger.rows.filter((r) => r.banned).length,
      ticketsDueForReview: ledger.rows.filter((r) => r.pending && r.nextReview).length,
      openGaps: gaps.length,
      englishSummaries: modules.filter((m) => m.summaryEn).length,
      keyFigures: keyFigures.length,
      glossaryTerms: glossary.defined.length,
      controlledAbbreviations: glossary.controlled.length,
      openItemDues: openItemDues.length,
    },
    enums: { confidence: CONFIDENCE, examples: EXAMPLE_MODES, policyStatus: POLICY_STATUS, priority: PRIORITIES, ticketStatus: TICKET_STATUS },
    gradeC: ledger.rows,
    gaps,
    keyFigures,
    openItems: open.items,
    openItemDues,
    glossary: { defined: glossary.defined, controlled: glossary.controlled },
    events,
    policyDrafts: policies.filter((p) => /草案|征求意见/.test(p.status)),
    modules,
  };
}

export function serializeIndex(index) {
  return `${JSON.stringify(index, null, 2)}\n`;
}

/**
 * 内容级门禁。只检查「结构化对象」，不对散文做语义猜测——
 * 实测散文里 22 处「草案 + 现行」共现全部是正确的对照说明，479 行标记仅 54 行带入口，
 * 若按行扫描会全量误报。
 */
export function checkContent(root) {
  const errors = [];
  const warnings = [];
  const push = (file, line, msg) => errors.push(`${file}${line ? `:${line}` : ''}: ${msg}`);
  const index = buildIndex(root);
  const dir = join(root, 'knowledge');

  // C1 frontmatter 声明字段必须是合法枚举值。
  for (const m of index.modules) {
    const text = norm(readFileSync(join(dir, m.file), 'utf8'));
    const fm = parseFrontmatter(text) || {};
    if (fm.confidence !== undefined && !CONFIDENCE.includes(fm.confidence)) {
      push(`knowledge/${m.file}`, 1, `confidence 非法：${fm.confidence}（应为 ${CONFIDENCE.join(' / ')}）`);
    }
    if (fm.examples !== undefined && !EXAMPLE_MODES.includes(fm.examples)) {
      push(`knowledge/${m.file}`, 1, `examples 非法：${fm.examples}（应为 ${EXAMPLE_MODES.join(' / ')}）`);
    }
    if (fm.historical !== undefined && !['true', 'false', true, false].includes(fm.historical)) {
      push(`knowledge/${m.file}`, 1, `historical 需要是 true / false`);
    }
    if (fm.historical === true || fm.historical === 'true') {
      if (!HISTORY_DECL_RE.test(text.slice(0, 2000))) {
        push(`knowledge/${m.file}`, 1, 'historical: true 但正文首屏缺少「数据时点/成书/史料」声明');
      }
      if (fm.confidence && fm.confidence !== 'historical') {
        push(`knowledge/${m.file}`, 1, 'historical: true 与 confidence 不一致');
      }
    }
    // C5 算例必须标 D：章节标题未标合成的模块必须显式声明 examples。
    const unmarked = m.exampleSections.filter((h) => !EXAMPLE_MARKED_RE.test(h));
    if (unmarked.length && !fm.examples) {
      push(`knowledge/${m.file}`, 1, `${unmarked.length} 个算例章节未标「合成 / D 级」，且 frontmatter 未声明 examples: synthetic|documented`);
    }
    if (fm.examples === 'synthetic' && !/合成|synthetic|仅演示|方法演示|示意，D 级|D 级经验|（D 级|\(D\)/i.test(text)) {
      push(`knowledge/${m.file}`, 1, 'examples: synthetic 但正文没有「合成 / 仅演示 / D 级算例」声明');
    }
    // C6 模块级声明与推断不一致时给提醒（不阻塞）。
    if (!m.confidenceInferred && m.confidence === 'verified' && m.marks.pending > 0) {
      warnings.push(`knowledge/${m.file}: confidence: verified，但正文有 ${m.marks.pending} 行「待核实 / 未定」`);
    }
  }

  // C2/C3 C 级登记册：行数、列数、复核入口、优先级、销项终态与下次复核日。
  const ledger = readGradeCLedger(root);
  if (ledger.error) push('knowledge/' + SNAPSHOT, 0, ledger.error);
  const rows = ledger.rows;
  if (!rows.length) push('knowledge/' + SNAPSHOT, 0, '§5 C 级工单表为空');
  const nums = new Set();
  for (const r of rows) {
    const at = `knowledge/${SNAPSHOT}#gradeC-${r.n}`;
    if (nums.has(r.n)) push(at, 0, `工单编号重复：${r.n}`);
    nums.add(r.n);
    if (r.columns !== TICKET_COLUMNS) {
      push(at, 0, `工单列数 ${r.columns} != ${TICKET_COLUMNS}（数字 / 所在模块 / 为什么是 C / 复核入口 / 优先级 / 状态 / 复核日期 / 结论·引用禁令）`);
    }
    if (!r.figure) push(at, 0, '工单缺少数字描述');
    if (!r.source) push(at, 0, 'C 级数字缺少复核入口');
    else if (!/`[^`]+`|https?:\/\//.test(r.source)) push(at, 0, `复核入口不是可查证来源：${r.source}`);
    if (!PRIORITIES.includes(r.priority)) push(at, 0, `优先级非法：${r.priority}`);
    if (!TICKET_STATUS.includes(r.status)) push(at, 0, `销项状态非法：${r.status}（应为 ${TICKET_STATUS.join(' / ')}）`);
    if (!r.conclusion) push(at, 0, '工单缺少结论 / 引用禁令');
    if (r.pending) {
      if (r.reviewedAt && r.reviewedAt !== '—') push(at, 0, '待复核工单不得填写复核日期');
      if (!r.nextReview) push(at, 0, '待复核工单必须在结论里写明「下次复核 YYYY-MM-DD」');
    } else {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(r.reviewedAt)) push(at, 0, '已销项工单必须有复核日期 YYYY-MM-DD');
    }
    if (r.banned && !/禁止|不得|撤销|未发布|不得把/.test(r.conclusion)) {
      push(at, 0, '已撤销 / 禁止引用工单必须在结论里写明引用禁令');
    }
  }
  for (let n = 1; n <= rows.length; n += 1) {
    if (!nums.has(n)) push('knowledge/' + SNAPSHOT, 0, `工单编号不连续，缺 #${n}`);
  }

  // C2b 空缺清单：每个「待核实」格都要有优先级与下次复核日，避免补数节奏悬空。
  const gaps = readGaps(root);
  if (!gaps.length) push('knowledge/' + SNAPSHOT, 0, '§1.4 空缺清单为空（应保留条目并顺延日期，而不是删表）');
  for (const g of gaps) {
    if (g.columns !== 6) push('knowledge/' + SNAPSHOT + '#gaps', 0, `空缺清单列数 ${g.columns} != 6`);
    if (!PRIORITIES.includes(g.priority) && !['P0', 'P1', 'P2'].includes(g.priority)) {
      push('knowledge/' + SNAPSHOT + '#gaps', 0, `空缺优先级非法：${g.priority}`);
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(g.nextReview)) {
      push('knowledge/' + SNAPSHOT + '#gaps', 0, `空缺格「${g.gap}」缺少下次复核日期`);
    }
  }

  // C4 草案不得当现行：政策状态列枚举 + 草案条目的要点不得写成已生效。
  for (const p of readPolicyStatus(root)) {
    if (!POLICY_STATUS.includes(p.status)) {
      push(`knowledge/${p.file}`, p.line, `政策状态非法：${p.status}（应为 ${POLICY_STATUS.join(' / ')}）`);
    }
    if (/草案|征求意见/.test(p.status) && /已施行|已生效|已实施|现行有效|正式施行/.test(p.note)) {
      push(`knowledge/${p.file}`, p.line, `草案条目不得写成已生效：${p.doc}`);
    }
  }

  // C7 Open items 编号必须连续，且每条要有明确的不确定性措辞。
  const open = readOpenItems(root);
  if (open.error) push('knowledge/' + INDEX_EN, 0, open.error);
  for (let n = 1; n <= open.items.length; n += 1) {
    if (open.items[n - 1]?.n !== n) {
      push('knowledge/' + INDEX_EN, 0, `Open items 编号不连续，第 ${n} 条缺失`);
      break;
    }
  }

  // C8 事件日历日期必须可解析（完整日期或年月）。
  for (const e of readEvents(root)) {
    if (!/^20\d\d/.test(e.date) && !/^待公布/.test(e.date)) {
      push('knowledge/' + SNAPSHOT, 0, `事件日历日期无法解析：${e.date}`);
    }
    if (/^待公布/.test(e.date) && !/空缺|禁止|复核/.test(e.grade)) {
      push('knowledge/' + SNAPSHOT, 0, `事件「${e.event}」日期待公布，级别列必须写明空缺/禁令/复核日`);
    }
  }

  // C9 English layer: every module must carry a summary_en so the digest is complete.
  for (const m of index.modules) {
    if (!m.summaryEn) push(`knowledge/${m.file}`, 1, '缺少 summary_en（English digest 需要每个模块都有英文摘要）');
  }

  // C10 Glossary: controlled abbreviations must be defined and actually used elsewhere.
  const gloss = readGlossary(root);
  if (gloss.error) push('knowledge/' + GLOSSARY, 0, gloss.error);
  const defined = new Set(gloss.defined.map((d) => d.term));
  for (const d of gloss.defined) {
    if (!d.definition || !d.confusion) {
      push('knowledge/' + GLOSSARY, 0, `术语「${d.term}」缺少定义或易混项`);
    }
  }
  const seenCtl = new Set();
  let corpus = '';
  for (const m of index.modules) {
    if (m.file === GLOSSARY) continue;
    corpus += norm(readFileSync(join(dir, m.file), 'utf8'));
  }
  for (const term of gloss.controlled) {
    if (seenCtl.has(term)) push('knowledge/' + GLOSSARY, 0, `受控缩写重复：${term}`);
    seenCtl.add(term);
    if (!defined.has(term)) push('knowledge/' + GLOSSARY, 0, `受控缩写「${term}」没有定义表条目`);
    if (!corpus.includes(term)) push('knowledge/' + GLOSSARY, 0, `受控缩写「${term}」未在任何其它模块出现（字典悬空）`);
  }

  // C11 Open-item due register: valid dates, 5 columns, ids must exist in §4.
  const dues = readOpenItemDues(root);
  if (!dues.length) push('knowledge/' + INDEX_EN, 0, '§4.1 未定事项到期登记册为空');
  const openNums = new Set(open.items.map((i) => i.n));
  for (const d of dues) {
    if (d.columns !== 5) push('knowledge/' + INDEX_EN + '#due', 0, `到期登记册 #${d.n} 列数 ${d.columns} != 5`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d.due)) push('knowledge/' + INDEX_EN + '#due', 0, `到期登记册 #${d.n} 日期非法：${d.due}`);
    if (!openNums.has(d.n)) push('knowledge/' + INDEX_EN + '#due', 0, `到期登记册 #${d.n} 在 §4 Open items 里不存在`);
    if (!d.source) push('knowledge/' + INDEX_EN + '#due', 0, `到期登记册 #${d.n} 缺少查证入口`);
  }

  return { errors, warnings, index };
}
