/* 主题选择：纯白 / 米白 / 浅绿 / 深色。默认跟随系统深浅色，手动选择后写入 localStorage。 */
(function () {
  var root = document.documentElement;
  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var THEMES = ['light', 'cream', 'green', 'dark'];
  var LABELS = {
    zh: { title: '主题', choose: '选择主题', light: '纯白', cream: '米白', green: '浅绿', dark: '深色' },
    en: { title: 'Theme', choose: 'Choose theme', light: 'White', cream: 'Cream', green: 'Light green', dark: 'Dark' }
  };
  var uid = 0;

  function copy() {
    return (root.lang || '').toLowerCase().indexOf('en') === 0 ? LABELS.en : LABELS.zh;
  }

  function valid(theme) {
    return THEMES.indexOf(theme) !== -1;
  }

  function stored() {
    try {
      var value = localStorage.getItem('es-theme');
      return valid(value) ? value : null;
    } catch (e) {
      return null;
    }
  }

  function current() {
    var theme = root.getAttribute('data-theme');
    return valid(theme) ? theme : 'light';
  }

  function render() {
    var theme = current();
    var c = copy();
    var pickers = document.querySelectorAll('[data-theme-picker]');
    for (var i = 0; i < pickers.length; i += 1) {
      var button = pickers[i].querySelector('[data-theme-menu]');
      if (!button) continue;
      button.setAttribute('aria-label', c.choose);
      button.setAttribute('title', c.choose);
      var options = pickers[i].querySelectorAll('[data-theme-set]');
      for (var j = 0; j < options.length; j += 1) {
        options[j].setAttribute('aria-pressed', options[j].getAttribute('data-theme-set') === theme ? 'true' : 'false');
      }
    }
  }

  function apply(theme, persist) {
    if (!valid(theme)) return;
    root.setAttribute('data-theme', theme);
    if (persist) {
      try {
        localStorage.setItem('es-theme', theme);
      } catch (e) {}
    }
    render();
  }

  function close(picker, focusButton) {
    if (!picker) return;
    var button = picker.querySelector('[data-theme-menu]');
    var menu = picker.querySelector('.theme-menu');
    if (!button || !menu || menu.hidden) return;
    menu.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    if (focusButton) button.focus();
  }

  function closeAll(except) {
    var pickers = document.querySelectorAll('[data-theme-picker]');
    for (var i = 0; i < pickers.length; i += 1) {
      if (pickers[i] !== except) close(pickers[i], false);
    }
  }

  function build(picker) {
    if (picker.getAttribute('data-theme-ready') === 'true') return;
    var button = picker.querySelector('[data-theme-menu]');
    if (!button) return;
    picker.setAttribute('data-theme-ready', 'true');

    var c = copy();
    var menu = document.createElement('div');
    menu.className = 'theme-menu';
    menu.id = 'theme-menu-' + (++uid);
    menu.setAttribute('role', 'group');
    menu.setAttribute('aria-label', c.title);
    menu.hidden = true;

    var html = '<div class="theme-menu-label" aria-hidden="true">' + c.title + '</div>';
    for (var i = 0; i < THEMES.length; i += 1) {
      var theme = THEMES[i];
      html += '<button class="theme-option" type="button" data-theme-set="' + theme + '" aria-pressed="false">' +
        '<span class="theme-swatch theme-swatch-' + theme + '" aria-hidden="true"></span>' +
        '<span>' + c[theme] + '</span>' +
        '<span class="theme-check" aria-hidden="true">✓</span></button>';
    }
    menu.innerHTML = html;
    picker.appendChild(menu);

    button.setAttribute('aria-controls', menu.id);
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-haspopup', 'true');

    button.addEventListener('click', function (event) {
      event.stopPropagation();
      var willOpen = menu.hidden;
      closeAll(picker);
      if (!willOpen) {
        close(picker, false);
        button.focus();
        return;
      }
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      var selected = menu.querySelector('[aria-pressed="true"]') || menu.querySelector('[data-theme-set]');
      if (selected) selected.focus();
    });

    button.addEventListener('keydown', function (event) {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      if (menu.hidden) {
        menu.hidden = false;
        button.setAttribute('aria-expanded', 'true');
      }
      var target = menu.querySelector('[aria-pressed="true"]') || menu.querySelector('[data-theme-set]');
      if (target) target.focus();
    });

    menu.addEventListener('click', function (event) {
      var option = event.target.closest ? event.target.closest('[data-theme-set]') : null;
      if (!option) return;
      apply(option.getAttribute('data-theme-set'), true);
      close(picker, true);
    });

    menu.addEventListener('keydown', function (event) {
      var options = Array.prototype.slice.call(menu.querySelectorAll('[data-theme-set]'));
      var index = options.indexOf(document.activeElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        var step = event.key === 'ArrowDown' ? 1 : -1;
        options[(index + step + options.length) % options.length].focus();
      } else if (event.key === 'Home') {
        event.preventDefault();
        options[0].focus();
      } else if (event.key === 'End') {
        event.preventDefault();
        options[options.length - 1].focus();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        close(picker, true);
      } else if (event.key === 'Tab') {
        close(picker, false);
      }
    });
  }

  var pickers = document.querySelectorAll('[data-theme-picker]');
  for (var i = 0; i < pickers.length; i += 1) build(pickers[i]);

  document.addEventListener('click', function (event) {
    var inside = event.target.closest ? event.target.closest('[data-theme-picker]') : null;
    closeAll(inside);
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    var menu = document.querySelector('.theme-menu:not([hidden])');
    if (!menu) return;
    close(menu.parentElement, true);
  });

  if (mq && mq.addEventListener) {
    mq.addEventListener('change', function (event) {
      if (!stored()) apply(event.matches ? 'dark' : 'light', false);
    });
  }

  render();
})();
