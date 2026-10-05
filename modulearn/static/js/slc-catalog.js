(() => {
  'use strict';
  const dialog = document.getElementById('slcCatalog');
  const form = document.getElementById('customModuleForm');
  if (!dialog || !form) return;
  const find = selector => dialog.querySelector(selector);
  const results = find('[data-catalog-results]');
  const detail = find('[data-catalog-detail]');
  const query = find('[data-catalog-query]');
  const filters = [...dialog.querySelectorAll('[data-catalog-filter]')];
  const sort = find('[data-catalog-sort]');
  const count = find('[data-catalog-count]');
  const warning = find('[data-catalog-warning]');
  const prev = find('[data-catalog-prev]');
  const next = find('[data-catalog-next]');
  const selection = form.querySelector('[data-catalog-selection]');
  let page = 1, pages = 1, listRequest, detailRequest, timer, opener;
  const moreFilters = find('.slc-filters details');
  filters.forEach(select => { select.dataset.placeholder = select.options[0].textContent; });
  function remember() {
    try {
      sessionStorage.setItem(dialog.dataset.storageKey, JSON.stringify({
        query: query.value, sort: sort.value, page, moreFilters: moreFilters.open,
        filters: Object.fromEntries(filters.map(select => [select.dataset.catalogFilter, select.value])),
      }));
    } catch (_) { /* Browsing still works when browser storage is unavailable. */ }
  }
  try {
    const saved = JSON.parse(sessionStorage.getItem(dialog.dataset.storageKey) || 'null');
    if (saved && typeof saved === 'object') {
      query.value = typeof saved.query === 'string' ? saved.query : '';
      if ([...sort.options].some(option => option.value === saved.sort)) sort.value = saved.sort;
      page = Number.isSafeInteger(saved.page) && saved.page > 0 ? saved.page : 1;
      moreFilters.open = saved.moreFilters === true;
      filters.forEach(select => {
        const value = saved.filters?.[select.dataset.catalogFilter];
        if (typeof value !== 'string' || !value) return;
        if (select.dataset.catalogFilter === 'source' && !['pitt', 'splice'].includes(value)) return;
        if (![...select.options].some(option => option.value === value)) select.add(new Option(value, value));
        select.value = value;
      });
    }
  } catch (_) { /* Ignore unavailable storage or invalid saved state. */ }
  moreFilters.addEventListener('toggle', remember);

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  function button(text, action, className) {
    const element = node('button', text, className);
    element.type = 'button';
    element.addEventListener('click', action);
    return element;
  }
  function externalLink(text, url, className) {
    const link = node('a', text, className);
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }
  async function get(url, signal) {
    const response = await fetch(url, {signal, headers: {'Accept': 'application/json'}});
    if (response.redirected || !response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('Your session may have expired. Close the catalog and sign in again.');
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The catalog could not be loaded. Please retry.');
    return data;
  }
  function closeDetail() {
    detailRequest?.abort();
    detail.hidden = true;
    dialog.querySelector('.slc-card[aria-pressed=true]')?.focus();
  }
  function close() {
    clearTimeout(timer);
    remember();
    listRequest?.abort();
    detailRequest?.abort();
    dialog.close();
    opener?.focus();
  }
  dialog.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      // A focused search input otherwise clears itself before dialog dismissal.
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  });
  dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
  dialog.querySelectorAll('[data-catalog-close]').forEach(el => el.addEventListener('click', close));
  document.querySelectorAll('[data-open-slc-catalog]').forEach(el => el.addEventListener('click', () => {
    opener = el;
    const unit = form.querySelector('[name=unit_id]');
    find('[data-catalog-destination]').textContent = `Adding to: ${unit?.selectedOptions[0]?.textContent.trim() || 'your unit'}`;
    dialog.showModal();
    query.focus();
    load();
  }));

  function clearSelection() {
    form.elements.catalog_source.value = '';
    form.elements.catalog_item_id.value = '';
    selection.hidden = true;
  }
  form.elements.content_url.addEventListener('input', clearSelection);
  form.elements.module_type.addEventListener('change', clearSelection);
  function choose(item) {
    form.elements.title.value = item.title;
    form.elements.description.value = item.description;
    form.elements.content_url.value = item.selected_delivery.url;
    form.elements.catalog_source.value = item.source;
    form.elements.catalog_item_id.value = item.id;
    selection.textContent = `${item.source_label} · ${item.provider} · ${item.selected_delivery.protocol} delivery selected. Review the details, then choose Add Module.`;
    selection.hidden = false;
    close();
    form.elements.title.focus();
  }
  form.addEventListener('reset', clearSelection);

  function badges(values) {
    const wrap = node('div', null, 'slc-badges');
    values.filter(Boolean).forEach(value => wrap.append(node('span', value, 'slc-badge')));
    return wrap;
  }
  function renderCard(item) {
    const card = button('', () => showDetail(item, card), 'slc-card');
    card.setAttribute('aria-label', `View details: ${item.title}`);
    card.setAttribute('aria-pressed', 'false');
    const eyebrow = node('div', null, 'slc-eyebrow');
    eyebrow.append(node('span', item.provider), node('span', item.source_label));
    card.append(eyebrow, node('h3', item.title), node('p', item.description || item.type));
    card.append(badges([...item.languages, ...item.content_languages, item.protocols.includes('SPLICE') ? 'SPLICE' : item.protocols[0], item.status.startsWith('broken') ? 'Needs repair' : '']));
    return card;
  }
  function fillFacets(facets, totals) {
    filters.forEach(select => {
      const field = select.dataset.catalogFilter;
      if (!facets[field]) return;
      const value = select.value;
      select.replaceChildren(new Option(`${select.dataset.placeholder} (${totals[field].toLocaleString()})`, ''));
      facets[field].forEach(facet => {
        const option = new Option(`${facet.label || facet.value} (${facet.count.toLocaleString()})`, facet.value);
        option.disabled = facet.count === 0;
        select.add(option);
      });
      if (value && ![...select.options].some(option => option.value === value)) {
        const option = new Option(`${value} (0)`, value);
        option.disabled = true;
        select.add(option);
      }
      select.value = value;
    });
  }
  async function load() {
    remember();
    listRequest?.abort();
    const controller = new AbortController();
    listRequest = controller;
    const params = new URLSearchParams({q: query.value.trim(), sort: sort.value, page: String(page)});
    filters.forEach(select => { if (select.value) params.set(select.dataset.catalogFilter, select.value); });
    results.setAttribute('aria-busy', 'true');
    count.textContent = 'Finding learning activities…';
    prev.disabled = next.disabled = true;
    warning.hidden = true;
    try {
      const data = await get(`${dialog.dataset.searchUrl}?${params}`, controller.signal);
      if (controller.signal.aborted) return;
      page = data.page; pages = data.pages;
      fillFacets(data.facets, data.facet_totals);
      remember();
      count.textContent = `${data.total.toLocaleString()} activities${query.value.trim() ? ' matching your search' : ' to explore'}`;
      const cards = [];
      let group = null;
      data.items.forEach(item => {
        if (['provider', 'type'].includes(sort.value) && item[sort.value] !== group) {
          group = item[sort.value];
          cards.push(node('h3', group, 'slc-result-group'));
        }
        cards.push(renderCard(item));
      });
      results.replaceChildren(...cards);
      if (!data.items.length) results.append(node('p', 'No activities match these filters. Try another keyword or reset your filters.', 'slc-empty'));
      warning.textContent = data.warnings.join(' ');
      warning.hidden = !data.warnings.length;
      find('[data-catalog-page]').textContent = `Page ${page} of ${pages}`;
      prev.disabled = page <= 1; next.disabled = page >= pages;
      results.parentElement.scrollTop = 0;
    } catch (error) {
      if (error.name !== 'AbortError') {
        results.replaceChildren(node('p', error.message, 'slc-empty'));
        count.textContent = 'Unable to load catalog';
        find('[data-catalog-page]').textContent = '';
      }
    } finally {
      if (listRequest === controller) results.setAttribute('aria-busy', 'false');
    }
  }
  function changed() { page = 1; closeDetail(); load(); }
  query.addEventListener('input', () => { page = 1; remember(); clearTimeout(timer); timer = setTimeout(changed, 300); });
  query.addEventListener('keydown', event => { if (event.key === 'Enter') { clearTimeout(timer); changed(); } });
  filters.forEach(select => select.addEventListener('change', changed));
  sort.addEventListener('change', changed);
  find('[data-catalog-reset]').addEventListener('click', () => {
    query.value = ''; sort.value = 'title'; filters.forEach(select => select.value = ''); changed();
  });
  find('[data-catalog-retry]').addEventListener('click', load);
  prev.addEventListener('click', () => { if (page > 1) { page--; closeDetail(); load(); } });
  next.addEventListener('click', () => { if (page < pages) { page++; closeDetail(); load(); } });

  async function showDetail(summary, card) {
    detailRequest?.abort();
    const controller = new AbortController();
    detailRequest = controller;
    dialog.querySelectorAll('.slc-card').forEach(el => el.setAttribute('aria-pressed', String(el === card)));
    detail.hidden = false;
    detail.replaceChildren(button('← Back to results', closeDetail), node('p', 'Loading activity details…'));
    detail.scrollTop = 0;
    detail.querySelector('button').focus();
    try {
      const params = new URLSearchParams({source: summary.source, id: summary.id});
      const item = await get(`${dialog.dataset.detailUrl}?${params}`, controller.signal);
      if (controller.signal.aborted) return;
      const back = button('← Back to results', closeDetail);
      detail.replaceChildren(back, node('h3', item.title), badges([item.source_label, item.provider, item.type]));
      if (item.stale) detail.append(node('p', 'Showing cached metadata while the catalog is unavailable.', 'slc-warning'));
      if (item.status.startsWith('broken')) detail.append(node('p', 'The catalog marks this activity as needing repair. It cannot be added until repaired.', 'slc-warning'));
      const actions = node('div', null, 'slc-detail-actions');
      if (item.demo_url) actions.append(externalLink('Open demo ↗', item.demo_url, 'btn btn-outline-primary btn-sm'));
      const use = button('Use this activity', () => choose(item), 'btn btn-primary btn-sm');
      use.disabled = !item.selected_delivery || item.status.startsWith('broken');
      actions.append(use);
      detail.append(actions, node('p', item.description));
      const metadata = node('dl');
      const rows = {
        'Authors': item.authors.join(', '), 'Programming languages': item.languages.join(', '),
        'Content languages': item.content_languages.join(', '), 'License': item.license,
        'Keywords': item.tags.join(', '), 'Knowledge components': item.concepts.join(', '),
        'Delivery selected': item.selected_delivery ? `${item.selected_delivery.protocol}${item.selected_delivery.protocol === 'SPLICE' ? ' (preferred)' : ''}` : 'No usable endpoint published',
      };
      Object.entries(rows).filter(([,value]) => value).forEach(([label,value]) => metadata.append(node('dt', label), node('dd', value)));
      detail.append(metadata);
      const endpoints = node('details'); endpoints.append(node('summary', 'Delivery URLs'));
      item.delivery.forEach(endpoint => {
        const row = node('p', `${endpoint.protocol}: `);
        row.append(endpoint.url ? externalLink(endpoint.url, endpoint.url) : node('span', 'URL not published'));
        endpoints.append(row);
      });
      const raw = node('details');
      raw.append(node('summary', 'All catalog metadata'), node('pre', JSON.stringify(item.metadata, null, 2)));
      detail.append(endpoints, raw, node('p'));
      detail.lastChild.append(externalLink('View source catalog ↗', item.catalog_url));
      back.focus();
    } catch (error) {
      if (error.name !== 'AbortError') detail.append(node('p', error.message, 'slc-warning'), button('Retry details', () => showDetail(summary, card)));
    }
  }
})();
