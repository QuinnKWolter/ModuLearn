(function () {
  function setButtonState(button, state) {
    var label = button.querySelector('[data-next-label]');
    var icon = button.querySelector('[data-next-icon]');
    var text = button.dataset.readyLabel || 'Next Module';

    button.classList.remove('btn-primary', 'btn-outline-secondary', 'opacity-75');
    if (state === 'checking') {
      text = button.dataset.checkingLabel || 'Checking...';
      button.classList.add('btn-outline-secondary');
      if (icon) icon.className = 'bi bi-arrow-repeat';
    } else if (state === 'empty') {
      text = button.dataset.emptyLabel || 'No Unlocked Module';
      button.classList.add('btn-outline-secondary', 'opacity-75');
      if (icon) icon.className = 'bi bi-lock';
    } else if (state === 'error') {
      text = button.dataset.errorLabel || 'Try Again';
      button.classList.add('btn-outline-secondary');
      if (icon) icon.className = 'bi bi-exclamation-circle';
    } else {
      button.classList.add('btn-primary');
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
          button.title = data.title ? 'Open ' + data.title : 'Open the next module';
          setButtonState(button, 'ready');
          return data;
        }
        button.removeAttribute('data-resolved-url');
        button.href = '#';
        button.title = (data && data.message) || 'No visible unlocked module is available yet';
        setButtonState(button, 'empty');
        return data || null;
      })
      .catch(function () {
        button.href = '#';
        button.removeAttribute('data-resolved');
        button.title = 'Could not check the next module. Try again.';
        setButtonState(button, 'error');
        return null;
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
    });
  });
})();
