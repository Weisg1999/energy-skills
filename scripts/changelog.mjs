#!/usr/bin/env node
/**
 * 更新记录构建器。
 *
 * 单一事实源：仓库根目录的 CHANGELOG.md 与 CHANGELOG_EN.md。
 * 生成物：knowledge/assets/changelog-data.json（禁止手改），由 build-knowledge-html.mjs 写入与校验。
 * 同时提供全站共用的版本胶囊与弹窗骨架，首页、阅读页和实例总览复用同一份标记。
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const escapeHtml = (value) => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const unescapeHtml = (value) => String(value)
  .replace(/&lt;/g, '<')
  .replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&amp;/g, '&');

function rewriteLink(href, repository) {
  if (/^(https?:|mailto:|#)/.test(href)) return href;
  const hashAt = href.indexOf('#');
  const path = hashAt === -1 ? href : href.slice(0, hashAt);
  const hash = hashAt === -1 ? '' : href.slice(hashAt);
  if (!path) return href;
  const clean = path.replace(/^\.\//, '');
  const encoded = clean.split('/').map((part) => encodeURIComponent(part)).join('/');
  return `${repository}/blob/main/${encoded}${hash}`;
}

/** 行内 Markdown → 安全 HTML：代码、粗体、链接；仓库相对链接改指 GitHub blob。 */
function renderInline(text, repository) {
  const codes = [];
  let html = String(text).replace(/`([^`]+)`/g, (_, code) => {
    codes.push(`<code>${escapeHtml(code)}</code>`);
    return `\u0000${codes.length - 1}\u0000`;
  });
  html = escapeHtml(html);
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, href) => {
    const url = rewriteLink(unescapeHtml(href), repository);
    const external = /^https?:/.test(url);
    return `<a href="${escapeHtml(url)}"${external ? ' target="_blank" rel="noopener"' : ''}>${label}</a>`;
  });
  html = html.replace(/\u0000(\d+)\u0000/g, (_, index) => codes[Number(index)]);
  return html;
}

function parseChangelog(text, label, repository) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const introEnd = lines.findIndex((line) => /^###\s+/.test(line));
  const intro = lines.slice(0, introEnd === -1 ? lines.length : introEnd).join('\n');
  const version = /\*\*(v\d+(?:\.\d+)*)\*\*/.exec(intro)?.[1];
  const cutoff = /\*\*(\d{4}-\d{2}-\d{2})\*\*/.exec(intro)?.[1];
  if (!version || !cutoff) {
    throw new Error(`${label} 开头缺少「当前版本 **vX.Y**」或「数据截止 **YYYY-MM-DD**」`);
  }

  const entries = [];
  let current = null;
  for (const line of lines) {
    const heading = /^###\s+(.+?)\s*$/.exec(line);
    if (heading) {
      const match = /^(\d{4}-\d{2}-\d{2})\s*[（(](.*)[）)]\s*$/.exec(heading[1]);
      if (!match) throw new Error(`${label} 存在无法解析的条目标题：${line}`);
      current = { date: match[1], label: match[2].trim(), items: [] };
      entries.push(current);
      continue;
    }
    if (!current) continue;
    const bullet = /^-\s+(.+)$/.exec(line);
    if (bullet) {
      current.items.push(bullet[1].trim());
    } else if (/^\s{2,}\S/.test(line) && current.items.length) {
      current.items[current.items.length - 1] += ` ${line.trim()}`;
    }
  }
  if (!entries.length) throw new Error(`${label} 没有解析到任何 ### 条目`);

  return {
    version,
    cutoff,
    entries: entries.map((entry) => ({
      date: entry.date,
      label: entry.label,
      items: entry.items.map((item) => renderInline(item, repository)),
    })),
  };
}

export function buildChangelog(root, repository) {
  const zh = parseChangelog(readFileSync(join(root, 'CHANGELOG.md'), 'utf8'), 'CHANGELOG.md', repository);
  const en = parseChangelog(readFileSync(join(root, 'CHANGELOG_EN.md'), 'utf8'), 'CHANGELOG_EN.md', repository);
  if (zh.version !== en.version || zh.cutoff !== en.cutoff) {
    throw new Error(`中英文 CHANGELOG 的版本或数据截止不一致：${zh.version}/${zh.cutoff} vs ${en.version}/${en.cutoff}`);
  }
  if (zh.entries.length !== en.entries.length) {
    throw new Error(`中英文 CHANGELOG 条目数不一致：${zh.entries.length} vs ${en.entries.length}`);
  }
  zh.entries.forEach((entry, i) => {
    if (entry.date !== en.entries[i].date) {
      throw new Error(`中英文 CHANGELOG 第 ${i + 1} 条日期不一致：${entry.date} vs ${en.entries[i].date}`);
    }
  });

  return {
    schema: 1,
    generatedFrom: 'CHANGELOG.md + CHANGELOG_EN.md',
    version: zh.version,
    cutoff: zh.cutoff,
    latest: zh.entries[0].date,
    count: zh.entries.length,
    languages: {
      zh: { title: '更新记录', entries: zh.entries },
      en: { title: 'Changelog', entries: en.entries },
    },
  };
}

