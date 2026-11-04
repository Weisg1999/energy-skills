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
  if (!/v1\.5/.test(text)) fail(file, 1, 'missing current version marker v1.5');
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

const pairParity = {
  'skills/carbon-asset-expert/SKILL.md': [
    { name: 'ETS coverage entities', cn: /3,680 家/, en: /3,680 entities/ },
    { name: 'ETS coverage emissions', cn: /83 亿吨/, en: /8\.3 billion tonnes/ },
    { name: 'CCER registered projects', cn: /44 个项目/, en: /44 projects/ },
    { name: 'CCER average price', cn: /86\.51/, en: /86\.51/ },
    { name: 'CCER break-even price', cn: /89\.61/, en: /89\.61/ },
    { name: 'pledge margin-call price', cn: /71\.25/, en: /71\.25/ },
    { name: '2025 compliance rate', cn: /99\.99%/, en: /99\.99%/ },
    { name: 'CEA August 2026 close', cn: /97\.90/, en: /97\.90/ },
    { name: 'CBAM first surrender', cn: /2027-09-30/, en: /2027-09-30/ },
    { name: 'under-surrender multiple', cn: /5-10 倍/, en: /5-10x/ },
    { name: 'compliance purchase cost', cn: /5,445\.3 万元/, en: /54\.453 million/ },
    { name: 'five-fold penalty', cn: /1\.35 亿元/, en: /135 million/ },
    { name: 'CCER project NPV', cn: /−309\.5 万元/, en: /3\.095 million/ },
    { name: 'CCER project IRR', cn: /6\.25%/, en: /6\.25%/ },
    { name: 'PCF cradle-to-grave total', cn: /12,400 kg/, en: /12,400 kg/ },
    { name: 'PCF intensity', cn: /12\.4 kg\/kg/, en: /12\.4 kg\/kg/ },
    { name: 'PCF cradle-to-gate', cn: /10\.78/, en: /10\.78/ },
    { name: 'PCF raw-material share', cn: /66\.1%/, en: /66\.1%/ },
    { name: 'PCF residual after 20% cut', cn: /9,920/, en: /9,920/ },
    { name: 'PCF offset cost', cn: /892\.8/, en: /892\.8/ },
    { name: 'ISO 14068 edition', cn: /14068:2026/, en: /14068:2026/ },
    { name: 'battery passport date', cn: /2027-02-18/, en: /2027-02-18/ },
    { name: 'Shanghai certification uplift', cn: /0\.5 个百分点/, en: /0\.5 percentage-point/ },
    { name: 'uplift in tonnes', cn: /4 万吨/, en: /40,000 t/ },
  ],
  'skills/storage-investment-operations/SKILL.md': [
    { name: 'Anhui capacity price', cn: /165 元\/kW·年/, en: /CNY 165\/kW-yr/ },
    { name: 'Gansu capacity price', cn: /330 元\/kW·年/, en: /CNY 330\/kW-yr/ },
    { name: '2 h capacity charge', cn: /550 万元/, en: /CNY 5\.5 million/ },
    { name: 'discharge per cycle', cn: /187\.62 MWh/, en: /187\.62 MWh/ },
    { name: 'charge per cycle', cn: /213\.20 MWh/, en: /213\.20 MWh/ },
    { name: 'annual net arbitrage', cn: /3,106\.9 万元/, en: /CNY 31\.069 million/ },
    { name: 'annual revenue example A', cn: /3,656\.9 万元/, en: /CNY 36\.569 million/ },
    { name: 'NPV example A', cn: /3,119\.4 万元/, en: /CNY 31\.194 million/ },
    { name: 'IRR example A', cn: /10\.47%/, en: /10\.47%/ },
    { name: 'payback example A', cn: /7\.40 年/, en: /7\.40 years/ },
    { name: 'LCOS incl charging', cn: /742\.24/, en: /742\.24/ },
    { name: 'LCOS excl charging', cn: /458\.15/, en: /458\.15/ },
    { name: 'DSCR example A', cn: /1\.53/, en: /1\.53/ },
    { name: 'no capacity price NPV', cn: /−411 万元/, en: /-CNY 4\.11 million/ },
    { name: 'Doc 1656 effective date', cn: /2026-03-01 施行/, en: /effective 2026-03-01/ },
    { name: 'Zhejiang spread cut', cn: /−28\.5%/, en: /-28\.5%/ },
    { name: 'Jiangsu spread change', cn: /0\.85→0\.65/, en: /0\.85 to 0\.65/ },
    { name: 'demand charge with overrun', cn: /520,000/, en: /520,000/ },
    { name: 'demand charge after shaving', cn: /400,000/, en: /400,000/ },
    { name: 'annual demand saving', cn: /144 万元/, en: /CNY 1\.44 million/ },
    { name: 'NPV example B', cn: /259\.5 万元/, en: /CNY 2\.595 million/ },
    { name: 'IRR example B', cn: /12\.59%/, en: /12\.59%/ },
    { name: 'payback example B', cn: /5\.52 年/, en: /5\.52 years/ },
    { name: 'co-located IRR zero cost', cn: /4\.98%/, en: /4\.98%/ },
    { name: 'co-located IRR with cost', cn: /0\.26%/, en: /0\.26%/ },
    { name: 'co-located revenue zero cost', cn: /471\.7 万元/, en: /CNY 4\.717 million/ },
    { name: 'co-located revenue with cost', cn: /336\.7 万元/, en: /CNY 3\.367 million/ },
    { name: 'frequency-regulation daily', cn: /15,900 元/, en: /CNY 15,900/ },
    { name: 'frequency-regulation annual', cn: /524\.7 万元/, en: /CNY 5\.247 million/ },
    { name: 'degradation sensitivity IRR', cn: /8\.47%/, en: /8\.47%/ },
    { name: 'augmentation energy', cn: /50 MWh/, en: /50 MWh/ },
    { name: 'equivalent cycles', cn: /325\.9/, en: /325\.9/ },
    { name: 'years to 80% SOH', cn: /13\.33 年/, en: /13\.33 years/ },
    { name: '2 h system tender range', cn: /0\.53–0\.86/, en: /0\.53-0\.86/ },
    { name: 'recent project tender range', cn: /0\.678–1\.199/, en: /0\.678-1\.199/ },
  ],
};

const skillPairs = [
  ['skills/virtual-power-plant/SKILL.md', 'skills/virtual-power-plant/SKILL_EN.md'],
  ['skills/electricity-trading-expert/SKILL.md', 'skills/electricity-trading-expert/SKILL_EN.md'],
  ['skills/spot-bidding-quant/SKILL.md', 'skills/spot-bidding-quant/SKILL_EN.md'],
  ['skills/carbon-asset-expert/SKILL.md', 'skills/carbon-asset-expert/SKILL_EN.md'],
  ['skills/storage-investment-operations/SKILL.md', 'skills/storage-investment-operations/SKILL_EN.md'],
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
  const pairItems = [...parity, ...(pairParity[cnRel] ?? [])];
  for (const item of pairItems) {
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
