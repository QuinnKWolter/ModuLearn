(function () {
  var password = document.getElementById('id_password1');
  var confirmation = document.getElementById('id_password2');
  var validation = document.querySelector('[data-password-validation]');

  if (!password || !confirmation || !validation) {
    return;
  }

  var fields = {
    username: document.getElementById('id_username'),
    email: document.getElementById('id_email'),
    fullName: document.getElementById('id_full_name')
  };

  function normalize(value) {
    return (value || '').trim().toLowerCase();
  }

  function profileTokens() {
    return [
      fields.username && fields.username.value,
      fields.email && fields.email.value && fields.email.value.split('@')[0],
      fields.fullName && fields.fullName.value
    ]
      .join(' ')
      .split(/\s+/)
      .map(normalize)
      .filter(function (token) {
        return token.length >= 3;
      });
  }

  function setRule(name, state) {
    var rule = validation.querySelector('[data-password-rule="' + name + '"]');
    if (rule) {
      rule.dataset.state = state;
    }
  }

  function setFieldState(field, state) {
    field.classList.remove('is-valid', 'is-invalid');

    if (state === 'valid') {
      field.classList.add('is-valid');
    } else if (state === 'invalid') {
      field.classList.add('is-invalid');
    }
  }

  function updatePasswordChecks() {
    var value = password.value || '';
    var confirmationValue = confirmation.value || '';
    var hasPassword = value.length > 0;
    var hasConfirmation = confirmationValue.length > 0;
    var loweredPassword = normalize(value);
    var tokens = profileTokens();
    var states = {
      length: hasPassword ? value.length >= 8 : null,
      numeric: hasPassword ? !/^\d+$/.test(value) : null,
      personal: hasPassword ? !tokens.some(function (token) { return loweredPassword.indexOf(token) !== -1; }) : null,
      match: hasConfirmation ? hasPassword && value === confirmationValue : null
    };

    Object.keys(states).forEach(function (name) {
      setRule(name, states[name] === null ? 'idle' : states[name] ? 'valid' : 'invalid');
    });

    setFieldState(password, hasPassword ? (states.length && states.numeric && states.personal ? 'valid' : 'invalid') : 'idle');
    setFieldState(confirmation, hasConfirmation ? (states.match ? 'valid' : 'invalid') : 'idle');
  }

  [password, confirmation, fields.username, fields.email, fields.fullName].forEach(function (field) {
    if (field) {
      field.addEventListener('input', updatePasswordChecks);
    }
  });

  updatePasswordChecks();
})();
