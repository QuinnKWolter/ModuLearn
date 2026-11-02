(() => {
  const form = document.getElementById('study-settings');
  if (!form) return;
  const original = JSON.stringify([...new FormData(form).entries()]);
  const save = form.querySelector('[data-studio-save]');
  const preview = document.querySelector('[data-start-study-preview]');
  function update() {
    const dirty = original !== JSON.stringify([...new FormData(form).entries()]);
    if (save && !form.querySelector('fieldset').disabled) save.disabled = !dirty;
    if (preview) {
      preview.disabled = dirty;
      preview.title = dirty ? 'Save or discard changes before starting a preview.' : '';
    }
  }
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  form.addEventListener('reset', () => setTimeout(update, 0));
  update();
})();
