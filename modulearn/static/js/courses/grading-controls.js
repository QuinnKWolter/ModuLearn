document.addEventListener('DOMContentLoaded', () => {
  const t = text => window.ModuLearnI18n?.t(text) || text;
  const inputs = [...document.querySelectorAll('[data-grade-module]')];
  inputs.forEach(input => input.addEventListener('change', () => {
    const id = input.name.match(/module_(\d+)_/)[1];
    document.querySelectorAll(`[data-grade-star="${id}"]`).forEach(star => { star.hidden = !input.checked; });
    const button = input.closest('[data-module-block]').querySelector('[data-grade-toggle]');
    if (button) {
      button.setAttribute('aria-pressed', String(input.checked));
      button.classList.toggle('is-on', input.checked);
      button.classList.toggle('is-off', !input.checked);
      button.querySelector('i').className = input.checked ? 'bi bi-star-fill' : 'bi bi-star';
      button.querySelector('[data-chip-label]').textContent = window.ModuLearnI18n?.t(input.checked ? 'Graded' : 'Practice') || (input.checked ? 'Graded' : 'Practice');
    }
  }));
  document.querySelectorAll('[data-grade-toggle]').forEach(button => button.addEventListener('click', event => {
    event.preventDefault(); event.stopPropagation();
    const input = button.closest('[data-module-block]').querySelector('[data-grade-module]');
    input.checked = !input.checked; input.dispatchEvent(new Event('change', {bubbles:true}));
  }));
  document.querySelectorAll('.cfg-chip-toggle').forEach(button => button.addEventListener('click', () => {
    button.classList.add('is-recent');
    clearTimeout(button._labelTimer);
    button._labelTimer = setTimeout(() => button.classList.remove('is-recent'), 2500);
  }));
  document.querySelectorAll('[data-schedule-toggle]').forEach(button => button.addEventListener('click', event => {
    event.preventDefault(); event.stopPropagation();
    const panel = document.getElementById(button.getAttribute('aria-controls'));
    panel.hidden = !panel.hidden;
    button.setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) { button.closest('[data-unit-block]').open = true; panel.querySelector('input').focus(); }
  }));
  document.querySelectorAll('.cfg-schedule').forEach(panel => {
    const syncSchedule = () => {
      const active = [...panel.querySelectorAll('input')].some(input => input.value);
      const button = document.querySelector(`[aria-controls="${panel.id}"]`);
      button?.classList.toggle('is-on', active);
      button?.classList.toggle('is-off', !active);
      if (button) {
        button.querySelector('[data-chip-label]').textContent = t(active ? 'Scheduled' : 'Unscheduled');
        button.title = t(active ? 'Scheduled' : 'Unscheduled');
      }
    };
    panel.addEventListener('input', syncSchedule);
    syncSchedule();
  });
  const form = document.getElementById('structureControlsForm');
  const save = document.querySelector('[data-grade-save]');
  const weighting = document.querySelector('[data-grade-weighting]');
  if (form && save && weighting) {
    // Compare values, rather than counting edits: undoing a change restores the clean state.
    const snapshot = () => JSON.stringify([...form.elements].filter(el => el.name && !el.disabled).map(el =>
      [el.name, el.type === 'checkbox' || el.type === 'radio' ? el.checked : el.value]));
    const initial = snapshot();
    const syncDirty = () => {
      const dirty = snapshot() !== initial;
      save.disabled = !dirty;
      weighting.setAttribute('aria-disabled', String(dirty));
      return dirty;
    };
    // Capture clicks too: ordering and lock controls update hidden inputs programmatically.
    let pending = false;
    const scheduleDirty = () => {
      if (pending) return;
      pending = true;
      queueMicrotask(() => { pending = false; syncDirty(); });
    };
    ['input', 'change', 'click'].forEach(type => document.addEventListener(type, scheduleDirty));
    weighting.addEventListener('click', event => {
      if (syncDirty()) {
        event.preventDefault();
        window.alert(t('Save your configuration changes before opening Grade Weighting.'));
      }
    });
    syncDirty();
  }
  const select = document.getElementById('gradeTypeSelect');
  if (!select) return;
  for (const type of [...new Set(inputs.map(input => input.dataset.gradeType))].sort()) {
    const option = document.createElement('option'); option.value = type;
    option.textContent = `${t(type)} (${inputs.filter(input => input.dataset.gradeType === type).length})`;
    select.append(option);
  }
  const set = (input, checked) => { input.checked = checked; input.dispatchEvent(new Event('change', {bubbles:true})); };
  document.querySelectorAll('[data-grade-all]').forEach(button => button.addEventListener('click', () => inputs.forEach(input => set(input, button.dataset.gradeAll === '1'))));
  document.getElementById('gradeSelectedType').addEventListener('click', () => inputs.filter(input => input.dataset.gradeType === select.value).forEach(input => set(input, true)));
});
