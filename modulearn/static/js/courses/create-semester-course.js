(function () {
  function isUsableCsrfToken(token) {
    var normalized = token ? String(token).trim() : '';
    return Boolean(normalized && normalized !== 'NOTPROVIDED' && normalized !== 'csrf_token');
  }

  function getCookieCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function getFormCsrfToken() {
    var tokenInput = document.querySelector('#createRawSessionForm input[name="csrfmiddlewaretoken"]');
    return tokenInput ? tokenInput.value : '';
  }

  function getCsrfToken(config) {
    var formToken = getFormCsrfToken();
    if (isUsableCsrfToken(formToken)) {
      return formToken;
    }

    var cookieToken = getCookieCsrfToken();
    if (isUsableCsrfToken(cookieToken)) {
      return cookieToken;
    }

    if (config && isUsableCsrfToken(config.csrfToken)) {
      return config.csrfToken;
    }

    return '';
  }

  function showError(message) {
    var loadingState = document.getElementById('loadingState');
    var manualState = document.getElementById('manualState');
    var errorState = document.getElementById('errorState');
    var errorMessage = document.getElementById('errorMessage');

    if (loadingState) loadingState.classList.add('hidden');
    if (manualState) manualState.classList.add('hidden');
    if (errorState) errorState.classList.remove('hidden');
    if (errorMessage) {
      errorMessage.textContent = message || 'An unexpected error occurred while creating your course.';
    }
  }

  function hideManualError() {
    var manualError = document.getElementById('manualError');
    if (!manualError) return;
    manualError.textContent = '';
    manualError.classList.add('hidden');
  }

  function showManualError(message) {
    var manualError = document.getElementById('manualError');
    if (!manualError) return;
    manualError.textContent = message || 'Unable to create custom session.';
    manualError.classList.remove('hidden');
  }

  async function createCourseFromExport(config) {
    try {
      var exportResponse = await fetch(config.courseExportUrl, {
        method: 'GET',
        credentials: 'include',
      });

      if (!exportResponse.ok) {
        throw new Error('Failed to fetch course details: ' + exportResponse.statusText);
      }

      var courseData = await exportResponse.json();
      var backendResponse = await fetch(config.createCourseUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ course_data: courseData }),
      });

      if (!backendResponse.ok) {
        throw new Error('Failed to send course data to ModuLearn: ' + backendResponse.statusText);
      }

      var result = await backendResponse.json();
      if (!result.success) {
        throw new Error(result.error || 'Unknown error occurred while creating the course.');
      }

      window.location.href = config.redirectUrl;
    } catch (error) {
      console.error('Error during course import:', error);
      showError(error.message || 'An unexpected error occurred while importing your course.');
    }
  }

  async function createRawSession(config, payload) {
    var response = await fetch(config.createRawSessionUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(config),
      },
      body: JSON.stringify(payload),
      credentials: 'same-origin',
    });

    var responseBody = await response.text();
    var result = {};
    if (responseBody) {
      try {
        result = JSON.parse(responseBody);
      } catch (error) {
        result = {};
      }
    }

    if (!response.ok || !result.success) {
      var message = result.error || result.message || '';
      if (!message && /csrf/i.test(responseBody || '')) {
        message = 'Security check failed. Refresh this page and try again.';
      }
      throw new Error(message || 'Custom session creation failed.');
    }
    window.location.href = result.redirect_url || config.redirectUrl;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var config = window.createSemesterCourseConfig;
    if (!config) {
      return;
    }

    var manualState = document.getElementById('manualState');
    var loadingState = document.getElementById('loadingState');
    var form = document.getElementById('createRawSessionForm');
    var createButton = document.getElementById('createRawSessionButton');

    if (config.courseExportUrl) {
      if (manualState) manualState.classList.add('hidden');
      if (loadingState) loadingState.classList.remove('hidden');
      createCourseFromExport(config);
    } else {
      if (loadingState) loadingState.classList.add('hidden');
      if (manualState) manualState.classList.remove('hidden');
    }

    if (form) {
      form.addEventListener('submit', async function (event) {
        event.preventDefault();
        if (!createButton) return;

        var titleInput = document.getElementById('rawCourseTitle');
        var sessionInput = document.getElementById('rawSessionName');
        var descriptionInput = document.getElementById('rawCourseDescription');

        var payload = {
          course_title: titleInput ? titleInput.value : '',
          group_name: sessionInput ? sessionInput.value : '',
          course_description: descriptionInput ? descriptionInput.value : '',
        };

        hideManualError();
        createButton.disabled = true;
        createButton.innerHTML = '<span class="spinner-border spinner-border-sm mr-2" aria-hidden="true"></span>Creating...';

        try {
          await createRawSession(config, payload);
        } catch (error) {
          console.error('Error creating custom session:', error);
          showManualError(error.message || 'Unable to create custom session.');
        } finally {
          createButton.disabled = false;
          createButton.innerHTML = '<i class="bi bi-plus-circle mr-2"></i>Create Custom Session';
        }
      });
    }
  });
})();
