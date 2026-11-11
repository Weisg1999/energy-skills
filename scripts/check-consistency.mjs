#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { checkContent } from './credibility.mjs';

const root = resolve(process.argv[2] ?? process.cwd());
const errors = [];
const fail = (file, line, message) => errors.push(`${relative(root, file)}:${line}: ${message}`);

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    if (name === '.git' || name === 'node_modules' || name === '.workbuddy') continue;
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
  ...files.filter((f) => /[\\/]CHANGELOG(_EN)?\.md$/.test(f) && dirname(f) === root),
];
for (const file of versioned) {
  const text = read(file);
  if (!/v1\.9/.test(text)) fail(file, 1, 'missing current version marker v1.9');
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
  'skills/renewable-project-development/SKILL.md': [
    { name: 'P90 example', cn: /2,153\.93/, en: /2,153\.93/ },
    { name: 'wind capacity factor', cn: /27\.40%/, en: /27\.40%/ },
    { name: 'Weibull screening', cn: /27\.92%/, en: /27\.92%/ },
    { name: 'PV specific yield', cn: /1,407\.12/, en: /1,407\.12/ },
    { name: 'LCOE onshore wind', cn: /252\.80/, en: /252\.80/ },
    { name: 'LCOE utility PV', cn: /283\.94/, en: /283\.94/ },
    { name: 'LCOE offshore wind', cn: /446\.43/, en: /446\.43/ },
    { name: 'Example A total revenue', cn: /6,774\.48 万元/, en: /CNY 67\.7448 million/ },
    { name: 'effective price', cn: /0\.285/, en: /0\.285/ },
    { name: 'Example A NPV', cn: /596\.3 万元/, en: /CNY 5\.963 million/ },
    { name: 'Example A IRR', cn: /8\.18%/, en: /8\.18%/ },
    { name: 'Example A payback', cn: /9\.55 年/, en: /9\.55 years/ },
    { name: 'Example A DSCR', cn: /1\.76/, en: /1\.76/ },
    { name: 'low-price NPV', cn: /−5,893\.1 万元/, en: /−CNY 58\.931 million/ },
    { name: 'low-price IRR', cn: /6\.15%/, en: /6\.15%/ },
    { name: 'combined stress NPV', cn: /−9,404\.85 万元/, en: /−CNY 94\.0485 million/ },
    { name: 'combined stress IRR', cn: /5\.28%/, en: /5\.28%/ },
    { name: 'pre-tax break-even', cn: /245\.43/, en: /245\.43/ },
    { name: 'after-tax 8% break-even', cn: /294\.85/, en: /294\.85/ },
    { name: 'capture price wind', cn: /0\.279/, en: /0\.279/ },
    { name: 'Zhejiang first auction', cn: /0\.3816/, en: /0\.3816/ },
    { name: 'Gansu wind auction', cn: /0\.2440/, en: /0\.2440/ },
    { name: 'existing/incremental cutoff', cn: /2025-06-01/, en: /2025-06-01/ },
    { name: 'capacity price exclusion', cn: /新能源配储不执行容量电价/, en: /co-located storage does not receive a capacity price/ },
  ],
  'skills/ems-dispatch/SKILL.md': [
    { name: 'storage net energy', cn: /91,352\.24/, en: /91,352\.24/ },
    { name: 'storage capacity payment', cn: /15,068\.49/, en: /15,068\.49/ },
    { name: 'storage total', cn: /106,420\.74/, en: /106,420\.74/ },
    { name: 'storage with auxiliary', cn: /103,540\.74/, en: /103,540\.74/ },
    { name: 'storage RTE 85%', cn: /88,420\.85/, en: /88,420\.85/ },
    { name: '4h capacity payment', cn: /30,136\.99/, en: /30,136\.99/ },
    { name: '95% availability payment', cn: /14,315\.07/, en: /14,315\.07/ },
    { name: 'frequency regulation total', cn: /15,900/, en: /15,900/ },
    { name: 'B user-side total', cn: /8,414\.11/, en: /8,414\.11/ },
    { name: 'co-located net zero-cost', cn: /14,148/, en: /14,148/ },
    { name: 'co-located net paid charge', cn: /9,648/, en: /9,648/ },
    { name: 'capability power', cn: /418\.95/, en: /418\.95/ },
    { name: 'capability energy', cn: /735\.00/, en: /735\.00/ },
    { name: 'capability duration', cn: /1\.7544/, en: /1\.7544/ },
    { name: 'microgrid baseline', cn: /7,408\.72/, en: /7,408\.72/ },
    { name: 'microgrid optimized', cn: /6,525\.12/, en: /6,525\.12/ },
    { name: 'microgrid peak', cn: /838\.50/, en: /838\.50/ },
    { name: 'microgrid throughput', cn: /3,086\.56/, en: /3,086\.56/ },
    { name: 'microgrid cycles', cn: /1\.5433/, en: /1\.5433/ },
    { name: 'microgrid saving', cn: /883\.59/, en: /883\.59/ },
    { name: 'microgrid saving percent', cn: /11\.93%/, en: /11\.93%/ },
    { name: 'microgrid degradation', cn: /92\.60/, en: /92\.60/ },
    { name: 'microgrid with degradation', cn: /6,617\.72/, en: /6,617\.72/ },
    { name: 'storage +20%', cn: /6,350\.61/, en: /6,350\.61/ },
    { name: '900 kW cap', cn: /6,519\.97/, en: /6,519\.97/ },
    { name: 'PV +20% baseline', cn: /6,853\.38/, en: /6,853\.38/ },
    { name: 'PV +20% optimized', cn: /5,996\.19/, en: /5,996\.19/ },
    { name: 'reserve-energy cost', cn: /6,663\.52/, en: /6,663\.52/ },
    { name: 'reserve-energy throughput', cn: /2,625\.45/, en: /2,625\.45/ },
    { name: 'reserve energy shortfall', cn: /−52\.63/, en: /−52\.63/ },
    { name: 'demand bill before', cn: /35,082\.99/, en: /35,082\.99/ },
    { name: 'demand bill after', cn: /32,000/, en: /32,000/ },
    { name: 'demand saving', cn: /3,082\.99/, en: /3,082\.99/ },
    { name: 'full valley charge bill', cn: /36,800/, en: /36,800/ },
    { name: 'overrun penalty', cn: /1,717\.01/, en: /1,717\.01/ },
    { name: 'charging cap', cn: /440 kW/, en: /440 kW/ },
  ],
  'skills/tariff-bill-optimization/SKILL.md': [
    { name: 'bill total', cn: /171,600\.00/, en: /171,600\.00/ },
    { name: 'all-in price', cn: /0\.858/, en: /0\.858/ },
    { name: 'energy share', cn: /48\.95%/, en: /48\.95%/ },
    { name: 'capacity charge', cn: /51,200\.00/, en: /51,200\.00/ },
    { name: 'contract demand charge', cn: /43,809\.52/, en: /43,809\.52/ },
    { name: 'actual demand charge', cn: /46,000\.00/, en: /46,000\.00/ },
    { name: 'contract saving', cn: /7,390\.48/, en: /7,390\.48/ },
    { name: 'declared value', cn: /1,095\.24/, en: /1,095\.24/ },
    { name: 'under-declared charge', cn: /48,000/, en: /48,000/ },
    { name: 'annual capacity charge', cn: /614,400\.00/, en: /614,400\.00/ },
    { name: 'annual contract charge', cn: /500,304\.76/, en: /500,304\.76/ },
    { name: 'annual actual charge', cn: /525,320\.00/, en: /525,320\.00/ },
    { name: 'annual naive declaration', cn: /629,280\.00/, en: /629,280\.00/ },
    { name: 'annual saving', cn: /128,975\.24/, en: /128,975\.24/ },
    { name: 'peak month demand', cn: /1,311/, en: /1,311/ },
    { name: 'power-factor base', cn: /131,600/, en: /131,600/ },
    { name: 'power-factor surcharge', cn: /3,290\.00/, en: /3,290\.00/ },
    { name: 'power-factor discount', cn: /394\.80/, en: /394\.80/ },
    { name: 'power-factor difference', cn: /3,684\.80/, en: /3,684\.80/ },
    { name: 'annual consumption', cn: /6,702,688\.50/, en: /6,702,688\.50/ },
    { name: 'fixed annual cost', cn: /4,021,613\.10/, en: /4,021,613\.10/ },
    { name: 'TOU annual cost', cn: /4,509,570\.56/, en: /4,509,570\.56/ },
    { name: 'market annual cost', cn: /3,681,791\.55/, en: /3,681,791\.55/ },
    { name: 'market saving', cn: /339,821\.55/, en: /339,821\.55/ },
    { name: 'market +20%', cn: /4,351,122\.98/, en: /4,351,122\.98/ },
    { name: 'market +20% penalty', cn: /329,509\.88/, en: /329,509\.88/ },
    { name: 'market −20%', cn: /3,012,460\.13/, en: /3,012,460\.13/ },
    { name: 'break-even rise', cn: /10\.15%/, en: /10\.15%/ },
    { name: 'daily load', cn: /19,275/, en: /19,275/ },
    { name: 'daily cost before', cn: /12,968\.225/, en: /12,968\.225/ },
    { name: 'daily cost after', cn: /11,768\.225/, en: /11,768\.225/ },
    { name: 'daily saving', cn: /1,200\.00/, en: /1,200\.00/ },
    { name: 'annual shift saving', cn: /438,000\.00/, en: /438,000\.00/ },
    { name: 'unit shift revenue', cn: /0\.75/, en: /0\.75/ },
  ],
  'skills/retail-electricity-risk/SKILL.md': [
    { name: 'Guangdong per-kWh margin', cn: /0\.0039/, en: /0\.0039/ },
    { name: '2025 Guangdong margin', cn: /0\.0196/, en: /0\.0196/ },
    { name: 'Guangdong retail average', cn: /0\.4074/, en: /0\.4074/ },
    { name: 'system operation fee', cn: /0\.068/, en: /0\.068/ },
    { name: 'procurement price', cn: /0\.41725/, en: /0\.41725/ },
    { name: 'target quotation', cn: /0\.46025/, en: /0\.46025/ },
    { name: 'example A annual net', cn: /292,500\.00/, en: /292,500\.00/ },
    { name: 'portfolio revenue', cn: /28,900,000\.00/, en: /28,900,000\.00/ },
    { name: 'portfolio wholesale cost', cn: /25,035,000\.00/, en: /25,035,000\.00/ },
    { name: 'portfolio deviation cost', cn: /480,000\.00/, en: /480,000\.00/ },
    { name: 'portfolio opex', cn: /1,500,000\.00/, en: /1,500,000\.00/ },
    { name: 'portfolio net', cn: /1,885,000\.00/, en: /1,885,000\.00/ },
    { name: 'portfolio per-kWh net', cn: /0\.0314167/, en: /0\.0314167/ },
    { name: 'portfolio gross spread', cn: /0\.0644167/, en: /0\.0644167/ },
    { name: 'spot +20% net', cn: /238,000\.00/, en: /238,000\.00/ },
    { name: 'spot +30% net', cn: /−585,500\.00/, en: /−585,500\.00/ },
    { name: 'portfolio break-even rise', cn: /22\.89%/, en: /22\.89%/ },
    { name: 'single-contract break-even', cn: /0\.49/, en: /0\.49/ },
    { name: 'single-contract margin', cn: /7\.10%/, en: /7\.10%/ },
    { name: 'candidate D contribution', cn: /−101,250\.00/, en: /−101,250\.00/ },
    { name: 'portfolio with D', cn: /1,783,750\.00/, en: /1,783,750\.00/ },
    { name: 'candidate D unit cost', cn: /0\.45025/, en: /0\.45025/ },
    { name: 'sigma 2% expected volume', cn: /701\.13/, en: /701\.13/ },
    { name: 'sigma 2% expected cost', cn: /105\.17/, en: /105\.17/ },
    { name: 'sigma 4% expected volume', cn: /14,611\.93/, en: /14,611\.93/ },
    { name: 'sigma 4% expected cost', cn: /2,191\.79/, en: /2,191\.79/ },
    { name: 'sigma 4% q95 volume', cn: /28,398\.56/, en: /28,398\.56/ },
    { name: 'sigma 4% q95 cost', cn: /4,259\.78/, en: /4,259\.78/ },
    { name: 'sigma 6% expected volume', cn: /33,829\.43/, en: /33,829\.43/ },
    { name: 'sigma 6% expected cost', cn: /5,074\.41/, en: /5,074\.41/ },
    { name: 'sigma 6% q95 volume', cn: /67,597\.84/, en: /67,597\.84/ },
    { name: 'sigma 6% q95 cost', cn: /10,139\.68/, en: /10,139\.68/ },
    { name: 'single-period assessment', cn: /4,500\.00/, en: /4,500\.00/ },
    { name: 'current guarantee', cn: /2,500 万元/, en: /25 million CNY/ },
    { name: 'current guarantee first leg', cn: /2,400 万元/, en: /24 million CNY/ },
    { name: 'draft coefficient 1', cn: /3,000 万元/, en: /30 million CNY/ },
    { name: 'draft coefficient 5', cn: /1\.5 亿元/, en: /150 million CNY/ },
    { name: 'draft coefficient 10', cn: /3 亿元/, en: /300 million CNY/ },
    { name: 'guarantee funding current', cn: /25 万元/, en: /250,000 CNY/ },
    { name: 'guarantee funding coefficient 10', cn: /300 万元/, en: /3,000,000 CNY/ },
    { name: 'draft-to-current multiple', cn: /1\.2 倍到 12 倍/, en: /1\.2× to 12×/ },
    { name: 'guarantee gap', cn: /1,000 万元/, en: /10 million CNY/ },
    { name: 'guarantee gap funding', cn: /100,000\.00/, en: /100,000\.00/ },
    { name: 'linked base price', cn: /0\.4675/, en: /0\.4675/ },
    { name: 'linked base margin', cn: /0\.01725/, en: /0\.01725/ },
    { name: 'linked low-price margin', cn: /−0\.02300/, en: /−0\.02300/ },
    { name: 'cost-based floor', cn: /0\.433/, en: /0\.433/ },
  ],
};

