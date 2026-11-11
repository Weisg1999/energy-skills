#!/usr/bin/env node
/**
 * 把「更新清单.md」的到期判断从人工翻表变成可跑的看板 + 结构门禁。
 *
 * 用法：
 *   node scripts/check-maintenance.mjs                  # 打印到期看板（提醒不阻塞）
 *   node scripts/check-maintenance.mjs --check         # 只校验清单结构，失败退出码 1（供 CI）
 *   node scripts/check-maintenance.mjs --date 2026-12-01   # 用指定日期演算
 *   node scripts/check-maintenance.mjs --json          # 机器可读输出
 *
 * 设计：本脚本只读更新清单，不改它。清单仍是人工判断层；脚本负责让判断
 * 「可计算、可校验」——数量漂移、断链、重复登记、cutoff 不一致都会立刻暴露。
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildIndex, parseFrontmatter } from './credibility.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const listPath = join(root, '更新清单.md');
const knowledgeDir = join(root, 'knowledge');
const norm = (s) => String(s).replace(/\r\n?/g, '\n');

const argv = process.argv.slice(2);
const checkMode = argv.includes('--check');
const jsonMode = argv.includes('--json');
const dateArg = argv.indexOf('--date');
const today = dateArg >= 0 && argv[dateArg + 1] ? argv[dateArg + 1] : new Date().toLocaleDateString('sv-SE');

const toTime = (s) => {
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return null;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
};
const daysBetween = (a, b) => Math.round((toTime(b) - toTime(a)) / 86400000);

const text = norm(readFileSync(listPath, 'utf8'));
const errors = [];
const fail = (line, msg) => errors.push(`更新清单.md:${line}: ${msg}`);

/* ------------------------------------------------------- §一 到期节奏表 */
const schedule = [];
const headStart = text.indexOf('## 一、到期判断');
const headEnd = text.indexOf('\n## ', headStart + 4);
const headSeg = text.slice(headStart, headEnd === -1 ? undefined : headEnd);
for (const [i, line] of headSeg.split('\n').entries()) {
  const c = line.split('|').slice(1, -1).map((s) => s.trim());
  if (c.length < 3 || c[0] === '级别' || /^-+$/.test(c[0])) continue;
  const due = c[2].match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null;
  if (!/^(P0|P1|P2|P3)$/.test(c[0]) && due) {
    fail(i + 1, `到期表出现未识别级别：${c[0]}`);
  }
  if (due && toTime(due) === null) fail(i + 1, `下次到期日期无法解析：${c[2]}`);
  schedule.push({ level: c[0], cadence: c[1], due, risk: c[3] || '' });
}

