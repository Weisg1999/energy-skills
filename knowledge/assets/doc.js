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

  function closeNav() { body.classList.remove('nav-open'); if (toggle) toggle.setAttribute('aria-expanded', 'false'); }
  if (toggle) {
    toggle.addEventListener('click', function () {
      var open = body.classList.toggle('nav-open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  if (scrim) scrim.addEventListener('click', closeNav);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeNav(); });

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
      if (current && map[current.id]) {
        map[current.id].classList.add('on');
        var item = map[current.id].querySelector('a');
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
})();
