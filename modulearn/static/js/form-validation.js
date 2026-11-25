/* Shared by live forms, paged surveys, and the untracked authoring preview. */
(() => {
  const wired = new WeakSet();
  function init(form) {
    if (wired.has(form)) return;
    wired.add(form);
    function validate() {
      form.querySelectorAll('[data-require-choice]').forEach(group => {
        const choices = [...group.querySelectorAll('input[type="checkbox"]')];
        // Native required on every checkbox would incorrectly require ALL choices.
        if (choices[0]) choices[0].required = !choices.some(choice => choice.checked);
      });
      form.querySelectorAll('textarea[required], input[required]:not([type]), input[type="text"][required]').forEach(field => {
        const message = window.ModuLearnI18n?.t('Please answer every required question.') || 'Please answer every required question.';
        field.setCustomValidity(field.value.trim() ? '' : message);
      });
    }
    form.addEventListener('input', validate);
    form.addEventListener('change', validate);
    form.addEventListener('reset', () => setTimeout(validate, 0));
    // Refresh constraints before the browser's native submit validation.
    form.addEventListener('click', validate, true);
    form.addEventListener('keydown', validate, true);
    validate();
  }
  window.ModuLearnFormValidation = {init};
  document.querySelectorAll('form[data-study-form], .survey form').forEach(init);
})();
