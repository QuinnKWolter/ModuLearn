/* One server-selected catalog. Never translate authored content or code. */
(function () {
  'use strict';
  const language = (window.ModuLearnLanguage || document.documentElement.lang || 'en').toLowerCase().replace('_', '-');
  const catalog = JSON.parse(document.getElementById('modulearn-ui-messages')?.textContent || '{}');
  const attributes = ['aria-label', 'alt', 'title', 'placeholder', 'data-ready-label', 'data-checking-label', 'data-empty-label', 'data-error-label'];
  const skip = 'script, style, code, pre, textarea, [data-no-ui-translate], [translate="no"], [contenteditable]';
  const attributeSelector = attributes.map(name => '[' + name + ']').join(',');
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const cache = new Map(), lastText = new WeakMap(), lastAttributes = new WeakMap(), pending = new Set();
  let observer, scheduled = false;
  const options = {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: attributes};
  function t(message, parameters = {}) {
    const value = own(catalog, message) ? catalog[message] : String(message);
    // Interpolate after translation: names, titles and answers are data.
    return value.replace(/\{(\w+)\}/g, (match, key) => own(parameters, key) ? String(parameters[key]) : match);
  }
  function translateString(value) {
    if (!value || language === 'en') return value;
    if (cache.has(value)) return cache.get(value);
    const core = value.trim().replace(/\s+/g, ' ');
    let translated = own(catalog, core) ? catalog[core] : core;
    // Complete catalogued count labels; never replace arbitrary substrings.
    if (translated === core) {
      const count = core.match(/^(\d+) (.+)$/);
      if (count && own(catalog, '{count} ' + count[2])) translated = t('{count} ' + count[2], {count: count[1]});
    }
    const result = translated === core ? value : value.match(/^\s*/)[0] + translated + value.match(/\s*$/)[0];
    if (cache.size >= 2048) cache.clear();
    cache.set(value, result); return result;
  }
  function translateText(node) {
    if (!node.nodeValue?.trim() || !node.parentElement || node.parentElement.closest(skip) || lastText.get(node) === node.nodeValue) return;
    const translated = translateString(node.nodeValue);
    if (translated !== node.nodeValue) node.nodeValue = translated;
    lastText.set(node, node.nodeValue);
  }
  function translateAttributes(element) {
    if (!element?.getAttribute || element.closest(skip)) return;
    const previous = lastAttributes.get(element) || {};
    for (const attribute of attributes) {
      const value = element.getAttribute(attribute);
      if (!value || previous[attribute] === value) continue;
      const translated = translateString(value);
      if (translated !== value) element.setAttribute(attribute, translated);
      previous[attribute] = translated;
    }
    lastAttributes.set(element, previous);
  }
  function translateTree(root) {
    if (language === 'en' || !root) return;
    if (root.nodeType === Node.TEXT_NODE) { translateText(root); return; }
    if (!root.querySelectorAll || root.closest?.(skip)) return;
    translateAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (node.nodeType === Node.ELEMENT_NODE) return node.matches(skip) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_SKIP;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    while (walker.nextNode()) translateText(walker.currentNode);
    root.querySelectorAll(attributeSelector).forEach(translateAttributes);
  }
  function flush() {
    scheduled = false; observer?.disconnect();
    try {
      for (const node of pending) {
        if (!node.isConnected) continue;
        let ancestor = node.parentNode, covered = false;
        while (ancestor) { if (pending.has(ancestor)) { covered = true; break; } ancestor = ancestor.parentNode; }
        if (!covered) translateTree(node);
      }
    } finally { pending.clear(); observer?.observe(document.body, options); }
  }
  window.ModuLearnI18n = {language, t, translateTree,
    number: (value, options) => new Intl.NumberFormat(language, options).format(value),
    plural: (messages, count, parameters = {}) => t(messages[new Intl.PluralRules(language).select(count)] || messages.other, {...parameters, count})
  };
  function start() {
    if (language === 'en' || !document.body) return;
    translateTree(document.body); document.title = translateString(document.title);
    if (!window.MutationObserver) return;
    observer = new MutationObserver(mutations => {
      for (const mutation of mutations) {
        if (mutation.type === 'childList') mutation.addedNodes.forEach(node => pending.add(node));
        else pending.add(mutation.target);
      }
      if (!scheduled && pending.size) { scheduled = true; queueMicrotask(flush); }
    });
    observer.observe(document.body, options);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
