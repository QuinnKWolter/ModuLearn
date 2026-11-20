/* Uses the participant renderer; previews never submit answers or save edits. */
(() => {
  const config = document.querySelector('[data-study-text-preview-url]');
  if (!config) return;
  const t = (s) => window.ModuLearnI18n?.t(s) || s;
  // Share the participant renderer with inline editors and whole-form previews.
  const cache = new Map();
  async function render(text) {
    if (cache.has(text)) return cache.get(text);
    const data = new FormData();
    data.append('text', text);
    data.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    const response = await fetch(config.dataset.studyTextPreviewUrl, {method:'POST', body:data, credentials:'same-origin'});
    if (!response.ok) throw new Error('Preview unavailable');
    const result = await response.json();
    if (typeof result.html !== 'string') throw new Error('Invalid preview');
    if (cache.size >= 80) cache.delete(cache.keys().next().value);
    cache.set(text, result.html);
    return result.html;
  }
  async function renderMany(texts) {
    const data = new FormData();
    texts.forEach(text => data.append('texts', text));
    data.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    const response = await fetch(config.dataset.studyTextPreviewUrl, {method:'POST', body:data, credentials:'same-origin'});
    if (!response.ok) throw new Error('Preview unavailable');
    const result = await response.json();
    if (!Array.isArray(result.html) || result.html.length !== texts.length || result.html.some(html => typeof html !== 'string')) throw new Error('Invalid preview');
    return result.html;
  }
  async function renderActivity(activity) {
    const data = new FormData();
    data.append('activity', JSON.stringify(activity));
    data.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    const response = await fetch(config.dataset.studyTextPreviewUrl, {method:'POST',body:data,credentials:'same-origin'});
    if (!response.ok) throw new Error('Preview unavailable');
    const result = await response.json();
    if (typeof result.html !== 'string') throw new Error('Invalid preview');
    return result.html;
  }
  window.ModuLearnMarkdown = {render, renderMany, renderActivity};
  // Activity authoring has one full preview, never individual field previews.
  if (config.hasAttribute('data-activity-authoring')) return;
  const dialog = document.createElement('dialog');
  dialog.className = 'study-text-preview';
  dialog.setAttribute('aria-labelledby', 'study-text-preview-title');
  const header = document.createElement('header'); header.className = 'study-text-preview-header';
  const title = document.createElement('h2'); title.id = 'study-text-preview-title'; title.textContent = t('Preview Text');
  const close = document.createElement('button');
  close.type = 'button'; close.className = 'study-text-preview-close'; close.textContent = t('Close Preview');
  const status = document.createElement('p'); status.className = 'study-text-preview-status'; status.setAttribute('role', 'status');
  const content = document.createElement('div'); content.className = 'study-prose'; content.dataset.noUiTranslate = '';
  header.append(title, close); dialog.append(header, status, content); document.body.append(dialog);
  close.addEventListener('click', () => dialog.close());
  let requestId = 0;
  dialog.addEventListener('close', () => { requestId++; });
  async function preview(field) {
    const id = ++requestId;
    content.replaceChildren(); content.hidden = true; status.hidden = false;
    status.textContent = t('Loading…');
    if (!dialog.open) dialog.showModal();
    if (!field.value.trim()) {
      status.textContent = t('This field is empty. Add text to preview it.');
      return;
    }
    try {
      const html = await render(field.value);
      if (id === requestId) {
        content.innerHTML = html; // Server escapes all authored HTML.
        content.hidden = false; status.hidden = true;
      }
    } catch (_) { if (id === requestId) status.textContent = t('Unable to load preview. Please try again.'); }
  }
  function enhance(root) {
    root.querySelectorAll('textarea').forEach(field => {
      if (field.matches('[data-question-prompt],[data-question-help],[name$="_prompt"],[name$="_help_text"],[name$="form_instructions"]')) return;
      if (field.dataset.textPreviewReady || !/description|instructions|prompt|help_text/.test(field.name || '') &&
          !field.matches('[data-question-prompt],[data-question-help]')) return;
      field.dataset.textPreviewReady = 'true';
      const button = document.createElement('button'); button.type = 'button';
      button.className = 'btn btn-sm btn-outline-secondary study-text-preview-button'; button.textContent = t('Preview Text');
      button.addEventListener('click', () => preview(field)); field.after(button);
    });
  }
  enhance(document);
  new MutationObserver(records => {
    if (records.some(r => [...r.addedNodes].some(n => n.nodeType === 1 && (n.matches?.('textarea') || n.querySelector?.('textarea'))))) enhance(document);
  }).observe(document.body, {childList:true, subtree:true});
})();
