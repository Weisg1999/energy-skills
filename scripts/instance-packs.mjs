/**
 * 实例包总览页生成器。
 *
 * 事实源：skills/<skill>/instances/<pack>/instance.json 与 README.md。
 * 生成物：knowledge/instances.html（禁止手改），由 build-knowledge-html.mjs 调用。
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const esc = (s) => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const clean = (s) => String(s)
  .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
  .replace(/`([^`]*)`/g, '$1')
  .replace(/\*\*([^*]+)\*\*/g, '$1')
  .replace(/\*([^*]+)\*/g, '$1')
  .replace(/\s+/g, ' ')
  .trim();

const clip = (s, n) => {
  const text = clean(s);
  return text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text;
};

function readmeMeta(text) {
  const lines = String(text || '').replace(/\r\n?/g, '\n').split('\n');
  const titleIndex = lines.findIndex((line) => /^#\s+/.test(line));
  const title = titleIndex >= 0 ? clean(lines[titleIndex].replace(/^#\s+/, '')) : '';
  const quote = [];
  let started = false;
  for (let i = titleIndex + 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (/^>\s?/.test(line)) {
      started = true;
      quote.push(line.replace(/^>\s?/, ''));
      continue;
    }
    if (started) break;
  }
  let lead = clean(quote.join(' '));
  if (!lead || lead.startsWith('目录定位') || /^本目录是.*纵向切片/.test(lead) || lead.length > 220) lead = '';
  return { title, lead };
}

export function discoverInstancePacks(root, skillDocs) {
  const bySlug = new Map(skillDocs.map((skill) => [skill.slug, skill]));
  const packs = [];
  const skillsRoot = join(root, 'skills');
  for (const slug of readdirSync(skillsRoot).sort()) {
    const instancesDir = join(skillsRoot, slug, 'instances');
    if (!existsSync(instancesDir)) continue;
    for (const dirName of readdirSync(instancesDir).sort()) {
      const packDir = join(instancesDir, dirName);
      const configPath = join(packDir, 'instance.json');
      if (!existsSync(configPath)) continue;
      const config = JSON.parse(readFileSync(configPath, 'utf8'));
      const meta = config.meta || {};
      const required = ['instance_id', 'province', 'market', 'entity_type', 'rule_version', 'data_cutoff', 'grade', 'scope'];
      const missing = required.filter((key) => !meta[key]);
      if (missing.length) throw new Error(`${configPath} 缺少 meta.${missing.join('、meta.')}`);
      const readmePath = join(packDir, 'README.md');
      const readme = existsSync(readmePath) ? readFileSync(readmePath, 'utf8') : '';
      const parsed = readmeMeta(readme);
      const skill = bySlug.get(slug);
      packs.push({
        id: meta.instance_id,
        dirName,
        slug,
        skillTitle: skill?.title || slug,
        skillSummary: skill?.summary || '',
        title: parsed.title || `${meta.province} · ${meta.entity_type}`,
        lead: parsed.lead,
        province: meta.province,
        market: meta.market,
        entityType: meta.entity_type,
        ruleVersion: meta.rule_version,
        grade: meta.grade,
        scope: meta.scope,
        cutoff: meta.data_cutoff,
        readmeHref: `../skills/${slug}/instances/${dirName}/README.md`,
        configHref: `../skills/${slug}/instances/${dirName}/instance.json`,
        runHref: `../skills/${slug}/instances/${dirName}/run.py`,
        skillHref: `html/skill-${slug}.html`,
      });
    }
  }
  const order = new Map(skillDocs.map((skill, index) => [skill.slug, index]));
  packs.sort((a, b) => (order.get(a.slug) ?? 99) - (order.get(b.slug) ?? 99) || a.id.localeCompare(b.id));
  const groups = skillDocs
    .map((skill) => ({ ...skill, packs: packs.filter((pack) => pack.slug === skill.slug) }))
    .filter((group) => group.packs.length);
  const provinces = [...new Set(packs.map((pack) => pack.province))];
  const cutoff = packs.map((pack) => pack.cutoff).filter(Boolean).sort().at(-1) || '';
  return { packs, groups, provinces, cutoff, count: packs.length };
}

function renderCard(pack) {
  const lead = pack.lead || pack.scope;
  return `<article class="pack-card" id="pack-${esc(pack.id)}">
          <div class="pack-top">
            <h3 class="pack-title">${esc(pack.title)}</h3>
            <div class="pack-badges">
              <span class="pack-badge">${esc(pack.province)}</span>
              <span class="pack-badge pack-badge-grade">${esc(pack.grade)}</span>
            </div>
          </div>
          <p class="pack-lead">${esc(clip(lead, 170))}</p>
          <dl class="pack-meta">
            <div><dt>主体</dt><dd title="${esc(pack.entityType)}">${esc(clip(pack.entityType, 80))}</dd></div>
            <div><dt>市场</dt><dd title="${esc(pack.market)}">${esc(clip(pack.market, 90))}</dd></div>
            <div class="pack-meta-wide"><dt>规则版本</dt><dd title="${esc(pack.ruleVersion)}">${esc(clip(pack.ruleVersion, 180))}</dd></div>
            <div><dt>数据截止</dt><dd>${esc(pack.cutoff)}</dd></div>
            <div><dt>目录</dt><dd><code>instances/${esc(pack.dirName)}/</code></dd></div>
          </dl>
          <div class="pack-links">
            <a class="pack-link pack-link-primary" href="${esc(pack.readmeHref)}" target="_blank" rel="noopener">说明 README ↗</a>
            <a class="pack-link" href="${esc(pack.configHref)}" target="_blank" rel="noopener">instance.json ↗</a>
            <a class="pack-link" href="${esc(pack.runHref)}" target="_blank" rel="noopener">run.py ↗</a>
            <a class="pack-link" href="${esc(pack.skillHref)}">技能页 →</a>
          </div>
        </article>`;
}

const PAGE_CSS = `
:root{--pack-gap:10px}
.nav-list a{display:flex;justify-content:space-between;gap:8px}
.nav-count{font:600 var(--fs-2xs)/1.5 var(--mono);color:var(--muted)}
.pack-group{margin:38px 0 0;padding-top:22px;border-top:1px solid var(--line)}
.pack-group:first-of-type{margin-top:26px;padding-top:0;border-top:0}
.pack-group-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:12px}
.pack-group-head h2{font-family:var(--serif);font-size:var(--fs-md);line-height:1.4;margin:0 0 4px;letter-spacing:-.01em}
.pack-group-head p{margin:0;font-size:var(--fs-xs);line-height:1.6;color:var(--muted);max-width:56em}
.pack-group-link{flex:none;font-size:var(--fs-xs);white-space:nowrap;padding-top:4px}
.pack-grid{display:grid;grid-template-columns:1fr;gap:var(--pack-gap)}
.pack-card{scroll-margin-top:calc(var(--topbar-h) + 16px);border:1px solid var(--line);border-radius:12px;background:var(--card);padding:16px 18px;box-shadow:var(--shadow)}
.pack-card:target{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}
.pack-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.pack-title{font-size:var(--fs-md);line-height:1.45;margin:0;font-weight:650;letter-spacing:-.01em}
.pack-badges{display:flex;flex-wrap:wrap;gap:5px;flex:none}
.pack-badge{font:600 var(--fs-2xs)/1.5 var(--mono);padding:3px 7px;border-radius:4px;background:var(--accent-soft);color:var(--accent);white-space:nowrap}
.pack-badge-grade{background:var(--paper-2);color:var(--muted);border:1px solid var(--line)}
.pack-lead{margin:8px 0 0;font-size:var(--fs-sm);line-height:1.7;color:var(--ink-2)}
.pack-meta{display:grid;grid-template-columns:1fr 1fr;gap:7px 18px;margin:12px 0 0;padding-top:10px;border-top:1px dashed var(--line)}
.pack-meta div{min-width:0}
.pack-meta-wide{grid-column:1 / -1}
.pack-meta dt{font:600 var(--fs-2xs)/1.5 var(--mono);letter-spacing:.06em;color:var(--muted)}
.pack-meta dd{margin:1px 0 0;font-size:var(--fs-xs);line-height:1.6;color:var(--ink-2);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.pack-meta-wide dd{-webkit-line-clamp:3}
.pack-meta code{font-size:var(--fs-2xs);color:var(--ink-2);background:var(--paper-2);padding:1px 4px;border-radius:3px}
.pack-links{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.pack-link{font-size:var(--fs-2xs);line-height:1.5;padding:4px 8px;border:1px solid var(--line);border-radius:5px;background:var(--paper-2);color:var(--ink-2);white-space:nowrap}
.pack-link:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
.pack-link-primary{background:var(--accent-soft);border-color:transparent;color:var(--accent);font-weight:600}
.instance-steps{list-style:none;margin:0;padding:0;border-left:1px solid var(--line)}
.instance-steps li{padding:6px 0 6px 12px;border-left:2px solid transparent;margin-left:-1px}
.instance-steps b{display:block;font-size:var(--fs-xs);color:var(--ink)}
.instance-steps span{display:block;font-size:var(--fs-2xs);line-height:1.55;color:var(--muted)}
.instance-toc-title{margin-top:22px}
.instance-docs{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
.instance-docs a{display:block;padding:4px 8px;border-radius:5px;font-size:var(--fs-xs);color:var(--muted)}
.instance-docs a:hover{color:var(--accent);background:var(--accent-soft);text-decoration:none}
.instance-boundary{margin:16px 0 0;font-size:var(--fs-2xs);line-height:1.6;color:var(--muted)}
.pack-foot-lic code{font-size:var(--fs-2xs)}
@media(max-width:760px){
  .pack-meta{grid-template-columns:1fr}
  .pack-top{flex-direction:column}
  .pack-badges{flex-direction:row}
  .pack-group-head{flex-direction:column;gap:6px}
}
`;

export function renderInstancesPage(data) {
  const sideList = data.groups.map((group) => `<li><a href="#skill-${esc(group.slug)}">${esc(group.title)}<span class="nav-count">${group.packs.length}</span></a></li>`).join('\n              ');
  const mobileToc = data.groups.map((group) => `<li class="lv2"><a href="#skill-${esc(group.slug)}">${esc(group.title)}（${group.packs.length}）</a></li>`).join('\n            ');
  const groupsHtml = data.groups.map((group) => `<section class="pack-group" id="skill-${esc(group.slug)}" aria-labelledby="group-${esc(group.slug)}">
        <div class="pack-group-head">
          <div>
            <h2 id="group-${esc(group.slug)}">${esc(group.title)}</h2>
            <p>${esc(group.summary)}</p>
          </div>
          <a class="pack-group-link" href="html/skill-${esc(group.slug)}.html">技能页 →</a>
        </div>
        <div class="pack-grid">
          ${group.packs.map(renderCard).join('\n          ')}
        </div>
      </section>`).join('\n\n      ');
  const layerLinks = data.groups.map((group) => `<li><a href="../skills/${esc(group.slug)}/instances/README.md" target="_blank" rel="noopener">${esc(group.title)}实例层 ↗</a></li>`).join('\n        ');
  const description = `${data.count} 个一省一主体实例包：煤电、光储、独立储能、VPP、售电与工商业储能；配置改 JSON，数据换 CSV，运行 run.py。`;
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>实例包总览 | energy-skills 知识库</title>
<meta name="description" content="${esc(description)}">
<link rel="icon" type="image/svg+xml" href="assets/logo-book-favicon.svg">
<script>
(function(){try{var t=localStorage.getItem('es-theme');if(t!=='dark'&&t!=='light'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
</script>
<link rel="stylesheet" href="assets/tokens.css">
<link rel="stylesheet" href="assets/knowledge.css">
<style>${PAGE_CSS}</style>
</head>
<body data-cat="skill" id="top">
<a class="skip" href="#main">跳到正文</a>
<div class="progress" id="progress" aria-hidden="true"></div>
<div class="scrim"></div>

<header class="topbar">
  <a class="back" href="index.html" data-home-link aria-label="返回知识库"><span aria-hidden="true">←</span><span class="back-label">知识库</span></a>
  <div class="crumb">
    <span class="crumb-cat">INSTANCE LAYER</span>
    <span class="crumb-sep">/</span>
    <span class="crumb-doc">实例包总览</span>
  </div>
  <div class="topbar-act">
    <button class="theme-toggle" type="button" data-theme-toggle aria-label="切换到深色模式" title="切换到深色模式">
      <svg class="ico-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"/></svg>
      <svg class="ico-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    </button>
    <details class="more">
      <summary class="more-btn" aria-label="更多" title="更多"><span class="more-label">更多</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></svg></summary>
      <div class="more-menu">
        <a class="src" href="../README.md" target="_blank" rel="noopener">仓库说明<small>README.md</small></a>
        <a class="src" href="index.html#skills">配套技能</a>
        <a class="src" href="index.html#method">使用与口径</a>
      </div>
    </details>
    <button class="toc-toggle" type="button" id="navToggle" aria-expanded="false" aria-controls="nav">目录</button>
  </div>
</header>

<div class="shell">
  <aside class="sidebar" id="nav">
    <div class="nav-kicker">实例层</div>
    <div class="nav-num">INSTANCE</div>
    <h2 class="nav-cat"><a href="index.html#skills">配套技能</a></h2>
    <ul class="nav-list">
              ${sideList}
    </ul>
    <div class="nav-others">
      <div class="nav-kicker">回到</div>
      <ul>
        <li><a href="index.html#skills"><b>04</b>配套技能</a></li>
        <li><a href="index.html#map"><b>01</b>知识地图</a></li>
        <li><a href="index.html#method"><b>05</b>使用与口径</a></li>
      </ul>
    </div>
  </aside>

  <main class="main" id="main">
    <header class="doc-head">
      <div class="kicker">INSTANCE LAYER<i>配置层</i></div>
      <h1 class="doc-title">实例包总览</h1>
      <p class="lede">把“一省 + 一主体 + 一套合约/账单 + 一个规则版本”做成可运行切片：选包 → 改 JSON → 换 CSV → 运行 run.py。这里汇总 ${data.count} 个包，覆盖 ${esc(data.provinces.join('、'))}。</p>
      <p class="hook">配置层不是知识模块；所有演示数据均为 D 级合成样板，不对应任何真实主体，也不构成报价、投资或法律建议。</p>
      <div class="tags"><span class="tag">实例包</span><span class="tag">配置层</span><span class="tag">可运行</span><span class="tag">D 级合成</span></div>
      <div class="doc-meta"><span>${data.count} 个包</span><span>${data.groups.length} 项技能</span><span>${data.provinces.length} 个省份</span><span>数据截止 ${esc(data.cutoff)}</span></div>
    </header>

    <details class="toc-mobile">
      <summary>本页目录（${data.groups.length}）</summary>
      <ol>
            ${mobileToc}
      </ol>
    </details>

    <div class="pack-list">
      ${groupsHtml}
    </div>

    <footer class="doc-foot">
      <div class="lic pack-foot-lic">生成物：由 <code>scripts/build-knowledge-html.mjs</code> 从 <code>skills/*/instances/*/instance.json</code> 与 README 生成，不要手改；实例包只改 JSON 与 CSV，不改代码。</div>
      <div class="doc-foot-links">
        <a href="../README.md" target="_blank" rel="noopener">仓库说明 ↗</a>
        <span aria-hidden="true"> · </span>
        <a href="index.html" data-home-link>返回知识库</a>
      </div>
    </footer>
  </main>

  <aside class="toc" aria-label="实例包使用说明">
    <div class="toc-title">怎么用</div>
    <ol class="instance-steps">
      <li><b>选包</b><span>按技能或省份挑一个切片。</span></li>
      <li><b>改配置</b><span>只改 instance.json 的规则、资产与合约/账单参数。</span></li>
      <li><b>换数据</b><span>用你的 CSV 替换 data/ 下的 D 级演示数据。</span></li>
      <li><b>运行</b><span>python run.py；产物写入 out/，默认不入库。</span></li>
    </ol>
    <div class="toc-title instance-toc-title">实例层说明</div>
    <ul class="instance-docs">
        ${layerLinks}
    </ul>
    <p class="instance-boundary">实例包是配置层：不下单、不替代交易中心结算与调度认定；真实台账、合同与计量数据只放本地。</p>
  </aside>
</div>

<nav class="page-aux" aria-label="页面辅助">
  <a class="to-top" href="#top" aria-label="回到顶部">↑</a>
</nav>
<script src="assets/doc.js"></script>
<script src="assets/theme.js"></script>
</body>
</html>
`;
}

export function buildInstanceSearchRecord(data) {
  const chunks = [
    {
      h: '实例包总览',
      a: '',
      x: `${data.count} 个一省一主体实例包，覆盖 ${data.provinces.join('、')}；配置改 JSON，数据换 CSV，运行 run.py。`,
      l: 2,
    },
    ...data.packs.map((pack) => ({
      h: pack.title,
      a: `pack-${pack.id}`,
      x: [pack.skillTitle, pack.province, pack.entityType, pack.market, pack.scope, pack.ruleVersion].join(' '),
      l: 3,
    })),
  ];
  return {
    id: 'instance-packs',
    title: '实例包总览',
    summary: `${data.count} 个一省一主体的可运行切片：煤电、光储、独立储能、VPP、售电与工商业储能。`,
    tags: ['实例包', '配置层', '可运行', ...data.groups.map((group) => group.title)],
    cat: 'instance',
    catTitle: '实例层',
    catNum: 'INSTANCE',
    type: 'instance',
    html: 'instances.html',
    cutoff: data.cutoff,
    keywords: ['实例包', '一省一主体', '配置层', ...data.groups.map((group) => group.title), ...data.provinces, ...data.packs.map((pack) => pack.title)].join(' '),
    chunks,
  };
}
