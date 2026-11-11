/* 深色/浅色主题切换：默认跟随系统，手动切换后写入 localStorage。 */
(function () {
  var root = document.documentElement;
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function stored() {
    try {
      var v = localStorage.getItem('es-theme');
      return v === 'dark' || v === 'light' ? v : null;
    } catch (e) {
      return null;
    }
  }

  function current() {
    return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }

  function render() {
    var dark = current() === 'dark';
    var en = (document.documentElement.lang || '').toLowerCase().indexOf('en') === 0;
    var label = dark
      ? (en ? 'Switch to light mode' : '切换到浅色模式')
      : (en ? 'Switch to dark mode' : '切换到深色模式');
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].setAttribute('aria-label', label);
      buttons[i].setAttribute('title', label);
      buttons[i].setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
    var labels = document.querySelectorAll('[data-theme-label]');
    for (var j = 0; j < labels.length; j += 1) labels[j].textContent = dark ? '浅色' : '深色';
  }

  function apply(theme, persist) {
    root.setAttribute('data-theme', theme);
    if (persist) {
      try {
        localStorage.setItem('es-theme', theme);
      } catch (e) {}
    }
    render();
  }

  var buttons = document.querySelectorAll('[data-theme-toggle]');
  for (var i = 0; i < buttons.length; i += 1) {
    buttons[i].addEventListener('click', function () {
      apply(current() === 'dark' ? 'light' : 'dark', true);
    });
  }

  if (mq && mq.addEventListener) {
    mq.addEventListener('change', function (e) {
      if (!stored()) apply(e.matches ? 'dark' : 'light', false);
    });
  }

  render();
})();
