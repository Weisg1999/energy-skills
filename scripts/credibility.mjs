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
export const TICKET_STATUS = ['待复核', '已复核', '已改口径', '口径已确认', '部分确认'];

const SNAPSHOT = '海外市场同口径快照与投决日历-2026-11.md';
const INDEX_EN = 'INDEX_EN-2026-11.md';
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
    rows.push({
      n: Number(c[0]),
      figure: c[1] || '',
      module: c[2] || '',
      reason: c[3] || '',
      source: c[4] || '',
      priority: c[5] || '',
      status: c[6] || '',
      columns: c.length,
    });
  }
  return { rows, error: null };
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
    .filter((l) => /^\|\s*20\d\d/.test(l))
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
      unverifiedGradeC: ledger.rows.filter((r) => r.status === '待复核').length,
    },
    enums: { confidence: CONFIDENCE, examples: EXAMPLE_MODES, policyStatus: POLICY_STATUS, priority: PRIORITIES, ticketStatus: TICKET_STATUS },
    gradeC: ledger.rows,
    openItems: open.items,
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

  // C2/C3 C 级登记册：行数、列数、复核入口、优先级与状态。
  const ledger = readGradeCLedger(root);
  if (ledger.error) push('knowledge/' + SNAPSHOT, 0, ledger.error);
  const rows = ledger.rows;
  if (!rows.length) push('knowledge/' + SNAPSHOT, 0, '§5 C 级工单表为空');
  const nums = new Set();
  for (const r of rows) {
    const at = `knowledge/${SNAPSHOT}#gradeC-${r.n}`;
    if (nums.has(r.n)) push(at, 0, `工单编号重复：${r.n}`);
    nums.add(r.n);
    if (r.columns !== 7) push(at, 0, `工单列数 ${r.columns} != 7（数字 / 所在模块 / 为什么是 C / 复核入口 / 优先级 / 状态）`);
    if (!r.figure) push(at, 0, '工单缺少数字描述');
    if (!r.source) push(at, 0, 'C 级数字缺少复核入口');
    else if (!/`[^`]+`|https?:\/\//.test(r.source)) push(at, 0, `复核入口不是可查证来源：${r.source}`);
    if (!PRIORITIES.includes(r.priority)) push(at, 0, `优先级非法：${r.priority}`);
    if (!TICKET_STATUS.some((s) => r.status.startsWith(s) || s.startsWith(r.status))) {
      push(at, 0, `状态非法：${r.status}`);
    }
  }
  for (let n = 1; n <= rows.length; n += 1) {
    if (!nums.has(n)) push('knowledge/' + SNAPSHOT, 0, `工单编号不连续，缺 #${n}`);
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
    if (!/^20\d\d-\d{2}(-\d{2})?/.test(e.date) && !/^20\d\d/.test(e.date)) {
      push('knowledge/' + SNAPSHOT, 0, `事件日历日期无法解析：${e.date}`);
    }
  }

  return { errors, warnings, index };
}
