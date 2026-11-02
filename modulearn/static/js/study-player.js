/* The server owns routing and deadlines. Polling also covers server-side LTI callbacks. */
(() => {
  const node = document.getElementById('study-player-config');
  if (!node) return;
  const config = JSON.parse(node.textContent);
  let pending = false, deadline = null, offset = 0;
  const form = document.querySelector('[data-study-form]');
  const fields = {}, visitId = crypto.randomUUID();
  if (form) {
    function observe(event) {
      const target = event.target;
      if (!target.name || !target.name.startsWith('question_') || !target.matches('textarea,input:not([type=radio]):not([type=checkbox])')) return;
      const value = fields[target.name] ||= {keystrokes:0,paste_count:0,copy_count:0,characters:0};
      if (event.type === 'keydown' && !event.repeat && !event.ctrlKey && !event.metaKey && (event.key.length === 1 || ['Backspace','Delete','Enter'].includes(event.key))) value.keystrokes++;
      if (event.type === 'paste') value.paste_count++;
      if (event.type === 'copy') value.copy_count++;
      value.characters = target.value.length;
    }
    ['keydown','paste','copy','input'].forEach(name => form.addEventListener(name, observe));
    function flush() {
      if (!Object.keys(fields).length) return;
      const data = new FormData();
      data.append('csrfmiddlewaretoken', form.querySelector('[name=csrfmiddlewaretoken]').value);
      data.append('summary', JSON.stringify({activity_id:Number(form.dataset.studyForm), fields, visit_id:visitId}));
      navigator.sendBeacon(config.input_url, data);
    }
    form.addEventListener('submit', flush);
    window.addEventListener('pagehide', flush);
    setInterval(flush, 15000);
  }
  async function refresh() {
    if (pending) return;
    pending = true;
    try {
      const response = await fetch(config.status_url, {credentials:'same-origin', cache:'no-store'});
      if (!response.ok) throw new Error('Study state unavailable');
      const data = await response.json();
      offset = Date.parse(data.server_time) - Date.now();
      deadline = data.deadline ? Date.parse(data.deadline) : null;
      if (data.url && new URL(data.url, location.href).pathname !== location.pathname) location.replace(data.url);
    } catch (_) { /* Retry on the next poll. */ }
    finally { pending = false; }
  }
  setInterval(() => {
    if (deadline && deadline <= Date.now() + offset) refresh();
  }, 500);
  setInterval(refresh, 5000);
  document.addEventListener('moduLearn:module-progress-updated', refresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  refresh();
})();
