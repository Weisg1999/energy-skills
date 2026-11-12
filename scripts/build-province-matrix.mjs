#!/usr/bin/env node
/**
 * 生成省级规则参数矩阵。
 *
 * 单一事实源：knowledge/data/province-params.json（33 个省级市场的结构化参数）
 * 生成位置：knowledge/省级市场状态表-2026-11.md 的 §一之二，两处标记之间。
 *
 * 用法：
 *   node scripts/build-province-matrix.mjs          # 写入生成块
 *   node scripts/build-province-matrix.mjs --check  # 只校验生成块是否最新
 *
 * 纪律：矩阵只做横向索引，具体条款以单省页为准；'—' 表示尚未逐省核实，
 * 不代表当地没有政策。改数只改 JSON，不要手改 Markdown 生成块。
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const knowledgeDir = join(root, 'knowledge');
const dataPath = join(knowledgeDir, 'data', 'province-params.json');
const docPath = join(knowledgeDir, '省级市场状态表-2026-11.md');
const BEGIN = '<!-- BEGIN GENERATED: province-params -->';
const END = '<!-- END GENERATED: province-params -->';
const checkMode = process.argv.includes('--check');

const STATUSES = new Set(['正式', '区域正式', '试运行', '未运行']);
const GRADES = new Set(['A', 'A/B', 'B', 'B/C', 'C']);
const FIELDS = ['province', 'page', 'order', 'status', 'statusNote', 'declare', 'clear', 'mtu', 'settlement', 'mechanism136', 'capacity', 'vpp', 'grade', 'cutoff'];

const fail = (message) => {
  console.error(`[province-matrix] ${message}`);
  process.exit(1);
};

const data = JSON.parse(readFileSync(dataPath, 'utf8'));
if (!Array.isArray(data.provinces) || data.provinces.length === 0) fail('provinces 必须是非空数组');
if (!/^\d{4}-\d{2}-\d{2}$/.test(data.cutoff ?? '')) fail('顶层 cutoff 必须是 YYYY-MM-DD');

const seen = new Set();
for (const [i, p] of data.provinces.entries()) {
  for (const field of FIELDS) {
    if (p[field] === undefined || p[field] === '') fail(`provinces[${i}] 缺少 ${field}`);
    if (typeof p[field] !== 'string' && field !== 'order') fail(`provinces[${i}].${field} 必须是字符串`);
    if (typeof p[field] === 'string' && /[|\r\n]/.test(p[field])) fail(`provinces[${i}].${field} 不得含竖线或换行`);
  }
  if (!Number.isInteger(p.order) || p.order < 1 || p.order > data.provinces.length) fail(`${p.province}: order 越界`);
  if (seen.has(p.order)) fail(`${p.province}: order 重复 ${p.order}`);
  seen.add(p.order);
  if (!STATUSES.has(p.status)) fail(`${p.province}: status 必须是 ${[...STATUSES].join(' / ')}`);
  if (!GRADES.has(p.grade)) fail(`${p.province}: grade 必须是 ${[...GRADES].join(' / ')}`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(p.cutoff)) fail(`${p.province}: cutoff 必须是 YYYY-MM-DD`);
  if (!existsSync(join(knowledgeDir, p.page))) fail(`${p.province}: 单省页不存在 -> ${p.page}`);
}
for (let n = 1; n <= data.provinces.length; n += 1) {
  if (!seen.has(n)) fail(`order 不连续：缺少 ${n}`);
}

const rows = [...data.provinces].sort((a, b) => a.order - b.order);
const cell = (value) => String(value);
const name = (p) => `[${p.province}](${p.page})`;
const status = (p) => `**${p.status}** · ${p.statusNote}`;

const table = (header, body) => [
  `| ${header.join(' | ')} |`,
  `|${header.map(() => '---').join('|')}|`,
  ...body.map((cells) => `| ${cells.join(' | ')} |`),
].join('\n');

const tableA = table(
  ['省份', '现货状态', '申报限价（元/MWh）', '出清限价（元/MWh）', '出清粒度', '结算/偏差', '级别'],
  rows.map((p) => [name(p), status(p), cell(p.declare), cell(p.clear), cell(p.mtu), cell(p.settlement), cell(p.grade)]),
);

const tableB = table(
  ['省份', '136 机制电价（已核，原页单位）', '容量/储能（原页口径）', 'VPP 门槛', '级别', '截止'],
  rows.map((p) => [name(p), cell(p.mechanism136), cell(p.capacity), cell(p.vpp), cell(p.grade), cell(p.cutoff)]),
);

const block = [
  BEGIN,
  '',
  '### A. 现货与结算',
  '',
  tableA,
  '',
  '### B. 机制与主体',
  '',
  tableB,
  '',
  END,
].join('\n');

const doc = readFileSync(docPath, 'utf8').replace(/\r\n?/g, '\n');
const beginAt = doc.indexOf(BEGIN);
const endAt = doc.indexOf(END);
if (beginAt === -1 || endAt === -1 || endAt < beginAt) {
  fail(`未找到生成标记。请先在 ${docPath} 的 §一之二 放入 ${BEGIN} / ${END}`);
}
const current = doc.slice(beginAt, endAt + END.length);

if (checkMode) {
  if (current !== block) {
    console.error('[province-matrix] 生成块不是最新。运行 node scripts/build-province-matrix.mjs 重建。');
    process.exit(1);
  }
  console.log(`[province-matrix] 生成块已是最新：${rows.length} 个省级市场。`);
} else {
  if (current !== block) {
    writeFileSync(docPath, doc.slice(0, beginAt) + block + doc.slice(endAt + END.length), 'utf8');
    console.log(`[province-matrix] 已更新 ${docPath}：${rows.length} 个省级市场。`);
  } else {
    console.log(`[province-matrix] 无变化：${rows.length} 个省级市场。`);
  }
}

const count = (statusName) => rows.filter((p) => p.status === statusName).length;
console.log(`[province-matrix] 正式 ${count('正式')} / 区域正式 ${count('区域正式')} / 试运行 ${count('试运行')} / 未运行 ${count('未运行')}；数据截止 ${data.cutoff}。`);
