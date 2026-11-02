(function () {
  const menus = [...document.querySelectorAll('.language-menu')];
  const dialog = document.getElementById('translation-report');
  const t = value => window.ModuLearnI18n?.t(value) || value;
  menus.forEach(menu => menu.addEventListener('toggle', () => {
    if (menu.open) menus.filter(other => other !== menu).forEach(other => { other.open = false; });
  }));
  document.addEventListener('click', event => menus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') menus.forEach(menu => { if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); } });
  });
  if (!dialog) return;
  let opener;
  const form = dialog.querySelector('form'), status = dialog.querySelector('[data-report-status]');
  document.querySelectorAll('[data-report-translation]').forEach(button => button.addEventListener('click', () => {
    opener = button.closest('details').querySelector('summary');
    menus.forEach(menu => { menu.open = false; });
    status.textContent = ''; dialog.showModal();
  }));
  dialog.querySelectorAll('[data-report-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('close', () => opener?.focus());
  form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('[type=submit]'); button.disabled = true;
    try {
      const response = await fetch(form.action, {method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json', 'X-CSRFToken':form.elements.csrfmiddlewaretoken.value},
        body:JSON.stringify({language:window.ModuLearnI18n.language, page_path:location.pathname,
          original_text:form.elements.original_text.value, suggestion:form.elements.suggestion.value})});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { status.textContent = t(data.error || 'Could not send the report. Please try again.'); return; }
      form.reset(); status.textContent = t(data.message);
    } catch (error) { status.textContent = t('Could not send the report. Please try again.'); }
    finally { button.disabled = false; }
  });
})();
