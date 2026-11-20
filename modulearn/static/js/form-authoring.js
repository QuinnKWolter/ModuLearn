/* Progressive authoring enhancements. Original named fields remain the source of truth. */
(() => {
  const markdown = window.ModuLearnMarkdown;
  if (!markdown) return;
  const t = (s) => window.ModuLearnI18n?.t(s) || s;

  function syncTitle(question) {
    const field = question.querySelector('textarea[name$="_prompt"]');
    const title = question.querySelector('[data-config-question-title]');
    if (field && title) {
      const number = [...question.parentElement.children].indexOf(question) + 1;
      title.textContent = `${number}. ${field.value.trim() || t('Untitled question')}`;
      title.title = field.value;
    }
  }
  document.addEventListener('input', event => {
    const question = event.target.closest('details[data-config-question]');
    if (question) syncTitle(question);
  });
  document.addEventListener('toggle', event => {
    const question = event.target;
    if (!question.open || !question.matches('.cfg-question-item')) return;
    for (const sibling of question.parentElement.children) if (sibling !== question && sibling.matches('.cfg-question-item')) sibling.open = false;
  }, true);
  document.addEventListener('click', event => {
    const add = event.target.closest('[data-add-inline-question]');
    if (add) {
      const panel = document.getElementById(add.dataset.addInlineQuestion);
      panel.open = true; panel.scrollIntoView({block:'nearest'}); panel.querySelector('textarea').focus();
    }
    const close = event.target.closest('[data-close-inline-question]');
    if (close) close.closest('details').open = false;
  });
})();
