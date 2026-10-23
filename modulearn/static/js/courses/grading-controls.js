document.addEventListener('DOMContentLoaded', () => {
  const inputs = [...document.querySelectorAll('[data-grade-module]')];
  const select = document.getElementById('gradeTypeSelect');
  if (!select) return;
  const t = text => window.ModuLearnI18n?.t(text) || text;
  for (const type of [...new Set(inputs.map(input => input.dataset.gradeType))].sort()) {
    const option = document.createElement('option'); option.value = type;
    option.textContent = `${t(type)} (${inputs.filter(input => input.dataset.gradeType === type).length})`;
    select.append(option);
  }
  const set = (input, checked) => { input.checked = checked; input.dispatchEvent(new Event('change', {bubbles:true})); };
  document.querySelectorAll('[data-grade-all]').forEach(button => button.addEventListener('click', () => inputs.forEach(input => set(input, button.dataset.gradeAll === '1'))));
  document.getElementById('gradeSelectedType').addEventListener('click', () => inputs.filter(input => input.dataset.gradeType === select.value).forEach(input => set(input, true)));
});
