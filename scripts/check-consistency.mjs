#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';

const root = resolve(process.argv[2] ?? process.cwd());
const errors = [];
const fail = (file, line, message) => errors.push(`${relative(root, file)}:${line}: ${message}`);

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    if (name === '.git' || name === 'node_modules') continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (name.endsWith('.md')) out.push(full);
  }
  return out;
}

const files = walk(root);

function read(file) {
  return readFileSync(file, 'utf8');
}

function countPipes(line) {
  let n = 0;
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] === '|' && line[i - 1] !== '\\') n += 1;
  }
  return n;
}

// 1. Tables need blank lines around them and consistent column counts.
for (const file of files) {
  const lines = read(file).split('\n');
  let inTable = false;
  let columns = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (/^\s*\|/.test(line)) {
      if (!inTable) {
        if (i > 0 && lines[i - 1].trim() !== '') {
          fail(file, i + 1, 'table must be preceded by a blank line');
        }
        inTable = true;
        columns = countPipes(line);
      } else if (countPipes(line) !== columns) {
        fail(file, i + 1, `table column count ${countPipes(line)} != header ${columns}`);
      }
    } else if (inTable) {
      if (line.trim() !== '') {
        fail(file, i + 1, 'table must be followed by a blank line');
      }
      inTable = false;
    }
  }
}

// 2. Relative links and knowledge/ file references must resolve.
for (const file of files) {
  const lines = read(file).split('\n');
  lines.forEach((line, i) => {
    for (const match of line.matchAll(/\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
      let target = match[1];
      if (/^(https?:|mailto:|#|<)/.test(target)) continue;
      const hash = target.indexOf('#');
      if (hash >= 0) target = target.slice(0, hash);
      if (!target) continue;
      const path = resolve(dirname(file), decodeURI(target));
      if (!existsSync(path)) fail(file, i + 1, `broken link: ${match[1]}`);
    }
    for (const match of line.matchAll(/`((?:knowledge|skills)\/[\w\u4e00-\u9fa5\-./]+\.md)`/g)) {
      const path = resolve(root, match[1]);
      if (!existsSync(path)) fail(file, i + 1, `missing referenced file: ${match[1]}`);
    }
  });
}

// 3. Version markers.
const versioned = [
  ...files.filter((f) => /[\\/]skills[\\/].*SKILL(_EN)?\.md$/.test(f)),
  ...files.filter((f) => /[\\/]README(_EN)?\.md$/.test(f) && dirname(f) === root),
];
for (const file of versioned) {
  const text = read(file);
  if (!/v1\.2/.test(text)) fail(file, 1, 'missing current version marker v1.2');
  if (/v1\.1\s*[（(]\s*(updated|更新)/i.test(text)) {
    fail(file, 1, 'stale version header v1.1');
  }
}

// 4. Key numbers must appear in both the Chinese and English skill of the same domain.
const parity = [
  { name: 'VPP projects', cn: /470 个/, en: /470 (VPP )?projects/ },
  { name: 'VPP measured capability', cn: /1685 万 kW/, en: /16\.85 (GW|million kW)/ },
  { name: 'medium/long-term turnover', cn: /6\.3522/, en: /6\.3522/ },
  { name: 'PJM 2027/28', cn: /329\.17/, en: /329\.17/ },
  { name: 'PJM 2028/29', cn: /325 美元\/MW·日/, en: /325 USD\/MW-day|USD 325\/MW-day|325\/MW-day/ },
  { name: 'Tianjin capacity price', cn: /231 元\/kW·年/, en: /231 CNY\/kW·yr|CNY 231\/kW·yr/ },
  { name: 'Guangxi capacity price', cn: /247\.5/, en: /247\.5/ },
  { name: 'Liaoning reliable capacity', cn: /辽宁[^\n]{0,20}370/, en: /Liaoning[^\n]{0,80}370|370[^\n]{0,40}reliable/ },
  { name: 'Hongyanhe unit 1-4', cn: /0\.3823/, en: /0\.3823/ },
  { name: 'Hongyanhe unit 5-6', cn: /0\.3749/, en: /0\.3749/ },
  { name: 'Liaoning 2027 auction volume', cn: /53\.08 亿/, en: /5\.308 billion/ },
  { name: 'Jiangxi 2027 auction volume', cn: /40\.8 亿/, en: /4\.08 billion/ },
  { name: 'Fujian 2027 auction volume', cn: /83\.6 亿/, en: /8\.36 billion/ },
  { name: 'Guangdong 2027 auction volume', cn: /79\.34 亿/, en: /7\.934 billion/ },
  { name: 'Shenzhen connected capacity', cn: /475 万 kW/, en: /4\.75 GW/ },
];

const skillPairs = [
  ['skills/virtual-power-plant/SKILL.md', 'skills/virtual-power-plant/SKILL_EN.md'],
  ['skills/electricity-trading-expert/SKILL.md', 'skills/electricity-trading-expert/SKILL_EN.md'],
];
for (const [cnRel, enRel] of skillPairs) {
  const cnFile = join(root, cnRel);
  const enFile = join(root, enRel);
  if (!existsSync(cnFile) || !existsSync(enFile)) {
    fail(cnFile, 1, 'missing Chinese/English skill pair');
    continue;
  }
  const cn = read(cnFile);
  const en = read(enFile);
  for (const item of parity) {
    const cnHas = item.cn.test(cn);
    const enHas = item.en.test(en);
    if (cnHas && !enHas) fail(enFile, 1, `missing counterpart for ${item.name}`);
    if (enHas && !cnHas) fail(cnFile, 1, `missing counterpart for ${item.name}`);
  }
}

// 5. Stale strings that were corrected in v1.2 (current-state files only;
//    incremental research notes keep historical wording on purpose).
const stale = [
  { re: /4\.81\s*万亿/, allow: /口径|更正|不是|旧|→/, note: '4.81 trillion is a subset, not the national total' },
  { re: /0\.27\s*万亿/, allow: /口径|更正|不是|旧|→/, note: 'green power is 0.3285 trillion kWh' },
  { re: /329\.17[^\n]{0,40}2028\/29|2028\/29[^\n]{0,40}329\.17/, allow: /不是|非|标成|更正|not|Labeling/i, note: '329.17 is 2027/28, not 2028/29' },
  { re: /浙江[^\n]{0,20}（2025-04）/, allow: /1\.0|历史/, note: 'Zhejiang rules were revised on 2026-09-23' },
  { re: /云南[^\n]{0,20}2026 年新增/, allow: /更正|框架/, note: 'Yunnan framework dates from 2025-10-01' },
];
const currentFiles = files.filter((file) => {
  const rel = relative(root, file).split('\\').join('/');
  if (rel.startsWith('skills/')) return true;
  if (rel === 'README.md' || rel === 'README_EN.md') return true;
  if (rel.startsWith('knowledge/') && !/2026-(09|10)增量/.test(rel)) return true;
  return false;
});
for (const file of currentFiles) {
  const lines = read(file).split('\n');
  lines.forEach((line, i) => {
    for (const rule of stale) {
      if (rule.re.test(line) && !(rule.allow && rule.allow.test(line))) {
        fail(file, i + 1, `stale string: ${rule.note}`);
      }
    }
  });
}

if (errors.length) {
  console.error(`Consistency check failed with ${errors.length} issue(s):\n`);
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
console.log(`Consistency check passed: ${files.length} Markdown files.`);
