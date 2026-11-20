/* Bounded server-side browsing and restartable CSV preparation. No student data
   or payloads are cached in browser storage; only expiring export tickets are. */
(() => {
  'use strict';
  const t = (key, values) => window.ModuLearnI18n?.t(key, values) || key;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const csrf = () => document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
    decodeURIComponent(document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] || '');
  async function request(url, options = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (options.signal?.aborted) abort();
    options.signal?.addEventListener('abort', abort, {once: true});
    const timeout = setTimeout(abort, 25000);
    try {
      const response = await fetch(url, {credentials: 'same-origin', ...options, signal: controller.signal});
      if (!response.ok) throw new Error(String(response.status));
      return await response.json();
    } finally {
      clearTimeout(timeout);
      options.signal?.removeEventListener('abort', abort);
    }
  }
  const storage = {
    get(key) {try {return sessionStorage.getItem(key);} catch (_) {return null;}},
    set(key, value) {try {sessionStorage.setItem(key, value);} catch (_) {}},
    remove(key) {try {sessionStorage.removeItem(key);} catch (_) {}}
  };

  async function prepare(url, options, status, link, cancelled = () => false) {
    const key = `activity-export:${url}:${JSON.stringify(options)}`;
    let token = storage.get(key);
    link.hidden = true;
    status.textContent = t('Preparing CSV…');
    try {
      while (!cancelled()) {
        const result = await request(url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
          body: JSON.stringify(token ? {token} : options)});
        token = result.token;
        storage.set(key, token);
        if (cancelled()) return;
        status.textContent = t('{count} records prepared.', {count: result.count.toLocaleString()});
        if (result.done) {
          link.href = result.download;
          link.hidden = false;
          storage.remove(key);
          return;
        }
        // Yield between batches; every request is independently retryable.
        await new Promise(resolve => setTimeout(resolve, 80));
      }
    } catch (error) {
      if (error.message === '400') storage.remove(key);
      if (!cancelled()) status.textContent = t('Download preparation paused. Retry to continue; expired exports restart safely.');
    }
  }

  function initialize() {
    const exportPage = document.getElementById('activityExportPage');
    if (exportPage) {
      const button = document.getElementById('activityPrepareButton');
      const options = JSON.parse(document.getElementById('activityExportOptions').textContent);
      const run = async () => {
        button.disabled = true;
        await prepare(exportPage.dataset.url, options, document.getElementById('activityExportStatus'), document.getElementById('activityExportLink'));
        button.disabled = false;
      };
      button.addEventListener('click', run);
      run();
    }
    const root = document.getElementById('activityBrowser');
    if (!root) return;
    const form = document.getElementById('activityFilters');
    const body = document.getElementById('activityRows');
    const status = document.getElementById('activityStatus');
    const previous = document.getElementById('activityPrevious');
    const next = document.getElementById('activityNext');
    const pageLabel = document.getElementById('activityPage');
    let config, pages = [null], page = 0, nextCursor = null, generation = 0, controller, exportGeneration = 0, exporting = false;
    const filters = () => Object.fromEntries(new FormData(form));
    const linkedFilter = document.getElementById('activityLinkedFilter');
    function clearLink() {
      for (const key of ['student', 'module', 'original']) form.elements[key].value = '';
      linkedFilter.hidden = true;
    }
    linkedFilter.querySelector('button').addEventListener('click', () => {clearLink(); load(true);});
    function render(records, url, context) {
      body.replaceChildren();
      for (const record of records) {
        const row = el('tr');
        row.dataset.success = String(record.success);
        row.append(el('td', new Date(record.time_utc).toLocaleString(window.ModuLearnLanguage || 'en')));
        const student = el('td');
        student.setAttribute('data-no-ui-translate', '');
        student.append(el('span', record.student_name || record.student));
        if (record.student_name && record.student_name !== record.student) student.append(el('small', record.student));
        student.title = [record.student, record.email].filter(Boolean).join('\n');
        const activity = el('td');
        const title = el('span', record.activity || record.original_problem || '—', 'activity-title');
        title.setAttribute('data-no-ui-translate', '');
        title.title = title.textContent;
        activity.append(title);
        if (context === 'practice' && record.original_problem) {
          const source = el('details');
          const original = el('span', record.original_problem);
          original.setAttribute('data-no-ui-translate', '');
          source.append(el('summary', t('Original problem')), original);
          activity.append(source);
        }
        const event = el('td');
        const badge = el('span', record.event.replaceAll('_', ' '), 'activity-event');
        badge.dataset.kind = record.event;
        event.append(badge);
        event.setAttribute('data-no-ui-translate', '');
        event.append(el('small', record.source || ''));
        row.append(student, activity, event,
          el('td', record.progress == null ? '—' : `${Math.round(record.progress * 100)}%`),
          el('td', record.attempt_score == null ? '—' : `${Number(record.attempt_score.toFixed(2))}%`));
        const cell = el('td');
        const detail = el('details');
        const summary = el('summary', t('Inspect event'));
        const payload = el('pre');
        const related = el('button', context === 'practice' ? t('Course activity') : t('Show practice events'), 'btn btn-outline-secondary');
        related.type = 'button';
        related.addEventListener('click', () => {
          clearLink();
          form.elements.context.value = context === 'practice' ? 'course' : 'practice';
          form.elements.q.value = form.elements.event.value = '';
          form.elements.student.value = record.student_id;
          form.elements[context === 'practice' ? 'module' : 'original'].value = context === 'practice' ? record.source_module_id : record.module_id;
          linkedFilter.querySelector('span').textContent = `${record.student_name || record.student} · ${record.original_problem || record.activity}`;
          linkedFilter.hidden = false;
          load(true);
        });
        detail.append(summary, related, payload);
        let loaded = false, pending = false;
        detail.addEventListener('toggle', async () => {
          if (!detail.open || loaded || pending) return;
          pending = true;
          payload.textContent = t('Loading…');
          try {
            const result = await request(`${url}?${new URLSearchParams({context, detail: record.id})}`);
            payload.textContent = JSON.stringify({...record, payload: result.payload}, null, 2);
            loaded = true;
          } catch (_) {payload.textContent = t('Could not load activity. Please retry.');}
          finally {pending = false;}
        });
        cell.append(detail); row.append(cell); body.append(row);
      }
    }
    async function load(reset = false) {
      if (!config) return;
      if (reset) {pages = [null]; page = 0;}
      controller?.abort(); controller = new AbortController();
      const current = ++generation;
      previous.disabled = next.disabled = true;
      body.replaceChildren();
      status.textContent = t('Loading…');
      const options = filters();
      if (pages[page]) options.cursor = pages[page];
      const url = config.url;
      try {
        const result = await request(`${url}?${new URLSearchParams(options)}`, {signal: controller.signal});
        if (current !== generation) return;
        render(result.rows, url, options.context);
        nextCursor = result.next;
        previous.disabled = page === 0;
        next.disabled = !nextCursor;
        pageLabel.textContent = t('Page {page}', {page: page + 1});
        status.textContent = result.rows.length ? t('Newest recorded events first. Downloads include all matching records, not just this page.') : t('No activity matches the current filters.');
        if (result.types) {
          const select = form.elements.event;
          const value = select.value;
          select.replaceChildren(new Option(t('All events'), ''));
          for (const type of result.types) select.add(new Option(type.replaceAll('_', ' '), type));
          if (value && !result.types.includes(value)) select.add(new Option(value.replaceAll('_', ' '), value));
          select.value = value;
        }
      } catch (error) {
        if (current === generation && !controller.signal.aborted) {
          status.textContent = t('Could not load activity. Please retry.');
          previous.disabled = page === 0;
        }
      }
    }
    let timer;
    form.addEventListener('submit', event => event.preventDefault());
    form.addEventListener('input', event => {
      if (event.target.name !== 'q') return;
      clearTimeout(timer); timer = setTimeout(() => load(true), 300);
    });
    form.addEventListener('change', event => {
      if (event.target.name === 'q') return;
      clearTimeout(timer);
      if (event.target.name === 'context') {form.elements.event.value = ''; clearLink();}
      load(true);
    });
    form.addEventListener('reset', () => {clearLink(); setTimeout(() => load(true), 0);});
    previous.addEventListener('click', () => {page--; load();});
    next.addEventListener('click', () => {pages[++page] = nextCursor; load();});
    document.getElementById('activityRefresh').addEventListener('click', () => load(true));
    document.getElementById('activityShowPractice').addEventListener('click', () => {
      clearLink();
      form.elements.context.value = 'practice'; form.elements.event.value = ''; load(true);
    });
    root.querySelectorAll('[data-export]').forEach(button => button.addEventListener('click', async () => {
      if (exporting || !config) return;
      exporting = true;
      const current = exportGeneration;
      root.querySelectorAll('[data-export]').forEach(node => {node.disabled = true;});
      const options = button.dataset.export === 'all' ? {context: 'all'} :
        button.dataset.export === 'summary' ? {...filters(), context: 'summary'} : filters();
      await prepare(config.exportUrl, options,
        document.getElementById('activityExportStatus'), document.getElementById('activityExportLink'), () => current !== exportGeneration);
      if (current === exportGeneration) {
        exporting = false;
        root.querySelectorAll('[data-export]').forEach(node => {node.disabled = false;});
      }
    }));
    window.ModuLearnActivity = {open(button) {
      clearTimeout(timer);
      ++exportGeneration; exporting = false;
      root.querySelectorAll('[data-export]').forEach(node => {node.disabled = false;});
      document.getElementById('activityExportLink').hidden = true;
      document.getElementById('activityExportStatus').textContent = '';
      config = {url: button.dataset.activityUrl, exportUrl: button.dataset.exportUrl};
      clearLink();
      document.getElementById('sessionActivityModalTitle').textContent = button.dataset.sessionTitle;
      document.getElementById('activityPracticeLink').href = button.dataset.practiceUrl;
      document.getElementById('activityPracticeLink').target = '_blank';
      document.getElementById('activityPracticeLink').rel = 'noopener';
      load(true);
    }};
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize);
  else initialize();
})();
