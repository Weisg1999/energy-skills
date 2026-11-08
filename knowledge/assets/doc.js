/* energy-skills 知识库 · 内容页交互：阅读进度、目录高亮、移动端抽屉 */
(function () {
  var body = document.body;
  var bar = document.getElementById('progress');
  var topbar = document.querySelector('.topbar');
  var toTop = document.querySelector('.to-top');
  var toggle = document.getElementById('navToggle');
  var scrim = document.querySelector('.scrim');

  function onScroll() {
    var doc = document.documentElement;
    var max = doc.scrollHeight - doc.clientHeight;
    var y = doc.scrollTop || body.scrollTop || 0;
    if (bar) bar.style.width = (max > 0 ? (y / max) * 100 : 0).toFixed(2) + '%';
    if (topbar) topbar.classList.toggle('scrolled', y > 8);
    if (toTop) toTop.classList.toggle('show', y > 600);
  }

  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { onScroll(); ticking = false; });
  }, { passive: true });
  window.addEventListener('resize', onScroll);
  onScroll();

  var nav = document.getElementById('nav');
  var firstNavLink = nav ? nav.querySelector('a') : null;
  function closeNav() {
    body.classList.remove('nav-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
    if (nav && nav.contains(document.activeElement) && toggle) toggle.focus();
  }
  function openNav() {
    body.classList.add('nav-open');
    if (toggle) toggle.setAttribute('aria-expanded', 'true');
    if (firstNavLink) firstNavLink.focus();
  }
  if (toggle) {
    toggle.addEventListener('click', function () {
      if (body.classList.contains('nav-open')) closeNav();
      else openNav();
    });
  }
  if (scrim) scrim.addEventListener('click', closeNav);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeNav(); });

  var tocBox = document.querySelector('.toc');
  var tocMore = document.querySelector('.toc-more');
  if (tocBox && tocMore) {
    tocMore.addEventListener('click', function () {
      var open = tocBox.classList.toggle('expanded');
      tocMore.setAttribute('aria-expanded', open ? 'true' : 'false');
      tocMore.textContent = open ? '收起小节' : '展开 ' + tocMore.getAttribute('data-count') + ' 个小节';
    });
  }

  // 目录高亮：取当前视口上方最近的标题
  var links = Array.prototype.slice.call(document.querySelectorAll('.toc a[href^="#"]'));
  if (links.length && 'IntersectionObserver' in window) {
    var map = {};
    var targets = [];
    links.forEach(function (a) {
      var el = document.getElementById(a.getAttribute('href').slice(1));
      if (el) { map[el.id] = a.parentNode; targets.push(el); }
    });
    var visible = {};
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { visible[en.target.id] = en.isIntersecting; });
      var current = null;
      for (var i = 0; i < targets.length; i += 1) {
        var r = targets[i].getBoundingClientRect();
        if (r.top <= 120) current = targets[i];
      }
      links.forEach(function (a) { a.parentNode.classList.remove('on'); });
      var currentLi = current && map[current.id];
      if (currentLi && currentLi.classList.contains('lv3') && tocBox && !tocBox.classList.contains('expanded')) {
        var prev = currentLi.previousElementSibling;
        while (prev && !prev.classList.contains('lv2')) prev = prev.previousElementSibling;
        if (prev) currentLi = prev;
      }
      if (currentLi) {
        currentLi.classList.add('on');
        var item = currentLi.querySelector('a');
        if (item) {
          var box = item.closest('.toc');
          if (box) {
            var top = item.offsetTop - box.clientHeight / 2;
            box.scrollTo({ top: top > 0 ? top : 0, behavior: 'auto' });
          }
        }
      }
    }, { rootMargin: '-80px 0px -70% 0px', threshold: [0, 1] });
    targets.forEach(function (el) { io.observe(el); });
  }

  // 政策列表：关键词检索 + 状态筛选 + 分组计数
  var policyList = document.querySelector('.policy-list');
  if (policyList) {
    var policies = Array.prototype.slice.call(document.querySelectorAll('.policy-list a.policy'));
    var groups = Array.prototype.slice.call(document.querySelectorAll('.policy-group'));
    var pInput = document.getElementById('policySearch');
    var pClear = document.getElementById('policyClear');
    var pCount = document.getElementById('policyCount');
    var pEmpty = document.getElementById('policyEmpty');
    var pChips = Array.prototype.slice.call(document.querySelectorAll('.policy-chips .pchip'));
    var pStatus = 'all';
    var norm = function (s) { return String(s).replace(/\s+/g, '').toLowerCase(); };

    function applyPolicy() {
      var q = norm(pInput ? pInput.value : '');
      var shown = 0;
      policies.forEach(function (a) {
        var okStatus = pStatus === 'all' || a.getAttribute('data-status') === pStatus;
        var okQuery = !q || norm(a.getAttribute('data-search') || '').indexOf(q) !== -1;
        var on = okStatus && okQuery;
        a.classList.toggle('is-hidden', !on);
        if (on) shown += 1;
      });
      groups.forEach(function (g) {
        var visible = g.querySelectorAll('a.policy:not(.is-hidden)').length;
        g.classList.toggle('is-hidden', visible === 0);
        var badge = g.querySelector('.policy-group-count');
        if (badge) badge.textContent = visible;
      });
      var filtered = Boolean(q) || pStatus !== 'all';
      if (pCount) pCount.textContent = filtered
        ? '匹配 ' + shown + ' / ' + policies.length + ' 条'
        : '共 ' + policies.length + ' 条 · 点击卡片查看官方原文';
      if (pEmpty) pEmpty.hidden = shown !== 0;
      if (pClear) pClear.hidden = !(pInput && pInput.value);
    }

    if (pInput) {
      pInput.addEventListener('input', applyPolicy);
      pInput.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { pInput.value = ''; applyPolicy(); pInput.blur(); }
      });
    }
    if (pClear) {
      pClear.addEventListener('click', function () {
        if (pInput) { pInput.value = ''; pInput.focus(); }
        applyPolicy();
      });
    }
    pChips.forEach(function (btn) {
      btn.addEventListener('click', function () {
        pStatus = btn.getAttribute('data-status') || 'all';
        pChips.forEach(function (b) { b.classList.toggle('on', b === btn); });
        applyPolicy();
      });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      var tag = (document.activeElement && document.activeElement.tagName) || '';
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
      e.preventDefault();
      if (pInput) pInput.focus();
    });
    applyPolicy();
  }
})();