const skillPairs = [
  ['skills/virtual-power-plant/SKILL.md', 'skills/virtual-power-plant/SKILL_EN.md'],
  ['skills/electricity-trading-expert/SKILL.md', 'skills/electricity-trading-expert/SKILL_EN.md'],
  ['skills/spot-bidding-quant/SKILL.md', 'skills/spot-bidding-quant/SKILL_EN.md'],
  ['skills/carbon-asset-expert/SKILL.md', 'skills/carbon-asset-expert/SKILL_EN.md'],
  ['skills/storage-investment-operations/SKILL.md', 'skills/storage-investment-operations/SKILL_EN.md'],
  ['skills/renewable-project-development/SKILL.md', 'skills/renewable-project-development/SKILL_EN.md'],
  ['skills/ems-dispatch/SKILL.md', 'skills/ems-dispatch/SKILL_EN.md'],
  ['skills/tariff-bill-optimization/SKILL.md', 'skills/tariff-bill-optimization/SKILL_EN.md'],
  ['skills/retail-electricity-risk/SKILL.md', 'skills/retail-electricity-risk/SKILL_EN.md'],
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
  const globalParity = ['skills/ems-dispatch/SKILL.md', 'skills/tariff-bill-optimization/SKILL.md', 'skills/retail-electricity-risk/SKILL.md'].includes(cnRel) ? [] : parity;
  const pairItems = [...globalParity, ...(pairParity[cnRel] ?? [])];
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

// 6. Content discipline (credibility layer).
//    Only structured objects are checked — scanning prose for "draft + current"
//    produced 22 false positives and 479 untraceable marker lines in practice.
const content = checkContent(root);
errors.push(...content.errors);
const warnings = content.warnings;

if (errors.length) {
  console.error(`Consistency check failed with ${errors.length} issue(s):\n`);
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
for (const warning of warnings) console.warn(`[warning] ${warning}`);
console.log(`Consistency check passed: ${files.length} Markdown files; credibility register ${content.index.summary.gradeCItems} grade-C tickets / ${content.index.summary.openItems} open items / ${content.index.summary.events} events.`);
