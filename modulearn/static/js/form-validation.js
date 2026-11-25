/* Question-level validation shared by live forms, surveys and authoring previews. */
(() => {
  const wired = new WeakSet();
  let sequence = 0;
  const t = message => window.ModuLearnI18n?.t(message) || message;
  function init(form) {
    if (wired.has(form)) return;
    wired.add(form);
    // Own the presentation: native checkbox tooltips imply a specific choice is mandatory.
    form.noValidate = true;
    const groups = [...form.querySelectorAll('fieldset, .survey-matrix tbody tr')];
    const states = groups.map(group => {
      const fields = [...group.querySelectorAll('input, textarea, select')];
      const error = group.querySelector('[data-form-error]') || document.createElement('p');
      error.className = 'form-question-error';
      error.dataset.formError = '';
      error.id = `form-question-error-${++sequence}`;
      error.setAttribute('aria-live', 'polite');
      if (!error.isConnected) (group.matches('tr') ? group.querySelector('th') : group).append(error);
      group.tabIndex = -1;
      const descriptions = new Map(fields.map(field => [field, field.getAttribute('aria-describedby')]));
      function message() {
        if (group.hasAttribute('data-require-choice') && !fields.some(field => field.type === 'checkbox' && field.checked)) {
          return t('Select at least one answer.');
        }
        if (fields.some(field => field.required && field.type === 'radio') && !fields.some(field => field.type === 'radio' && field.checked)) {
          return t('Select one answer.');
        }
        if (fields.some(field => field.required && !['radio', 'checkbox'].includes(field.type) && !field.value.trim())) {
          return t('Enter an answer.');
        }
        const invalid = fields.find(field => field.willValidate && !field.validity.valid);
        return invalid ? invalid.validationMessage : '';
      }
      function render() {
        const text = message();
        error.textContent = text;
        error.hidden = !text;
        group.classList.toggle('form-question-invalid', !!text);
        group.setAttribute('aria-invalid', String(!!text));
        if (text) group.setAttribute('aria-describedby', error.id);
        else group.removeAttribute('aria-describedby');
        fields.forEach(field => {
          if (text) {
            field.setAttribute('aria-invalid', 'true');
            field.setAttribute('aria-describedby', [descriptions.get(field), error.id].filter(Boolean).join(' '));
          } else {
            field.removeAttribute('aria-invalid');
            const original = descriptions.get(field);
            if (original) field.setAttribute('aria-describedby', original);
            else field.removeAttribute('aria-describedby');
          }
        });
        return !!text;
      }
      const state = {group, render};
      error.hidden = !error.textContent.trim();
      if (!error.hidden) render();
      return state;
    });
    form.addEventListener('submit', event => {
      if (event.submitter?.formNoValidate) return; // Survey Back intentionally permits incomplete pages.
      const invalid = states.filter(state => state.render());
      if (!invalid.length) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const group = invalid[0].group;
      group.focus({preventScroll: true});
      group.scrollIntoView({block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
    }, true);
    function update(event) {
      const state = states.find(item => item.group.contains(event.target));
      if (state?.group.classList.contains('form-question-invalid')) state.render();
    }
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('reset', () => setTimeout(() => {
      states.forEach(({group}) => {
        group.classList.remove('form-question-invalid');
        group.removeAttribute('aria-invalid');
        group.removeAttribute('aria-describedby');
        const error = group.querySelector('[data-form-error]');
        error.textContent = ''; error.hidden = true;
        group.querySelectorAll('[aria-invalid]').forEach(field => {
          field.removeAttribute('aria-invalid');
          const ids = (field.getAttribute('aria-describedby') || '').split(' ').filter(id => id !== error.id);
          if (ids.length) field.setAttribute('aria-describedby', ids.join(' '));
          else field.removeAttribute('aria-describedby');
        });
      });
    }, 0));
  }
  window.ModuLearnFormValidation = {init};
  document.querySelectorAll('form[data-study-form], .survey form').forEach(init);
})();
