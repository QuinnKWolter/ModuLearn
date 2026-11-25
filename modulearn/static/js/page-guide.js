/* Small entry point; the tour engine is fetched only on explicit request. */
(() => {
  const panel = document.getElementById('page-guide-dialog');
  if (!panel) return;
  const t = (message) => window.ModuLearnI18n.t(message);
  const start = panel.querySelector('[data-guide-start]');
  const restart = panel.querySelector('[data-guide-restart]');
  const status = panel.querySelector('[data-guide-status]');
  let loading, opener, chooserVersion = 0;
  function load() {
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = panel.dataset.guideCss;
      const script = document.createElement('script'); script.src = panel.dataset.guideScript;
      let timer;
      Promise.race([Promise.all([
        new Promise((ok, fail) => { css.onload = ok; css.onerror = fail; }),
        new Promise((ok, fail) => { script.onload = ok; script.onerror = fail; }),
      ]), new Promise((_, fail) => { timer = setTimeout(fail, 15000); })])
        .then(resolve, () => { css.remove(); script.remove(); loading = null; reject(new Error('guide-assets')); })
        .finally(() => clearTimeout(timer));
      document.head.append(css); document.body.append(script);
    });
    return loading;
  }
  document.querySelectorAll('[data-page-guide]').forEach(button => button.addEventListener('click', async () => {
    chooserVersion++; opener = button; status.textContent = ''; panel.showModal();
    start.textContent = t('Start guide'); restart.hidden = true;
    start.disabled = true; status.textContent = t('Loading guide…');
    try {
      await load(); status.textContent = '';
      if (window.ModuLearnTours.hasProgress(panel)) {
        start.textContent = t('Resume guide'); restart.hidden = false;
      }
    } catch { status.textContent = t('The guide could not be loaded. Please try again.'); }
    finally { start.disabled = false; }
  }));
  panel.querySelector('[data-guide-close]').addEventListener('click', () => panel.close());
  panel.addEventListener('close', () => { chooserVersion++; opener?.focus(); });
  async function begin(reset) {
    const generation = chooserVersion;
    let started = false;
    start.disabled = restart.disabled = true;
    status.textContent = t('Loading guide…');
    try {
      await load();
      // Closing the chooser while assets load cancels the pending start.
      if (!panel.open || generation !== chooserVersion) return;
      started = true;
      panel.close();
      await window.ModuLearnTours.start(panel, {reset, opener});
    } catch {
      if (!started && (!panel.open || generation !== chooserVersion)) return;
      if (!panel.open) panel.showModal();
      status.textContent = t('The guide could not be loaded. Please try again.');
    } finally { start.disabled = restart.disabled = false; }
  }
  start.addEventListener('click', () => begin(false));
  restart.addEventListener('click', () => begin(true));
})();
