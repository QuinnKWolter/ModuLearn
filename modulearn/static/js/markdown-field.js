/* Reusable, opt-in Markdown textarea. Original names, values and input events are preserved. */
(() => {
  const t = s => window.ModuLearnI18n?.t(s) || s;
  const fields = new Map();
  // Inline SVG keeps these controls self-contained, without an icon-font dependency.
  const icons = {
    link:'<path d="m10 13 4-4m-6 6-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 3 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
    bullet:'<path d="M9 5h12M9 12h12M9 19h12"/><circle cx="3" cy="5" r="1"/><circle cx="3" cy="12" r="1"/><circle cx="3" cy="19" r="1"/>',
    ordered:'<path d="M10 5h11M10 12h11M10 19h11M3 2h1v5M2 7h4M2 10c4-2 5 2 1 3l-1 1h4M2 17h4l-2 2c4-1 3 4-2 2"/>',
  };
  let sequence = 0;
  const selector = 'textarea[data-markdown-editor]';
  function enhance(root) {
    if (!window.ModuLearnInlineMarkdown) return; // Ordinary textareas remain usable if the editor fails to load.
    const candidates = [...root.querySelectorAll(selector)];
    if (root.matches?.(selector)) candidates.unshift(root);
    candidates.forEach(field => {
      if (fields.has(field)) return;
      const labelCopy = field.labels?.[0]?.cloneNode(true);
      labelCopy?.querySelectorAll('input,textarea,select,button').forEach(node => node.remove());
      const accessibleLabel = field.getAttribute('aria-label') || labelCopy?.textContent.trim() || field.placeholder || t('Prompt');
      const shell = document.createElement('div'); shell.className = 'form-markdown';
      const toolbar = document.createElement('div'); toolbar.className = 'form-markdown-toolbar';
      const tools = document.createElement('div'); tools.className = 'form-markdown-tools';
      const toggle = document.createElement('button'); toggle.type = 'button'; toggle.textContent = t('Markdown source'); toggle.setAttribute('aria-pressed', 'false');
      const host = document.createElement('div'); host.className = 'form-markdown-editor'; host.dataset.noUiTranslate = '';
      host.id = `form-markdown-${++sequence}`; toggle.setAttribute('aria-controls', host.id);
      const error = document.createElement('p'); error.className = 'form-markdown-error'; error.hidden = true; error.setAttribute('role','alert');
      error.id = host.id + '-error';
      toolbar.append(tools, toggle);
      // A contenteditable inside <label> would activate its first toolbar button on every click.
      let caption, captionGroup, captionClass;
      if (field.parentElement.tagName === 'LABEL') {
        caption = field.parentElement;
        captionClass = caption.className;
        const group = document.createElement('div'); group.className = caption.className;
        captionGroup = group;
        caption.replaceWith(group); group.append(caption, shell); caption.className = 'form-markdown-label';
      } else field.before(shell);
      shell.append(toolbar, field, host, error);
      let editor, source = false, changing = false;
      const originalFocus = field.focus;
      const wasHidden = field.hidden;
      const controller = new AbortController();
      const listen = (target, type, handler) => target.addEventListener(type, handler, {signal:controller.signal});
      function ensure() {
        if (!editor) {
          const wasFocused = document.activeElement === field;
          editor = window.ModuLearnInlineMarkdown.mount(host, {
            value:field.value, label:accessibleLabel, hint:field.placeholder, maxLength:field.maxLength,
            onChange(value) {
              changing = true; field.value = value; field.setCustomValidity(''); error.hidden = true;
              editor.invalid('');
              field.dispatchEvent(new Event('input', {bubbles:true}));
              changing = false;
            },
          });
          field.hidden = true;
          if (wasFocused) editor.focus();
        }
        editor.sync(field.value);
        return editor;
      }
      for (const [kind, caption, symbol] of [
        ['bold','Bold','B'],['italic','Italic','I'],['strike','Strikethrough','S'],['heading','Heading','H'],
        ['bullet','Bulleted list','•'],['ordered','Numbered list','1.'],['task','Checklist','☑'],
        ['indent','Indent','⇥'],['outdent','Outdent','⇤'],['quote','Blockquote','❝'],
        ['link','Insert link','↗'],['image','Insert image','▧'],['table','Insert table','▦'],
        ['code','Inline code','<>'],['codeblock','Code block','{ }'],['rule','Horizontal rule','―'],
      ]) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = symbol;
        if (icons[kind]) {
          const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
          svg.setAttribute('viewBox','0 0 24 24'); svg.setAttribute('aria-hidden','true');
          svg.setAttribute('fill','none'); svg.setAttribute('stroke','currentColor');
          svg.setAttribute('stroke-width','1.7'); svg.setAttribute('stroke-linecap','round'); svg.setAttribute('stroke-linejoin','round');
          svg.innerHTML=icons[kind]; button.replaceChildren(svg);
        }
        button.className = 'form-format-' + kind; button.title = t(caption); button.setAttribute('aria-label', t(caption));
        listen(button, 'mousedown', event => event.preventDefault());
        listen(button, 'click', event => { event.preventDefault(); ensure().format(kind); });
        tools.append(button);
      }
      field.focus = () => ensure().focus();
      if (caption) listen(caption, 'click', event => { event.preventDefault(); ensure().focus(); });
      listen(field, 'input', () => { if (!changing) editor?.sync(field.value); });
      listen(field, 'invalid', event => {
        event.preventDefault(); const view = ensure(); error.textContent = field.validationMessage;
        error.hidden = false; view.invalid(field.validationMessage); view.focus();
      });
      listen(toggle, 'click', event => {
        event.preventDefault(); source = !source; ensure().source(source);
        toggle.setAttribute('aria-pressed', String(source));
      });
      const entry = {
        update() { if (shell.getClientRects().length) ensure(); },
        destroy() {
          visibility.unobserve(shell); fields.delete(field); controller.abort(); editor?.destroy();
          field.focus = originalFocus; field.hidden = wasHidden;
          field.removeAttribute('data-markdown-editor');
          if (caption) { caption.append(field); caption.className=captionClass; captionGroup.replaceWith(caption); }
          else shell.before(field);
          shell.remove();
        },
        shell, focus:()=>ensure().focus(), sync:()=>editor?.sync(field.value),
      };
      fields.set(field, entry); visibility.observe(shell);
    });
  }
  const visibility = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) [...fields.values()].find(field => field.shell === entry.target)?.update();
  }));
  window.ModuLearnMarkdownField = {
    enhance,
    mount(field) { field.setAttribute('data-markdown-editor',''); enhance(field); return fields.get(field); },
  };
  enhance(document);
  new MutationObserver(records => {
    if (records.some(r => [...r.addedNodes].some(n => n.nodeType === 1 && (n.matches?.(selector) || n.querySelector?.(selector))))) enhance(document);
    for (const [field, entry] of fields) if (!field.isConnected) { visibility.unobserve(entry.shell); entry.destroy(); fields.delete(field); }
  }).observe(document.body, {childList:true, subtree:true});
  document.addEventListener('reset', event => {
    setTimeout(() => { for (const [field, entry] of fields) if (event.target.contains(field)) entry.update(); }, 0);
  });

})();