export function serializeChangelog(changelog) {
  return `${JSON.stringify(changelog, null, 2)}\n`;
}

const LABELS = {
  zh: {
    kicker: 'RELEASE NOTES',
    badge: '更新记录',
    badgeTitle: (version) => `查看更新记录（当前 ${version}）`,
    title: '更新记录',
    subtitle: (version, cutoff, count) => `当前版本 ${version} · 数据截止 ${cutoff} · ${count} 条记录`,
    close: '关闭更新记录',
    language: '切换语言',
    loading: '正在读取更新记录…',
    error: '更新记录加载失败。',
    retry: '重试',
    full: '在 GitHub 查看完整更新记录',
    footer: (version, cutoff, count) => `${version} · ${cutoff} · ${count} 条记录`,
  },
  en: {
    kicker: 'RELEASE NOTES',
    badge: 'Changelog',
    badgeTitle: (version) => `View changelog (current ${version})`,
    title: 'Changelog',
    subtitle: (version, cutoff, count) => `Current ${version} · data cutoff ${cutoff} · ${count} entries`,
    close: 'Close changelog',
    language: 'Switch language',
    loading: 'Loading changelog…',
    error: 'Could not load the changelog.',
    retry: 'Retry',
    full: 'View full changelog on GitHub',
    footer: (version, cutoff, count) => `${version} · ${cutoff} · ${count} entries`,
  },
};

/** 版本胶囊 + 弹窗骨架。assetPrefix 为空表示同级 assets/，'../' 表示上一级。 */
export function renderChangelogWidget(changelog, { lang = 'zh', assetPrefix = '', repository } = {}) {
  const copy = LABELS[lang] || LABELS.zh;
  const version = escapeHtml(changelog.version);
  const cutoff = escapeHtml(changelog.cutoff);
  const count = changelog.count;
  return `<div class="cl-root" data-changelog data-src="${assetPrefix}assets/changelog-data.json" data-repo="${escapeHtml(repository)}" data-page-lang="${lang}" data-version="${version}" data-cutoff="${cutoff}" data-latest="${escapeHtml(changelog.latest)}" data-count="${count}">
  <button class="cl-badge" type="button" data-changelog-open aria-haspopup="dialog" aria-controls="cl-dialog" aria-expanded="false" aria-label="${escapeHtml(copy.badgeTitle(changelog.version))}" title="${escapeHtml(copy.badgeTitle(changelog.version))}">
    <span class="cl-badge-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 2.6-6.4"/><path d="M3 4v5h5"/><path d="M12 7.5V12l3 1.8"/></svg></span>
    <span class="cl-badge-ver">${version}</span>
    <span class="cl-badge-label">${escapeHtml(copy.badge)}</span>
  </button>
  <div class="cl-dialog" id="cl-dialog" data-changelog-dialog hidden>
    <div class="cl-backdrop" data-changelog-close></div>
    <div class="cl-panel" role="dialog" aria-modal="true" aria-labelledby="cl-title" aria-describedby="cl-subtitle" tabindex="-1">
      <header class="cl-head">
        <div class="cl-head-main">
          <span class="cl-kicker">${escapeHtml(copy.kicker)}</span>
          <h2 class="cl-title" id="cl-title"><span class="cl-title-text">${escapeHtml(copy.title)}</span> <span class="cl-pill">${version}</span></h2>
          <p class="cl-sub" id="cl-subtitle">${escapeHtml(copy.subtitle(changelog.version, changelog.cutoff, count))}</p>
        </div>
        <div class="cl-actions">
          <div class="cl-lang" role="group" aria-label="${escapeHtml(copy.language)}">
            <button type="button" data-cl-lang="zh" aria-pressed="${lang === 'zh' ? 'true' : 'false'}">中文</button>
            <button type="button" data-cl-lang="en" aria-pressed="${lang === 'en' ? 'true' : 'false'}">EN</button>
          </div>
          <button class="cl-close" type="button" data-changelog-close aria-label="${escapeHtml(copy.close)}" title="${escapeHtml(copy.close)}">×</button>
        </div>
      </header>
      <div class="cl-body" data-changelog-body>
        <div class="cl-skeleton" data-changelog-status role="status">
          <span class="cl-sr">${escapeHtml(copy.loading)}</span>
          <i></i><i></i><i></i><i></i>
        </div>
      </div>
      <footer class="cl-foot">
        <span data-changelog-meta>${escapeHtml(copy.footer(changelog.version, changelog.cutoff, count))}</span>
        <a data-changelog-full href="${escapeHtml(repository)}/blob/main/${lang === 'en' ? 'CHANGELOG_EN.md' : 'CHANGELOG.md'}" target="_blank" rel="noopener">${escapeHtml(copy.full)} ↗</a>
      </footer>
    </div>
  </div>
</div>`;
}
