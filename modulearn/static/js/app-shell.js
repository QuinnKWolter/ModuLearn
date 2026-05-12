(function () {
  const root = document.documentElement;
  const storageKey = 'theme';
  const themeColorMeta = document.querySelector('meta[name="theme-color"]');

  function getStoredTheme() {
    const saved = window.localStorage.getItem(storageKey);
    if (saved) {
      return saved;
    }
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
    if (themeColorMeta) {
      themeColorMeta.setAttribute('content', theme === 'dark' ? '#0f172a' : '#f4f8fc');
    }
    document.querySelectorAll('[data-theme-icon]').forEach(function (icon) {
      icon.classList.toggle('bi-sun-fill', theme === 'dark');
      icon.classList.toggle('bi-moon-stars-fill', theme !== 'dark');
    });
    document.querySelectorAll('[data-theme-toggle]').forEach(function (trigger) {
      const nextTheme = theme === 'dark' ? 'light' : 'dark';
      trigger.setAttribute('aria-pressed', String(theme === 'dark'));
      trigger.setAttribute('aria-label', 'Switch to ' + nextTheme + ' mode');
      trigger.setAttribute('title', 'Switch to ' + nextTheme + ' mode');
    });
  }

  function toggleTheme() {
    const nextTheme = root.classList.contains('dark') ? 'light' : 'dark';
    window.localStorage.setItem(storageKey, nextTheme);
    applyTheme(nextTheme);
  }

  function toggleMobileNav() {
    const menu = document.querySelector('[data-mobile-nav]');
    const toggle = document.querySelector('[data-mobile-toggle]');
    const icon = document.querySelector('[data-mobile-toggle-icon]');
    if (!menu) {
      return;
    }
    menu.classList.toggle('hidden');
    if (toggle) {
      const isOpen = !menu.classList.contains('hidden');
      toggle.setAttribute('aria-expanded', String(isOpen));
      toggle.setAttribute('aria-label', isOpen ? 'Close navigation' : 'Open navigation');
      if (icon) {
        icon.classList.toggle('bi-list', !isOpen);
        icon.classList.toggle('bi-x-lg', isOpen);
      }
    }
    window.requestAnimationFrame(syncShellOffsets);
  }

  function handleHeaderScroll() {
    const header = document.querySelector('.site-header');
    if (!header) {
      return;
    }
    header.classList.toggle('is-scrolled', window.scrollY > 12);
  }

  function syncShellOffsets() {
    const header = document.querySelector('.site-header');
    const footer = document.querySelector('.footer-shell');

    root.style.setProperty('--site-header-height', header ? header.offsetHeight + 'px' : '0px');
    root.style.setProperty('--site-footer-height', footer ? footer.offsetHeight + 'px' : '0px');
  }

  document.addEventListener('DOMContentLoaded', function () {
    applyTheme(getStoredTheme());
    handleHeaderScroll();
    syncShellOffsets();

    document.querySelectorAll('[data-theme-toggle]').forEach(function (trigger) {
      trigger.addEventListener('click', toggleTheme);
    });

    const mobileToggle = document.querySelector('[data-mobile-toggle]');
    if (mobileToggle) {
      mobileToggle.addEventListener('click', toggleMobileNav);
      mobileToggle.setAttribute('aria-label', 'Open navigation');
    }

    window.addEventListener('scroll', handleHeaderScroll, { passive: true });
    window.addEventListener('resize', syncShellOffsets);
    window.addEventListener('load', syncShellOffsets);
    window.addEventListener('storage', function (event) {
      if (event.key === storageKey) {
        applyTheme(event.newValue || getStoredTheme());
      }
    });

    if (window.ResizeObserver) {
      const observer = new ResizeObserver(syncShellOffsets);
      document.querySelectorAll('.site-header, .footer-shell').forEach(function (element) {
        observer.observe(element);
      });
    }
  });
})();