/* -------------------------------------------------- §二～§八 模块登记表 */
const sections = [];
const secRe = /^## ([二三四五六七八])、([^\n]+)$/gm;
const heads = [...text.matchAll(secRe)];
for (const [idx, h] of heads.entries()) {
  const segStart = h.index + h[0].length;
  const segEnd = idx + 1 < heads.length ? heads[idx + 1].index : text.length;
  const seg = text.slice(segStart, segEnd);
  const declared = Number(h[2].match(/（(\d+) 个）/)?.[1] ?? NaN);
  const due = seg.match(/到期日\s*\*\*(\d{4}-\d{2}-\d{2})\*\*/)?.[1] ?? null;
  const rows = [];
  seg.split('\n').forEach((line, i) => {
    if (!/^\|\s*\[/.test(line)) return;
    const link = line.match(/\[([^\]]+)\]\((knowledge\/[^)]+\.md)\)/);
    if (!link) { fail(0, `${h[2]}：模块行缺少 knowledge/ 链接 -> ${line.slice(0, 60)}`); return; }
    const c = line.split('|').slice(1, -1).map((s) => s.trim());
    rows.push({ title: link[1], file: link[2].replace(/^knowledge\//, ''), cutoff: c[1] || '', line: segStart + i });
  });
  const level = h[2].match(/^(P0|P1|P2|P3)/)?.[1] ?? h[2].split('：')[0];
  sections.push({ num: h[1], title: h[2], level, declared, due, rows });
}

/* ------------------------------------------------------------ 结构校验 */
const seen = new Map();
for (const s of sections) {
  if (Number.isFinite(s.declared) && s.declared !== s.rows.length) {
    fail(0, `${s.title}：标题声明 ${s.declared} 个，表格实有 ${s.rows.length} 个`);
  }
  for (const r of s.rows) {
    const path = join(knowledgeDir, r.file);
    if (!existsSync(path)) { fail(0, `${s.title}：链接目标不存在 -> ${r.file}`); continue; }
    if (seen.has(r.file)) fail(0, `${r.file} 重复登记于「${seen.get(r.file)}」与「${s.title}」`);
    seen.set(r.file, s.title);
    const fm = parseFrontmatter(readFileSync(path, 'utf8')) || {};
    if (r.cutoff && r.cutoff !== '—' && fm.cutoff && !fm.cutoff.startsWith(r.cutoff)) {
      fail(0, `${r.file}：清单截止日 ${r.cutoff} 与 frontmatter cutoff ${fm.cutoff} 不一致`);
    }
  }
}
// 所有知识模块都应被登记（INDEX_EN 自身与政策索引类也应在表内）。
const allMd = readdirSync(knowledgeDir).filter((f) => f.endsWith('.md'));
const missing = allMd.filter((f) => !seen.has(f));
for (const f of missing) fail(0, `knowledge/${f} 未登记到任何复核级别`);

// 到期节奏与登记表要能对上。
for (const item of schedule.filter((s) => /^(P0|P1|P2|P3)$/.test(s.level))) {
  const sec = sections.find((s) => s.level === item.level);
  if (!sec) { fail(0, `到期表中的 ${item.level} 没有对应登记表`); continue; }
  if (sec.due && item.due && sec.due !== item.due) {
    fail(0, `${item.level} 到期日不一致：§一 ${item.due} vs ${sec.title} ${sec.due}`);
  }
}

/* -------------------------------------------------------------- 看板 */
const board = schedule.map((s) => {
  const days = s.due && toTime(today) !== null ? daysBetween(today, s.due) : null;
  const sec = sections.find((x) => x.level === s.level);
  return {
    level: s.level,
    cadence: s.cadence,
    due: s.due,
    days,
    state: days === null ? '不设到期' : days < 0 ? `已逾期 ${-days} 天` : days === 0 ? '今天到期' : `${days} 天后`,
    overdue: days !== null && days <= 0,
    modules: sec?.rows.length ?? 0,
  };
});
const overdue = board.filter((b) => b.overdue);

/* ---------- C 级工单与空缺格的销项节奏（来自 credibility.json 的同一事实源） ---------- */
const cred = buildIndex(root);
const isDue = (date) => date && toTime(today) !== null && toTime(date) !== null && daysBetween(today, date) <= 0;
const ticketsDue = cred.gradeC.filter((t) => t.pending && isDue(t.nextReview));
const gapsDue = cred.gaps.filter((g) => isDue(g.nextReview));
// INDEX_EN §4.1 的未定事项到期后自动进入 P0 复核队列。
const openItemsDue = cred.openItemDues.filter((d) => isDue(d.due));

if (jsonMode) {
  console.log(JSON.stringify({ today, board, sections: sections.map((s) => ({ title: s.title, level: s.level, declared: s.declared, actual: s.rows.length, due: s.due })), missing, errors, tickets: { total: cred.gradeC.length, pending: cred.summary.unverifiedGradeC, verified: cred.summary.verifiedTickets, banned: cred.summary.bannedTickets, due: ticketsDue.map((t) => ({ n: t.n, figure: t.figure, priority: t.priority, nextReview: t.nextReview })) }, gaps: { total: cred.gaps.length, due: gapsDue.map((g) => ({ priority: g.priority, gap: g.gap, target: g.target, nextReview: g.nextReview })) }, openItemsDue: openItemsDue.map((d) => ({ n: d.n, item: d.item, due: d.due, trigger: d.trigger })) }, null, 2));
} else if (!checkMode) {
  console.log(`更新清单到期看板 · 今天 ${today} · 盘点 ${seen.size}/${allMd.length} 个知识模块`);
  console.log('─'.repeat(76));
  for (const b of board) {
    const flag = b.overdue ? '[到期] ' : '        ';
    console.log(`${flag}${b.level.padEnd(4)} ${(b.cadence || '').padEnd(16)} ${String(b.due || '—').padEnd(12)} ${b.state.padEnd(14)} ${b.modules} 个模块`);
  }
  console.log('─'.repeat(76));
  if (overdue.length) {
    for (const b of overdue) {
      const sec = sections.find((s) => s.level === b.level);
      console.log(`[提醒] ${b.level} 已到期，待复核 ${sec?.rows.length ?? 0} 个模块：`);
      for (const r of sec?.rows ?? []) console.log(`   - ${r.title}（${r.file}）`);
    }
  } else {
    console.log('当前无到期级别。');
  }
  console.log(`可信度销项：${cred.gradeC.length} 项 C 级工单（已销项 ${cred.summary.verifiedTickets + cred.summary.bannedTickets}、待复核 ${cred.summary.unverifiedGradeC}）；§1.4 空缺格 ${cred.gaps.length} 项`);
  if (openItemsDue.length) {
    console.log(`[P0 触发] ${openItemsDue.length} 项未定事项已到触发日，进入本轮 P0 复核队列：`);
    for (const d of openItemsDue) console.log(`   - #${d.n} ${d.item}（${d.due}，${d.trigger}）`);
  }
  if (ticketsDue.length || gapsDue.length) {
    if (ticketsDue.length) {
      console.log(`[销项] ${ticketsDue.length} 项 C 级工单到期：`);
      for (const t of ticketsDue) console.log(`   - #${t.n} ${t.figure}（${t.priority}，下次复核 ${t.nextReview}）`);
    }
    if (gapsDue.length) {
      console.log(`[补数] ${gapsDue.length} 项空缺格到期：`);
      for (const g of gapsDue) console.log(`   - ${g.priority} ${g.gap} → ${g.target}（${g.nextReview}）`);
    }
  } else {
    console.log('当前无到期的工单或空缺格。');
  }
  if (!openItemsDue.length) console.log('当前无到期的未定事项触发日。');
  if (missing.length) console.log(`[注意] ${missing.length} 个模块未登记：${missing.join('、')}`);
}

if (errors.length) {
  if (checkMode) {
    console.error(`更新清单结构校验失败（${errors.length} 条）：`);
    for (const e of errors) console.error(`- ${e}`);
    process.exit(1);
  } else if (!jsonMode) {
    console.log(`[结构问题] ${errors.length} 条，运行 --check 查看详情`);
  }
} else if (checkMode) {
  console.log(`更新清单结构校验通过：${sections.length} 个级别、${seen.size} 个模块、${schedule.length} 条节奏；今天 ${today}，${overdue.length} 个级别已到期；C 级工单 ${cred.summary.unverifiedGradeC} 项待复核、空缺格 ${cred.gaps.length} 项、未定事项触发日 ${cred.openItemDues.length} 条，其中 ${ticketsDue.length + gapsDue.length + openItemsDue.length} 项今日到期。`);
}
