(function () {
  var REFRESH_EVENT = 'moduLearn:refresh-next-module';
  var PROGRESS_EVENT = 'moduLearn:module-progress-updated';
  var refreshTimers = new WeakMap();

  function t(value) {
    return window.ModuLearnI18n && typeof window.ModuLearnI18n.t === 'function'
      ? window.ModuLearnI18n.t(value)
      : value;
  }

  function setButtonState(button, state) {
    var label = button.querySelector('[data-next-label]');
    var icon = button.querySelector('[data-next-icon]');
    var text = button.dataset.readyLabel || t('Next Module');

    button.classList.remove('btn-primary', 'btn-outline-secondary', 'opacity-75');
    button.dataset.nextState = state;
    if (state === 'checking') {
      text = button.dataset.checkingLabel || t('Checking...');
      button.classList.add('btn-outline-secondary');
      button.setAttribute('aria-disabled', 'true');
      if (icon) icon.className = 'bi bi-arrow-repeat';
    } else if (state === 'empty') {
      text = button.dataset.emptyLabel || t('No Unlocked Module');
      button.classList.add('btn-outline-secondary', 'opacity-75');
      button.setAttribute('aria-disabled', 'true');
      if (icon) icon.className = 'bi bi-lock';
    } else if (state === 'error') {
      text = button.dataset.errorLabel || t('Try Again');
      button.classList.add('btn-outline-secondary');
      button.removeAttribute('aria-disabled');
      if (icon) icon.className = 'bi bi-exclamation-circle';
    } else {
      button.classList.add('btn-primary');
      button.removeAttribute('aria-disabled');
      if (icon) icon.className = 'bi bi-arrow-right';
    }

    if (label) label.textContent = text;
  }

  function resolveNext(button) {
    if (!button || !button.dataset.nextUrl) {
      return Promise.resolve(null);
    }

    setButtonState(button, 'checking');
    return fetch(button.dataset.nextUrl, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    })
      .then(function (response) {
        if (!response.ok) throw new Error('Next module lookup failed');
        return response.json();
      })
      .then(function (data) {
        button.dataset.resolved = '1';
        if (data && data.available && data.url) {
          button.href = data.url;
          button.dataset.resolvedUrl = data.url;
          button.title = data.title ? t('Open') + ' ' + data.title : t('Open the next module');
          setButtonState(button, 'ready');
          return data;
        }
        button.removeAttribute('data-resolved-url');
        button.href = '#';
        button.title = (data && data.message) || t('No visible unlocked module is available yet');
        setButtonState(button, 'empty');
        return data || null;
      })
      .catch(function () {
        button.href = '#';
        button.removeAttribute('data-resolved');
        button.title = t('Could not check the next module. Try again.');
        setButtonState(button, 'error');
        return null;
      });
  }

  function scheduleRefresh(button, delay) {
    if (!button || !button.dataset.nextUrl) {
      return Promise.resolve(null);
    }
    var existing = refreshTimers.get(button);
    if (existing) {
      clearTimeout(existing);
    }
    return new Promise(function (resolve) {
      var timer = setTimeout(function () {
        refreshTimers.delete(button);
        resolve(button.moduLearnRefreshNextModule ? button.moduLearnRefreshNextModule() : resolveNext(button));
      }, typeof delay === 'number' ? delay : 120);
      refreshTimers.set(button, timer);
    });
  }

  function refreshAll(delay) {
    document.querySelectorAll('[data-next-module-button]').forEach(function (button) {
      scheduleRefresh(button, delay);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-next-module-button]').forEach(function (button) {
      var pending = null;

      function warm() {
        if (pending) return pending;
        pending = resolveNext(button).finally(function () {
          pending = null;
        });
        return pending;
      }

      button.moduLearnRefreshNextModule = warm;
      button.addEventListener('mouseenter', warm);
      button.addEventListener('focus', warm);
      button.addEventListener('click', function (event) {
        event.preventDefault();
        warm().then(function (data) {
          if (data && data.available && data.url) {
            window.location.href = data.url;
          }
        });
      });

      scheduleRefresh(button, 250);
    });

    document.addEventListener(REFRESH_EVENT, function () {
      refreshAll(80);
    });
    document.addEventListener(PROGRESS_EVENT, function () {
      refreshAll(80);
    });
    window.addEventListener('message', function (event) {
      var message = event.data;
      if (typeof message === 'string') {
        try {
          message = JSON.parse(message);
        } catch (error) {
          return;
        }
      }
      if (
        message &&
        (
          message.subject === 'ModuLearn.activityProgressMaybeUpdated' ||
          message.subject === 'SPLICE.reportScoreAndState'
        )
      ) {
        refreshAll(120);
      }
    });
    window.addEventListener('focus', function () {
      refreshAll(150);
    });
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) {
        refreshAll(150);
      }
    });
  });
})();
