/* 更新记录：左下角版本胶囊打开中英双语弹窗。数据由构建器从两份 CHANGELOG 生成，首次打开时懒加载。 */
(function () {
  var root = document.querySelector('[data-changelog]');
  if (!root) return;

  var openBtn = root.querySelector('[data-changelog-open]');
  var dialog = root.querySelector('[data-changelog-dialog]');
  var panel = root.querySelector('.cl-panel');
  var bodyEl = root.querySelector('[data-changelog-body]');
  var titleText = root.querySelector('.cl-title-text');
  var pill = root.querySelector('.cl-pill');
  var subtitle = root.querySelector('.cl-sub');
  var metaEl = root.querySelector('[data-changelog-meta]');
  var fullLink = root.querySelector('[data-changelog-full]');
  var langGroup = root.querySelector('.cl-lang');
  var langBtns = root.querySelectorAll('[data-cl-lang]');
  var closeBtn = root.querySelector('.cl-close');
  if (!openBtn || !dialog || !panel || !bodyEl) return;

  var COPY = {
    zh: {
      title: '更新记录',
      badgeTitle: function (v) { return '查看更新记录（当前 ' + v + '）'; },
      subtitle: function (v, c, n) { return '当前版本 ' + v + ' · 数据截止 ' + c + ' · ' + n + ' 条记录'; },
      subBase: function (v, c) { return '当前版本 ' + v + ' · 数据截止 ' + c; },
      footer: function (v, c, n) { return v + ' · ' + c + ' · ' + n + ' 条记录'; },
      close: '关闭更新记录',
      language: '切换语言',
      loading: '正在读取更新记录…',
      error: '更新记录加载失败。',
      retry: '重试',
      full: '在 GitHub 查看完整更新记录',
      empty: '暂无更新记录。'
    },
    en: {
      title: 'Changelog',
      badgeTitle: function (v) { return 'View changelog (current ' + v + ')'; },
      subtitle: function (v, c, n) { return 'Current ' + v + ' · data cutoff ' + c + ' · ' + n + ' entries'; },
      subBase: function (v, c) { return 'Current ' + v + ' · data cutoff ' + c; },
      footer: function (v, c, n) { return v + ' · ' + c + ' · ' + n + ' entries'; },
      close: 'Close changelog',
      language: 'Switch language',
      loading: 'Loading changelog…',
      error: 'Could not load the changelog.',
      retry: 'Retry',
      full: 'View full changelog on GitHub',
      empty: 'No entries yet.'
    }
  };

  var repo = root.getAttribute('data-repo') || '';
  var src = root.getAttribute('data-src');
  var pageLang = root.getAttribute('data-page-lang') === 'en' ? 'en' : 'zh';
  var meta = {
    version: root.getAttribute('data-version') || '',
    cutoff: root.getAttribute('data-cutoff') || '',
    latest: root.getAttribute('data-latest') || '',
    count: Number(root.getAttribute('data-count')) || 0
  };
  var lang = storedLang() || pageLang;
  var data = null;
  var loading = null;
  var failed = false;
  var lastFocus = null;
  var closeTimer = 0;
  var reduceMotion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  function c() {
    return COPY[lang];
  }

  function esc(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function storedLang() {
    try {
      var value = localStorage.getItem('es-changelog-lang');
      return value === 'zh' || value === 'en' ? value : null;
    } catch (e) {
      return null;
    }
  }

  function rememberLang(value) {
    try {
      localStorage.setItem('es-changelog-lang', value);
    } catch (e) {}
  }

  function changelogFile() {
    return lang === 'en' ? 'CHANGELOG_EN.md' : 'CHANGELOG.md';
  }

  function changesUrl() {
    return repo + '/blob/main/' + changelogFile();
  }

  function updateChrome() {
    var copy = c();
    if (titleText) titleText.textContent = copy.title;
    if (pill) pill.textContent = meta.version;
    if (subtitle) {
      subtitle.textContent = meta.count
        ? copy.subtitle(meta.version, meta.cutoff, meta.count)
        : copy.subBase(meta.version, meta.cutoff);
    }
    if (metaEl) {
      metaEl.textContent = meta.count
        ? copy.footer(meta.version, meta.cutoff, meta.count)
        : meta.version + ' · ' + meta.cutoff;
    }
    if (fullLink) {
      fullLink.href = changesUrl();
      fullLink.textContent = copy.full + ' ↗';
    }
    if (langGroup) langGroup.setAttribute('aria-label', copy.language);
    if (closeBtn) {
      closeBtn.setAttribute('aria-label', copy.close);
      closeBtn.setAttribute('title', copy.close);
    }
    for (var i = 0; i < langBtns.length; i += 1) {
      langBtns[i].setAttribute('aria-pressed', langBtns[i].getAttribute('data-cl-lang') === lang ? 'true' : 'false');
    }
    bodyEl.setAttribute('lang', lang === 'en' ? 'en' : 'zh-CN');
  }

  function skeleton() {
    return '<div class="cl-skeleton" data-changelog-status role="status">' +
      '<span class="cl-sr">' + esc(c().loading) + '</span>' +
      '<i></i><i></i><i></i><i></i></div>';
  }

  function showLoading() {
    bodyEl.innerHTML = skeleton();
  }

  function showError() {
    bodyEl.innerHTML = '<div class="cl-status">' + esc(c().error) +
      ' <a href="' + esc(changesUrl()) + '" target="_blank" rel="noopener">' + esc(c().full) + ' ↗</a>' +
      ' <button class="cl-retry" type="button" data-changelog-retry>' + esc(c().retry) + '</button></div>';
  }

  function renderEntries() {
    var entries = data && data.languages && data.languages[lang] ? data.languages[lang].entries || [] : [];
    if (!entries.length) {
      bodyEl.innerHTML = '<p class="cl-status">' + esc(c().empty) + '</p>';
      return;
    }
    var html = '<ol class="cl-list">';
    for (var i = 0; i < entries.length; i += 1) {
      var entry = entries[i];
      html += '<li class="cl-entry">' +
        '<div class="cl-entry-head"><time datetime="' + esc(entry.date) + '">' + esc(entry.date) + '</time>' +
        '<span class="cl-entry-label">' + esc(entry.label) + '</span></div>';
      if (entry.items && entry.items.length) {
        html += '<ul class="cl-items">';
        for (var j = 0; j < entry.items.length; j += 1) html += '<li>' + entry.items[j] + '</li>';
        html += '</ul>';
      }
      html += '</li>';
    }
    html += '</ol>';
    bodyEl.innerHTML = html;
    bodyEl.scrollTop = 0;
  }

  function load(force) {
    if (loading) return;
    if (data && !force) return;
    if (typeof fetch !== 'function' || !src) {
      failed = true;
      showError();
      return;
    }
    failed = false;
    showLoading();
    var url = src + '?v=' + encodeURIComponent(meta.latest || meta.version);
    if (force) url += '&r=' + Date.now();
    loading = fetch(url, { credentials: 'same-origin' })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (payload) {
        if (!payload || !payload.languages || !payload.languages.zh || !payload.languages.en) {
          throw new Error('bad payload');
        }
        data = payload;
        meta.version = payload.version || meta.version;
        meta.cutoff = payload.cutoff || meta.cutoff;
        meta.latest = payload.latest || meta.latest;
        meta.count = payload.count || payload.languages.zh.entries.length || 0;
        updateChrome();
        renderEntries();
      })
      .catch(function () {
        failed = true;
        showError();
      })
      .then(function () {
        loading = null;
      });
  }

  function setLang(next, persist) {
    if (next !== 'zh' && next !== 'en') return;
    lang = next;
    if (persist) rememberLang(next);
    updateChrome();
    if (data) renderEntries();
    else if (failed) showError();
    else showLoading();
  }

  function focusables() {
    var nodes = panel.querySelectorAll('a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])');
    var list = [];
    for (var i = 0; i < nodes.length; i += 1) {
      if (nodes[i].offsetParent !== null) list.push(nodes[i]);
    }
    return list;
  }

  function open() {
    if (!dialog.hidden) return;
    if (closeTimer) {
      window.clearTimeout(closeTimer);
      closeTimer = 0;
    }
    lastFocus = document.activeElement;
    dialog.hidden = false;
    openBtn.setAttribute('aria-expanded', 'true');
    document.body.classList.add('cl-open');
    window.requestAnimationFrame(function () {
      if (!dialog.hidden) root.classList.add('is-visible');
    });
    var target = closeBtn || panel;
    target.focus();
    load(false);
  }

  function close() {
    if (dialog.hidden || closeTimer) return;
    root.classList.remove('is-visible');
    openBtn.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('cl-open');
    var finish = function () {
      dialog.hidden = true;
      closeTimer = 0;
      if (lastFocus && typeof lastFocus.focus === 'function' && document.contains(lastFocus)) lastFocus.focus();
    };
    if (reduceMotion && reduceMotion.matches) finish();
    else closeTimer = window.setTimeout(finish, 200);
  }

  openBtn.addEventListener('click', open);

  root.addEventListener('click', function (event) {
    var target = event.target;
    if (target.closest && target.closest('[data-changelog-close]')) {
      event.preventDefault();
      close();
      return;
    }
    var langBtn = target.closest ? target.closest('[data-cl-lang]') : null;
    if (langBtn) {
      setLang(langBtn.getAttribute('data-cl-lang'), true);
      return;
    }
    if (target.closest && target.closest('[data-changelog-retry]')) load(true);
  });

  dialog.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab') return;
    var list = focusables();
    if (!list.length) {
      event.preventDefault();
      panel.focus();
      return;
    }
    var first = list[0];
    var last = list[list.length - 1];
    if (event.shiftKey && (document.activeElement === first || !panel.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !panel.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !dialog.hidden) close();
  });

  setLang(lang, false);
})();
