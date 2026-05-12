/**
 * Bootstrap JavaScript Compatibility Layer for Tailwind CSS Migration
 * Provides the same API surface as Bootstrap 5 JS so existing code continues to work.
 * Handles: Modal, Tooltip, Toast, Collapse, Tabs, Dismiss
 */
(function () {
  'use strict';

  /* ======================================================================= */
  /* Modal                                                                    */
  /* ======================================================================= */
  const _modalInstances = new Map();

  class Modal {
    constructor(element) {
      if (typeof element === 'string') element = document.querySelector(element);
      this._element = element;
      this._relatedTarget = null;
      if (element) _modalInstances.set(element, this);
    }

    show() {
      const el = this._element;
      if (!el) return;
      const showEvt = new Event('show.bs.modal', { bubbles: true, cancelable: true });
      showEvt.relatedTarget = this._relatedTarget || null;
      el.dispatchEvent(showEvt);
      if (showEvt.defaultPrevented) return;

      el.classList.remove('hidden');
      el.classList.add('flex');
      el.removeAttribute('aria-hidden');
      document.body.style.overflow = 'hidden';

      requestAnimationFrame(() => {
        const shownEvt = new Event('shown.bs.modal', { bubbles: true });
        el.dispatchEvent(shownEvt);
      });
    }

    hide() {
      const el = this._element;
      if (!el) return;
      const hideEvt = new Event('hide.bs.modal', { bubbles: true, cancelable: true });
      el.dispatchEvent(hideEvt);
      if (hideEvt.defaultPrevented) return;

      el.classList.add('hidden');
      el.classList.remove('flex');
      el.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';

      setTimeout(() => {
        const hiddenEvt = new Event('hidden.bs.modal', { bubbles: true });
        el.dispatchEvent(hiddenEvt);
      }, 150);
    }

    static getOrCreateInstance(element) {
      if (typeof element === 'string') element = document.querySelector(element);
      if (!element) return new Modal(null);
      return _modalInstances.get(element) || new Modal(element);
    }

    static getInstance(element) {
      if (typeof element === 'string') element = document.querySelector(element);
      return element ? (_modalInstances.get(element) || null) : null;
    }
  }

  /* ======================================================================= */
  /* Tooltip                                                                  */
  /* ======================================================================= */
  class Tooltip {
    constructor(element, options) {
      this._element = element;
      this._options = options || {};
      this._tip = null;
    }

    show() {
      if (this._tip) return;
      const text = this._options.title || this._element.getAttribute('title') || '';
      if (!text) return;

      this._tip = document.createElement('div');
      this._tip.className =
        'fixed z-[9999] px-3 py-1.5 text-xs text-white bg-gray-900 rounded-lg shadow-lg pointer-events-none transition-opacity';
      this._tip.textContent = text;
      document.body.appendChild(this._tip);

      const rect = this._element.getBoundingClientRect();
      const tipRect = this._tip.getBoundingClientRect();
      this._tip.style.top = rect.top - tipRect.height - 6 + 'px';
      this._tip.style.left = rect.left + rect.width / 2 - tipRect.width / 2 + 'px';
    }

    hide() {
      if (this._tip) { this._tip.remove(); this._tip = null; }
    }

    dispose() { this.hide(); }
  }

  /* ======================================================================= */
  /* Toast                                                                    */
  /* ======================================================================= */
  class Toast {
    constructor(element) { this._element = element; }

    show() {
      if (!this._element) return;
      this._element.classList.remove('hidden');
      setTimeout(() => { if (this._element) this._element.classList.add('hidden'); }, 5000);
    }
  }

  /* ======================================================================= */
  /* Expose global bootstrap object                                           */
  /* ======================================================================= */
  window.bootstrap = { Modal, Tooltip, Toast };

  /* ======================================================================= */
  /* Delegated data-bs-toggle handlers                                        */
  /* ======================================================================= */
  document.addEventListener('click', function (e) {
    /* --- data-bs-toggle --- */
    var trigger = e.target.closest('[data-bs-toggle]');
    if (trigger) {
      var action = trigger.getAttribute('data-bs-toggle');
      var sel = trigger.getAttribute('data-bs-target') || trigger.getAttribute('href');
      var target = sel ? document.querySelector(sel) : null;

      if (action === 'modal' && target) {
        e.preventDefault();
        var m = Modal.getOrCreateInstance(target);
        m._relatedTarget = trigger;
        m.show();
      }

      if (action === 'collapse' && target) {
        e.preventDefault();
        var hidden = target.classList.contains('hidden');
        if (hidden) {
          target.classList.remove('hidden');
          target.classList.add('show');
          trigger.setAttribute('aria-expanded', 'true');
          setTimeout(function () {
            target.dispatchEvent(new Event('shown.bs.collapse', { bubbles: true }));
          }, 50);
        } else {
          target.classList.add('hidden');
          target.classList.remove('show');
          trigger.setAttribute('aria-expanded', 'false');
        }
      }

      if (action === 'tab' && target) {
        e.preventDefault();
        var container = trigger.closest('[role="tablist"], ul, nav');
        if (container) {
          container.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (t) {
            t.classList.remove('active', 'text-blue-600', 'border-blue-600', 'dark:text-blue-400');
            t.classList.add('text-gray-500', 'dark:text-gray-400');
            var p = document.querySelector(t.getAttribute('data-bs-target'));
            if (p) { p.classList.add('hidden'); p.classList.remove('show', 'active'); }
          });
        }
        trigger.classList.add('active', 'text-blue-600', 'border-blue-600');
        trigger.classList.remove('text-gray-500', 'dark:text-gray-400');
        target.classList.remove('hidden');
        target.classList.add('show', 'active');
      }

      if (action === 'tooltip') {
        /* no-op, handled by CSS title or Tooltip class */
      }
    }

    /* --- data-bs-dismiss --- */
    var dismiss = e.target.closest('[data-bs-dismiss]');
    if (dismiss) {
      var dtype = dismiss.getAttribute('data-bs-dismiss');

      if (dtype === 'modal') {
        var modalEl = dismiss.closest('.modal-overlay');
        if (modalEl) Modal.getOrCreateInstance(modalEl).hide();
      }

      if (dtype === 'alert') {
        var alertEl = dismiss.closest('[role="alert"]') || dismiss.parentElement;
        if (alertEl) {
          alertEl.style.transition = 'opacity .15s';
          alertEl.style.opacity = '0';
          setTimeout(function () { alertEl.remove(); }, 150);
        }
      }

      if (dtype === 'toast') {
        var toastEl = dismiss.closest('[role="alert"]') || dismiss.parentElement;
        if (toastEl) toastEl.classList.add('hidden');
      }
    }
  });

  /* Close modal on backdrop click (click directly on the overlay, not dialog) */
  document.addEventListener('mousedown', function (e) {
    if (e.target.classList.contains('modal-backdrop-close')) {
      var modalEl = e.target.closest('.modal-overlay');
      if (modalEl) Modal.getOrCreateInstance(modalEl).hide();
    }
  });
})();
