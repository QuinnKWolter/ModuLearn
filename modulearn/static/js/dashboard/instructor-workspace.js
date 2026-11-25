/* Navigation/presentation only. Existing dashboard controllers own all mutations. */
(() => {
  document.addEventListener('DOMContentLoaded', () => {
    const app = document.getElementById('instructorDashboardApp');
    const workspace = app?.querySelector('[data-workspace]');
    if (!workspace) return;
    const t = (key, params) => window.ModuLearnI18n.t(key, params);
    const nav = app.querySelector('#workspaceNavigation');
    const search = app.querySelector('#workspaceSearch');
    const status = app.querySelector('[data-workspace-status]');
    const browse = app.querySelector('[data-workspace-browse]');
    const storageKey = `modulearn.workspace.${app.dataset.workspaceUser}.${location.pathname}`;
    let saved = {}, current = '', explicitSelection = false;
    try { saved = JSON.parse(sessionStorage.getItem(storageKey) || '{}') || {}; } catch { /* Optional convenience. */ }
    const links = () => [...nav.querySelectorAll('[data-workspace-select]')];
    const panels = () => [...workspace.querySelectorAll('[data-workspace-panel]')];
    const normal = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim();
    function remember() {
      try { sessionStorage.setItem(storageKey, JSON.stringify({selected: current, search: search.value})); } catch { /* Private mode. */ }
    }
    function mobile(open) {
      workspace.dataset.mobileNav = open ? 'open' : 'closed';
      browse.setAttribute('aria-expanded', String(open));
    }
    function select(id, {user = false, historyMode = 'replace'} = {}) {
      const target = document.getElementById(id);
      if (!target?.matches('[data-workspace-panel]') || !workspace.contains(target)) return false;
      const hidingFocus = panels().some(panel => panel !== target && panel.contains(document.activeElement));
      panels().forEach(panel => { panel.hidden = panel !== target; });
      links().forEach(link => {
        if (link.getAttribute('aria-controls') === id) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
      current = id;
      if (user) explicitSelection = true;
      if (historyMode) {
        const url = new URL(location.href); url.hash = id;
        history[historyMode === 'push' ? 'pushState' : 'replaceState'](null, '', url);
      }
      remember();
      status.textContent = target.querySelector('h2,h3,h6')?.textContent.trim() || '';
      if (hidingFocus || (user && matchMedia('(max-width:900px)').matches)) {
        if (matchMedia('(max-width:900px)').matches) mobile(false);
        target.querySelector('h2,h3,h6')?.focus({preventScroll: true});
        target.scrollIntoView({block: 'start', behavior: 'instant'});
      }
      return true;
    }
    function filter() {
      const term = normal(search.value);
      links().forEach(link => { link.hidden = !!term && !normal(link.dataset.workspaceSearch || link.textContent).includes(term); });
      nav.querySelectorAll('[data-workspace-course]').forEach(group => {
        const any = [...group.querySelectorAll('[data-workspace-select]')].some(link => !link.hidden);
        group.hidden = !any;
        if (any) group.querySelector('.workspace-course-title').hidden = false;
      });
      nav.querySelectorAll('[data-workspace-group]').forEach(group => {
        const items = [...group.querySelectorAll('[data-workspace-select]')];
        group.hidden = !!term && items.length > 0 && items.every(link => link.hidden);
      });
      app.querySelector('[data-workspace-no-results]').hidden = !term || links().some(link => !link.hidden);
      remember();
    }
    app.addEventListener('click', event => {
      const link = event.target.closest('[data-workspace-select],[data-workspace-jump]');
      if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) {
        const id = link.getAttribute('href').slice(1);
        if (select(id, {user: true, historyMode: 'push'})) event.preventDefault();
      }
    });
    nav.addEventListener('keydown', event => {
      if (!event.target.matches('[data-workspace-select]')) return;
      const visible = links().filter(link => link.getClientRects().length);
      const index = visible.indexOf(event.target);
      const next = {ArrowDown: (index + 1) % visible.length, ArrowUp: (index - 1 + visible.length) % visible.length, Home: 0, End: visible.length - 1}[event.key];
      if (next !== undefined) { event.preventDefault(); visible[next]?.focus(); }
    });
    browse.addEventListener('click', () => { const open = workspace.dataset.mobileNav !== 'open'; mobile(open); if (open) search.focus(); });
    search.addEventListener('input', filter);
    app.querySelector('[data-workspace-clear]').addEventListener('click', () => { search.value = ''; filter(); search.focus(); });
    const historySelection = () => select(location.hash.slice(1), {historyMode: null});
    window.addEventListener('popstate', historySelection);
    window.addEventListener('hashchange', historySelection);
    workspace.classList.add('workspace-ready');
    const desired = location.hash.slice(1) || saved.selected;
    search.value = typeof saved.search === 'string' ? saved.search : '';
    if (!select(desired)) select(nav.querySelector('[data-workspace-default]')?.getAttribute('aria-controls') || links()[0]?.getAttribute('aria-controls') || 'workspace-welcome');
    filter();

    // Legacy data arrives asynchronously. Reuse its real action controls, without
    // cloning IDs/listeners or routing the selection through a server mutation.
    window.ModuLearnInstructorWorkspace = {
      legacyLoaded(groups) {
        const container = app.querySelector('#legacyGroupsContainer');
        const list = app.querySelector('[data-workspace-legacy-nav]');
        if (!container || !list) return;
        list.replaceChildren();
        [...container.children].forEach((panel, index) => {
          const group = groups[index];
          const id = `workspace-legacy-${encodeURIComponent(group.groupLogin || group.courseIds.join(',') || group.groupName)}`;
          panel.id = id; panel.dataset.workspacePanel = '';
          panel.className = 'workspace-panel'; panel.hidden = true;
          panel.firstElementChild.className = 'flex flex-col';
          const title = panel.querySelector('h6');
          const heading = document.createElement('h2'); heading.textContent = title.textContent;
          heading.id = `${id}-title`; heading.tabIndex = -1; heading.dataset.noUiTranslate = '';
          title.replaceWith(heading); panel.setAttribute('aria-labelledby', heading.id);
          const link = document.createElement('a'); link.href = `#${id}`;
          link.dataset.workspaceSelect = ''; link.dataset.workspaceSearch = `${group.groupName} ${group.groupLogin}`;
          link.setAttribute('aria-controls', id); link.textContent = group.groupName; link.dataset.noUiTranslate = '';
          list.append(link);
        });
        if (!explicitSelection && desired?.startsWith('workspace-legacy-')) select(desired);
        else if (current.startsWith('workspace-legacy-')) select(current) || select('workspace-welcome');
        filter();
      },
    };

    // Dashboard dialogs keep keyboard focus and return it to their invoker.
    // Native dialogs and the page guide retain their own focus management.
    const openDialogs = [], openers = new WeakMap();
    app.querySelectorAll('.modal-overlay').forEach(dialog => {
      dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true');
      const heading = dialog.querySelector('h2,h3,h4,h5');
      if (heading) { heading.id ||= `${dialog.id}-title`; dialog.setAttribute('aria-labelledby', heading.id); }
      dialog.querySelectorAll('[data-bs-dismiss="modal"]').forEach(button => {
        if (!button.hasAttribute('aria-label') && button.textContent.trim() === '×') button.setAttribute('aria-label', t('Close'));
      });
      dialog.addEventListener('show.bs.modal', event => { openers.set(dialog, event.relatedTarget || document.activeElement); });
      dialog.addEventListener('shown.bs.modal', () => {
        if (dialog.classList.contains('hidden')) return;
        if (!openDialogs.includes(dialog)) openDialogs.push(dialog);
        if (!document.body.classList.contains('driver-active')) focusable(dialog)[0]?.focus();
      });
      dialog.addEventListener('hidden.bs.modal', () => {
        const index = openDialogs.indexOf(dialog); if (index >= 0) openDialogs.splice(index, 1);
        if (!document.body.classList.contains('driver-active')) {
          const opener = openers.get(dialog);
          if (opener?.getClientRects().length) opener.focus({preventScroll:true});
        }
      });
    });
    function focusable(dialog) {
      return [...dialog.querySelectorAll('a[href],button,input,textarea,select,[tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length);
    }
    document.addEventListener('keydown', event => {
      if (document.body.classList.contains('driver-active') || document.querySelector('dialog[open]')) return;
      const dialog = openDialogs.at(-1); if (!dialog) return;
      if (event.key === 'Escape') { event.preventDefault(); window.bootstrap.Modal.getOrCreateInstance(dialog).hide(); }
      if (event.key === 'Tab') {
        const items = focusable(dialog), first = items[0], last = items.at(-1);
        if (!items.length) return;
        if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    });
    const menu = app.querySelector('.workspace-import');
    document.addEventListener('click', event => { if (!menu.contains(event.target)) menu.open = false; });
    menu.addEventListener('keydown', event => { if (event.key === 'Escape') { menu.open = false; menu.querySelector('summary').focus(); } });
  });
})();
