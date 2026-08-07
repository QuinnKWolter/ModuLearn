(function () {
  function t(value) {
    return window.ModuLearnI18n && typeof window.ModuLearnI18n.t === 'function'
      ? window.ModuLearnI18n.t(value)
      : value;
  }

  function debounce(fn, wait) {
    let timeoutId = null;
    return function debounced(...args) {
      window.clearTimeout(timeoutId);
      timeoutId = window.setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function replacePattern(pattern, placeholder, value) {
    return (pattern || '').replace(placeholder, encodeURIComponent(String(value)));
  }

  function replaceNumericPathSegment(pattern, segmentValue, replacementValue) {
    return (pattern || '').replace(
      `/${encodeURIComponent(String(segmentValue))}/`,
      `/${encodeURIComponent(String(replacementValue))}/`
    );
  }

  function parseJsonResponse(response) {
    return response.json().catch(() => ({}));
  }

  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  document.addEventListener('DOMContentLoaded', function () {
    const app = document.getElementById('instructorDashboardApp');
    if (!app) return;

    const config = {
      csrfToken: app.dataset.csrfToken || '',
      courseDetailsPattern: app.dataset.courseDetailsPattern || '',
      courseDeletePattern: app.dataset.courseDeletePattern || '',
      courseInstanceDeletePattern: app.dataset.courseInstanceDeletePattern || '',
      getEnrollmentsPattern: app.dataset.getEnrollmentsPattern || '',
      removeEnrollmentPattern: app.dataset.removeEnrollmentPattern || '',
      bulkEnrollPattern: app.dataset.bulkEnrollPattern || '',
      generateAnonymousStudentsPattern: app.dataset.generateAnonymousStudentsPattern || '',
      createCourseInstancePattern: app.dataset.createCourseInstancePattern || '',
      checkGroupNameUrl: app.dataset.checkGroupNameUrl || '',
      createCourseUrl: app.dataset.createCourseUrl || '',
      generateCourseAuthUrl: app.dataset.generateCourseAuthUrl || '',
      resetCourseAuthoringPasswordUrl: app.dataset.resetCourseAuthoringPasswordUrl || '',
      proxyCourseAuthoringXLoginUrl: app.dataset.proxyCourseAuthoringXLoginUrl || '',
      resourceApiPattern: app.dataset.resourceApiPattern || '',
      legacyGroupsUrl: app.dataset.legacyGroupsUrl || '',
      legacyDashboardBaseUrl: app.dataset.legacyDashboardBaseUrl || '',
      ltiLaunchPath: app.dataset.ltiLaunchPath || '',
      ltiSetupDetailsUrl: app.dataset.ltiSetupDetailsUrl || '',
      ltiPlatformRegistrationUrl: app.dataset.ltiPlatformRegistrationUrl || '',
      courseAuthoringXLoginUrl: app.dataset.courseAuthoringXLoginUrl || '',
      courseAuthoringAppUrl: app.dataset.courseAuthoringAppUrl || '',
    };

    const resourcesClient = window.ModuLearnCourseResources
      ? window.ModuLearnCourseResources.init({ resourceApiPattern: config.resourceApiPattern })
      : null;

    if (resourcesClient) {
      resourcesClient.bindTriggers(app);
    }

    const sessionActivityState = {
      events: [],
      filtered: [],
      sortKey: 'created_at',
      sortDirection: 'desc',
      title: 'Recent Activity',
    };

    function activityEventLabel(value) {
      const normalized = String(value || '').replace(/_/g, ' ').trim();
      if (!normalized) return t('Activity');
      return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function activityEventClass(value) {
      return `is-${String(value || 'activity').replace(/_/g, '-').toLowerCase()}`;
    }

    function formatActivityDate(value) {
      if (!value) return '';
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleString([], {
        month: 'short',
        day: '2-digit',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
      });
    }

    function activitySuccessLabel(event) {
      if (event.success === true) return t('Yes');
      if (['completion', 'outcome', 'progress'].includes(event.event_type)) return t('No');
      return '-';
    }

    function activitySortValue(event, key) {
      switch (key) {
        case 'created_at':
          return Date.parse(event.created_at || '') || 0;
        case 'learner':
          return `${event.learner_name || ''} ${event.learner_username || ''} ${event.learner_email || ''}`.toLowerCase();
        case 'module':
          return String(event.module_title || '').toLowerCase();
        case 'event_type':
          return String(event.event_type || '').toLowerCase();
        case 'progress':
          return Number(event.progress_percent || 0);
        case 'score':
          return Number(event.score ?? -1);
        case 'source':
          return String(event.source || '').toLowerCase();
        case 'success':
          return event.success === true ? 1 : 0;
        default:
          return '';
      }
    }

    function compareActivityValues(a, b, direction) {
      if (typeof a === 'number' && typeof b === 'number') {
        return direction === 'asc' ? a - b : b - a;
      }
      const result = String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
      return direction === 'asc' ? result : -result;
    }

    function renderSessionActivityTable() {
      const tbody = document.getElementById('sessionActivityTableBody');
      const meta = document.getElementById('sessionActivityModalMeta');
      const search = (document.getElementById('sessionActivitySearch')?.value || '').trim().toLowerCase();
      const type = document.getElementById('sessionActivityTypeFilter')?.value || '';
      if (!tbody) return;

      const filtered = sessionActivityState.events
        .filter((event) => !type || event.event_type === type)
        .filter((event) => {
          if (!search) return true;
          const haystack = [
            event.learner_name,
            event.learner_username,
            event.learner_email,
            event.module_title,
            event.event_type,
            event.source,
            event.score,
            event.progress_percent,
          ].join(' ').toLowerCase();
          return haystack.includes(search);
        })
        .sort((left, right) => compareActivityValues(
          activitySortValue(left, sessionActivityState.sortKey),
          activitySortValue(right, sessionActivityState.sortKey),
          sessionActivityState.sortDirection
        ));

      sessionActivityState.filtered = filtered;
      if (meta) {
        meta.textContent = `${filtered.length} of ${sessionActivityState.events.length} events - reverse chronological by default.`;
      }

      if (!filtered.length) {
        tbody.innerHTML = `
          <tr>
            <td colspan="8" class="text-center text-slate-500 py-5">${escapeHtml(t('No activity matches the current filters.'))}</td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = filtered.map((event) => {
        const learnerLabel = event.learner_name || event.learner_username || t('Unknown learner');
        const learnerSub = [event.learner_username ? `@${event.learner_username}` : '', event.learner_email || ''].filter(Boolean).join(' - ');
        const score = event.score === null || event.score === undefined ? '-' : `${Number(event.score).toFixed(0)}%`;
        const progress = `${Number(event.progress_percent || 0).toFixed(0)}%`;
        return `
          <tr>
            <td class="whitespace-nowrap">${escapeHtml(formatActivityDate(event.created_at))}</td>
            <td>
              <div class="font-semibold text-slate-900 dark:text-white">${escapeHtml(learnerLabel)}</div>
              <div class="text-xs text-slate-500 dark:text-slate-300">${escapeHtml(learnerSub)}</div>
            </td>
            <td class="max-w-xs">
              <div class="truncate font-semibold" title="${escapeHtml(event.module_title || '')}">${escapeHtml(event.module_title || t('Module activity'))}</div>
            </td>
            <td><span class="activity-event-pill ${activityEventClass(event.event_type)}">${escapeHtml(activityEventLabel(event.event_type))}</span></td>
            <td class="text-right font-semibold">${escapeHtml(progress)}</td>
            <td class="text-right">${escapeHtml(score)}</td>
            <td>${escapeHtml(event.source || '-')}</td>
            <td>${escapeHtml(activitySuccessLabel(event))}</td>
          </tr>
        `;
      }).join('');
    }

    function populateSessionActivityTypeFilter(events) {
      const select = document.getElementById('sessionActivityTypeFilter');
      if (!select) return;
      const types = Array.from(new Set((events || []).map((event) => event.event_type).filter(Boolean))).sort();
      select.innerHTML = `<option value="">${escapeHtml(t('All events'))}</option>` + types
        .map((type) => `<option value="${escapeHtml(type)}">${escapeHtml(activityEventLabel(type))}</option>`)
        .join('');
    }

    function openSessionActivity(button) {
      if (!button) return;
      const scriptId = button.dataset.sessionActivityScript;
      const script = scriptId ? document.getElementById(scriptId) : null;
      let events = [];
      try {
        events = script ? JSON.parse(script.textContent || '[]') : [];
      } catch (error) {
        console.error('Failed to parse session activity data:', error);
        events = [];
      }
      sessionActivityState.events = events;
      sessionActivityState.sortKey = 'created_at';
      sessionActivityState.sortDirection = 'desc';
      sessionActivityState.title = button.dataset.sessionTitle || t('Recent Activity');
      const title = document.getElementById('sessionActivityModalTitle');
      const search = document.getElementById('sessionActivitySearch');
      if (title) title.textContent = sessionActivityState.title;
      if (search) search.value = '';
      populateSessionActivityTypeFilter(events);
      renderSessionActivityTable();
    }

    function csvEscape(value) {
      const text = value === null || value === undefined ? '' : String(value);
      return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    }

    function downloadSessionActivityCsv() {
      const rows = sessionActivityState.filtered || [];
      const header = ['time', 'student_name', 'username', 'email', 'module', 'event_type', 'progress_percent', 'score', 'source', 'success'];
      const csvRows = rows.map((event) => [
        formatActivityDate(event.created_at),
        event.learner_name || '',
        event.learner_username || '',
        event.learner_email || '',
        event.module_title || '',
        event.event_type || '',
        event.progress_percent ?? '',
        event.score ?? '',
        event.source || '',
        activitySuccessLabel(event),
      ]);
      const csv = [header, ...csvRows].map((row) => row.map(csvEscape).join(',')).join('\n');
      const slug = sessionActivityState.title.toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 80) || 'session-activity';
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${slug}-activity.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }

    function initializeSessionActionRows() {
      document.querySelectorAll('.session-action-row').forEach((row) => {
        const buttons = Array.from(row.querySelectorAll('.session-action-btn'));
        if (!buttons.length) return;

        let resetTimer = null;

        const clearReset = () => {
          if (resetTimer) {
            window.clearTimeout(resetTimer);
            resetTimer = null;
          }
        };

        const expandButton = (button) => {
          clearReset();
          row.classList.add('is-interacting');
          buttons.forEach((item) => item.classList.toggle('is-action-expanded', item === button));
        };

        const scheduleIdleState = () => {
          clearReset();
          resetTimer = window.setTimeout(() => {
            if (row.matches(':hover') || row.contains(document.activeElement)) return;
            row.classList.remove('is-interacting');
            buttons.forEach((item) => item.classList.remove('is-action-expanded'));
          }, 180);
        };

        row.addEventListener('pointerenter', clearReset);
        row.addEventListener('pointerleave', scheduleIdleState);

        buttons.forEach((button) => {
          button.addEventListener('pointerenter', () => expandButton(button));
          button.addEventListener('focusin', () => expandButton(button));
          button.addEventListener('focusout', scheduleIdleState);
        });
      });
    }

    app.addEventListener('click', async function handleDashboardCopy(event) {
      const button = event.target.closest('[data-copy-from]');
      if (!button) return;
      const target = app.querySelector(`[data-copy-target="${button.dataset.copyFrom}"]`);
      if (!target) return;
      const originalText = button.textContent;
      try {
        await navigator.clipboard.writeText(target.value || target.textContent || '');
        button.textContent = t('Copied');
        window.setTimeout(() => {
          button.textContent = originalText;
        }, 1200);
      } catch (error) {
        target.focus();
        if (target.select) target.select();
      }
    });

    function csrfHeaders(extraHeaders) {
      return Object.assign({ 'X-CSRFToken': config.csrfToken }, extraHeaders || {});
    }

    function buildLegacyDashboardUrl(group) {
      const baseUrl = config.legacyDashboardBaseUrl || '/dashboard/legacy/';
      if (!group || !group.groupLogin) {
        return baseUrl;
      }

      const params = new URLSearchParams({ grp: group.groupLogin });
      if (group.courseIds && group.courseIds.length) {
        params.set('cid', group.courseIds[0]);
      }
      return `${baseUrl}?${params.toString()}`;
    }

    function createNewSession(courseId) {
      document.getElementById('courseId').value = courseId;
      document.getElementById('groupName').value = '';
      document.getElementById('groupName').classList.remove('is-valid', 'is-invalid');
      document.getElementById('groupNameFeedback').textContent = '';
      document.getElementById('newSessionForm').dataset.courseId = courseId;
      bootstrap.Modal.getOrCreateInstance(document.getElementById('newSessionModal')).show();
    }

    function setInputValue(id, value) {
      const input = document.getElementById(id);
      if (input) input.value = value || '';
    }

    function setLtiValue(name, value) {
      document.querySelectorAll(`[data-lti-value="${name}"]`).forEach((input) => {
        input.value = value || '';
      });
    }

    function setText(id, value) {
      const element = document.getElementById(id);
      if (element) element.textContent = value || '';
    }

    async function copyInputValue(inputId, button) {
      const input = document.getElementById(inputId);
      if (!input) return;
      const originalText = button ? button.textContent : '';
      const originalLabel = button ? button.getAttribute('aria-label') : '';
      const originalTitle = button ? button.getAttribute('title') : '';
      const isIconButton = button && button.classList.contains('lti-copy-icon');
      try {
        await navigator.clipboard.writeText(input.value || '');
        if (button) {
          if (isIconButton) {
            button.classList.add('is-copied');
            button.setAttribute('aria-label', t('Copied'));
            button.setAttribute('title', t('Copied'));
          } else {
            button.textContent = t('Copied');
          }
          window.setTimeout(() => {
            if (isIconButton) {
              button.classList.remove('is-copied');
              if (originalLabel) button.setAttribute('aria-label', originalLabel);
              if (originalTitle) button.setAttribute('title', originalTitle);
            } else {
              button.textContent = originalText;
            }
          }, 1200);
        }
      } catch (error) {
        input.focus();
        input.select();
      }
    }

    function normalizeIssuerBase(value) {
      const trimmed = String(value || '').trim().replace(/\/+$/, '');
      if (!trimmed) return '';
      if (!/^https?:\/\//i.test(trimmed)) return '';
      try {
        const parsed = new URL(trimmed);
        return `${parsed.origin}${parsed.pathname.replace(/\/+$/, '')}`;
      } catch (error) {
        return trimmed;
      }
    }

    function fillLtiEndpointDefaults(form, forcedPlatform) {
      if (!form) return;
      const platform = forcedPlatform || (form.elements.platform ? form.elements.platform.value : '');
      if (forcedPlatform && form.elements.platform) {
        form.elements.platform.value = forcedPlatform;
        syncLtiPlatformHelp(form);
      }
      const issuerBase = normalizeIssuerBase(form.elements.issuer ? form.elements.issuer.value : '');
      const status = document.getElementById('ltiPlatformRegistrationStatus');
      if (!issuerBase || !['moodle', 'canvas'].includes(platform)) {
        if (status && forcedPlatform) {
          status.textContent = t('Enter the Platform ID / Issuer first, then fill endpoint defaults.');
        }
        return;
      }

      const defaults = platform === 'canvas'
        ? {
          auth_login_url: `${issuerBase}/api/lti/authorize_redirect`,
          auth_token_url: `${issuerBase}/login/oauth2/token`,
          key_set_url: `${issuerBase}/api/lti/security/jwks`,
          auth_audience: `${issuerBase}/login/oauth2/token`,
        }
        : {
          auth_login_url: `${issuerBase}/mod/lti/auth.php`,
          auth_token_url: `${issuerBase}/mod/lti/token.php`,
          key_set_url: `${issuerBase}/mod/lti/certs.php`,
          auth_audience: `${issuerBase}/mod/lti/token.php`,
        };

      Object.entries(defaults).forEach(([name, value]) => {
        const input = form.elements[name];
        if (!input) return;
        const previousBase = input.dataset.ltiDefaultBase || '';
        const pathMarker = platform === 'canvas' ? '/' : '/mod/lti/';
        const isPreviousDefault = previousBase && input.value.startsWith(`${previousBase}${pathMarker}`);
        if (!input.value || input.dataset.ltiAutofilled === 'true' || isPreviousDefault) {
          input.value = value;
          input.dataset.ltiAutofilled = 'true';
          input.dataset.ltiDefaultBase = issuerBase;
        }
      });

      if (status && forcedPlatform) {
        status.textContent = platform === 'canvas'
          ? t('Canvas endpoint defaults filled from the issuer URL.')
          : t('Moodle endpoint defaults filled from the issuer URL.');
      }
    }

    function fillMoodleEndpointDefaults(form) {
      fillLtiEndpointDefaults(form);
    }

    function syncLtiPlatformHelp(form) {
      if (!form) return;
      const platform = form.elements.platform ? form.elements.platform.value : 'moodle';
      document.querySelectorAll('[data-lti-platform-help]').forEach((panel) => {
        panel.classList.toggle('hidden', panel.dataset.ltiPlatformHelp !== platform);
      });
    }

    function resetLtiEndpointAutofillState(form) {
      if (!form) return;
      ['auth_login_url', 'auth_token_url', 'key_set_url', 'auth_audience'].forEach((name) => {
        const input = form.elements[name];
        if (!input) return;
        delete input.dataset.ltiAutofilled;
        delete input.dataset.ltiDefaultBase;
      });
    }

    async function openLtiSetup(button) {
      const modalElement = document.getElementById('ltiSetupModal');
      if (!modalElement) return;
      const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
      const loading = document.getElementById('ltiSetupLoading');
      const content = document.getElementById('ltiSetupContent');
      const status = document.getElementById('ltiPlatformRegistrationStatus');
      const form = document.getElementById('ltiPlatformRegistrationForm');
      const courseInstanceId = button.dataset.courseInstanceId || '';

      setText(
        'ltiSetupSubtitle',
        `${button.dataset.courseTitle || t('Course Session')} - ${button.dataset.groupName || ''}`
      );
      if (loading) loading.classList.remove('hidden');
      if (content) content.classList.add('hidden');
      if (status) status.textContent = '';
      if (form) {
        form.reset();
        resetLtiEndpointAutofillState(form);
      }
      modal.show();

      try {
        const url = new URL(config.ltiSetupDetailsUrl, window.location.origin);
        url.searchParams.set('course_id', courseInstanceId);
        const response = await fetch(url.toString(), { headers: { 'Accept': 'application/json' } });
        const data = await parseJsonResponse(response);
        if (!response.ok || !data.success) {
          throw new Error(data.error || t('Unable to load LTI setup details.'));
        }

        const setup = data.setup || {};
        const tool = setup.tool || {};
        const lti11 = setup.lti_11 || {};
        const lti13 = setup.lti_13 || {};
        setInputValue('lti11LaunchUrl', lti11.launch_url);
        setInputValue('lti11ConfigUrl', lti11.cartridge_xml_url);
        setInputValue('lti11ConsumerKey', lti11.consumer_key);
        setInputValue('lti11SharedSecret', lti11.shared_secret);
        setInputValue('lti13ToolUrl', lti13.tool_url || lti13.target_link_uri);
        setInputValue('lti13LoginUrl', lti13.initiate_login_url || lti13.oidc_login_url);
        setInputValue('lti13RedirectUri', lti13.redirect_uri);
        setInputValue('lti13JwksUrl', lti13.jwks_url || lti13.public_keyset_url);
        setLtiValue('tool.name', tool.name);
        setLtiValue('tool.description', tool.description);
        setLtiValue('tool.default_launch_container', tool.default_launch_container);
        setLtiValue('lti_11.launch_url', lti11.launch_url);
        setLtiValue('lti_11.cartridge_xml_url', lti11.cartridge_xml_url);
        setLtiValue('lti_11.consumer_key', lti11.consumer_key);
        setLtiValue('lti_11.shared_secret', lti11.shared_secret);
        setLtiValue('lti_11.custom_parameters', lti11.custom_parameters);
        setLtiValue('lti_13.tool_url', lti13.tool_url || lti13.target_link_uri);
        setLtiValue('lti_13.login_url', lti13.initiate_login_url || lti13.oidc_login_url);
        setLtiValue('lti_13.redirect_uri', lti13.redirect_uri);
        setLtiValue('lti_13.jwks_url', lti13.jwks_url || lti13.public_keyset_url);
        setLtiValue('lti_13.custom_parameters', lti13.custom_parameters);
      } catch (error) {
        console.error('Failed to load LTI setup:', error);
        setText('ltiSetupSubtitle', error.message || t('Unable to load LTI setup details.'));
      } finally {
        if (loading) loading.classList.add('hidden');
        if (content) content.classList.remove('hidden');
      }
    }

    async function saveLtiPlatformRegistration(form) {
      const status = document.getElementById('ltiPlatformRegistrationStatus');
      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());
      if (status) status.textContent = t('Saving...');

      try {
        const response = await fetch(config.ltiPlatformRegistrationUrl, {
          method: 'POST',
          headers: csrfHeaders({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          }),
          body: JSON.stringify(payload),
        });
        const data = await parseJsonResponse(response);
        if (!response.ok || !data.success) {
          throw new Error(data.error || t('Failed to save platform registration.'));
        }
        if (status) status.textContent = data.created
          ? t('Platform registration saved.')
          : t('Platform registration updated.');
      } catch (error) {
        console.error('Failed to save LTI platform registration:', error);
        if (status) status.textContent = error.message || t('Failed to save platform registration.');
      }
    }

    async function showDeleteCourseConfirmation(courseId) {
      const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteCourseModal'));
      const confirmButton = document.getElementById('confirmDeleteButton');
      const instancesList = document.getElementById('instancesListGroup');
      const noInstancesMessage = document.getElementById('noInstancesMessage');
      const courseInstancesList = document.getElementById('courseInstancesList');

      modal.show();
      document.getElementById('courseToDelete').textContent = t('Loading...');
      confirmButton.disabled = true;
      instancesList.innerHTML = '';
      noInstancesMessage.classList.add('hidden');
      courseInstancesList.classList.remove('hidden');

      try {
        const response = await fetch(replacePattern(config.courseDetailsPattern, '__COURSE_ID__', courseId));
        const data = await parseJsonResponse(response);
        if (!response.ok || data.error) {
          throw new Error(data.error || `${t('Failed to load course details')} (${response.status})`);
        }

        document.getElementById('courseToDelete').textContent = data.course.title;
        if (data.instances && data.instances.length) {
          data.instances.forEach((instance) => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = `${instance.group_name} (${t('Enrolled')}: ${instance.enrollment_count})`;
            instancesList.appendChild(li);
          });
          courseInstancesList.classList.remove('hidden');
          noInstancesMessage.classList.add('hidden');
        } else {
          courseInstancesList.classList.add('hidden');
          noInstancesMessage.classList.remove('hidden');
          noInstancesMessage.innerHTML = `<p class="text-sm text-gray-500 dark:text-gray-400">${t('This course has no active sessions.')}</p>`;
        }

        confirmButton.disabled = false;
        confirmButton.onclick = () => deleteCourse(courseId);
      } catch (error) {
        console.error('Error fetching course details:', error);
        document.getElementById('courseToDelete').textContent = t('Error loading course details');
        courseInstancesList.classList.add('hidden');
        noInstancesMessage.classList.remove('hidden');
        noInstancesMessage.innerHTML = `<div class="alert alert-danger">${t('Error:')} ${error.message || t('Failed to load course details')}</div>`;
      }
    }

    async function deleteCourse(courseId) {
      const confirmButton = document.getElementById('confirmDeleteButton');
      confirmButton.disabled = true;
      confirmButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${t('Deleting...')}`;

      try {
        const response = await fetch(replacePattern(config.courseDeletePattern, '__COURSE_ID__', courseId), {
          method: 'POST',
          headers: csrfHeaders({ 'Content-Type': 'application/json' }),
        });
        const data = await parseJsonResponse(response);

        if (!response.ok || !data.success) {
          throw new Error(data.error || t('Failed to delete course'));
        }

        window.location.reload();
      } catch (error) {
        console.error('Error deleting course:', error);
        alert(`${t('Error:')} ${t(error.message || 'Failed to delete course')}`);
        confirmButton.disabled = false;
        confirmButton.innerHTML = `<i class="bi bi-trash mr-1"></i>${t('Delete Course')}`;
      }
    }

    function showDeleteSessionConfirmation(button) {
      const modalElement = document.getElementById('deleteSessionModal');
      if (!modalElement) return;
      const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
      const confirmButton = document.getElementById('confirmDeleteSessionButton');
      const confirmInput = document.getElementById('deleteSessionConfirmText');
      const sessionLabel = `${button.dataset.courseTitle || t('Course')} - ${button.dataset.groupName || t('Session')}`;
      const enrollmentCount = Number.parseInt(button.dataset.enrollmentCount || '0', 10) || 0;

      document.getElementById('sessionToDelete').textContent = sessionLabel;
      document.getElementById('sessionDeleteEnrollmentCount').textContent = String(enrollmentCount);
      if (confirmInput) {
        confirmInput.value = '';
        confirmInput.dataset.courseInstanceId = button.dataset.courseInstanceId || '';
      }
      if (confirmButton) {
        confirmButton.disabled = true;
        confirmButton.dataset.courseInstanceId = button.dataset.courseInstanceId || '';
        confirmButton.innerHTML = `<i class="bi bi-trash mr-1"></i>${t('Delete Session')}`;
      }
      modal.show();
      window.setTimeout(() => confirmInput?.focus(), 120);
    }

    async function deleteCourseSession(courseInstanceId) {
      const confirmButton = document.getElementById('confirmDeleteSessionButton');
      if (!courseInstanceId || !confirmButton) return;
      confirmButton.disabled = true;
      confirmButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${t('Deleting...')}`;

      try {
        const response = await fetch(
          replaceNumericPathSegment(config.courseInstanceDeletePattern, 0, courseInstanceId),
          {
            method: 'POST',
            headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          }
        );
        const data = await parseJsonResponse(response);

        if (!response.ok || !data.success) {
          throw new Error(data.error || t('Failed to delete course session'));
        }

        window.location.reload();
      } catch (error) {
        console.error('Error deleting course session:', error);
        alert(`${t('Error:')} ${t(error.message || 'Failed to delete course session')}`);
        confirmButton.disabled = false;
        confirmButton.innerHTML = `<i class="bi bi-trash mr-1"></i>${t('Delete Session')}`;
      }
    }

    function updateAnonymousCapacityHint(limits) {
      const countInput = document.getElementById('anonymousStudentCount');
      const hint = document.getElementById('anonymousCapacityHint');
      const form = document.getElementById('anonymousEnrollmentForm');
      const submitButton = form ? form.querySelector('button[type="submit"]') : null;
      const maxStudents = Number.parseInt(limits && limits.max_students, 10) || 500;
      const remaining = Math.max(0, Number.parseInt(limits && limits.remaining_students, 10) || 0);
      if (countInput) {
        countInput.max = String(Math.max(1, remaining));
        if (Number.parseInt(countInput.value, 10) > remaining && remaining > 0) {
          countInput.value = String(remaining);
        }
        countInput.disabled = remaining <= 0;
      }
      if (submitButton) {
        submitButton.disabled = remaining <= 0;
      }
      if (hint) {
        hint.textContent = remaining > 0
          ? t(`This session has ${remaining} of ${maxStudents} student slots remaining.`)
          : t(`This session is at its ${maxStudents}-student limit.`);
      }
    }

    async function loadEnrollments(courseInstanceId) {
      const tableBody = document.getElementById('enrollmentTableBody');
      if (!tableBody) return;

      tableBody.innerHTML = `
        <tr>
          <td colspan="5" class="text-center text-gray-400 py-4">
            <span class="spinner-border mr-2"></span>${t('Loading...')}
          </td>
        </tr>
      `;

      try {
        const response = await fetch(replacePattern(config.getEnrollmentsPattern, '__COURSE_INSTANCE_ID__', courseInstanceId));
        const data = await parseJsonResponse(response);

        if (!response.ok) {
          throw new Error(data.error || `${t('Failed to load enrollments')} (${response.status})`);
        }

        updateAnonymousCapacityHint(data.limits);
        tableBody.innerHTML = '';
        if (data.enrollments && data.enrollments.length) {
          data.enrollments.forEach((enrollment) => {
            const row = document.createElement('tr');
            const studentName = enrollment.student.full_name || enrollment.student.username || t('Student');
            const emailLabel = enrollment.student.email || t('No email on file');
            const emailClass = enrollment.student.email ? '' : 'text-slate-400 italic';
            row.innerHTML = `
              <td>
                <div class="font-semibold">${escapeHtml(studentName)}</div>
                <div class="text-xs text-slate-500 dark:text-slate-400">${escapeHtml(enrollment.student.username || '')}</div>
              </td>
              <td><span class="${emailClass}">${escapeHtml(emailLabel)}</span></td>
              <td>${enrollment.progress.modules_completed}/${enrollment.progress.total_modules}</td>
              <td class="text-right">${enrollment.progress.overall_score.toFixed(2)}%</td>
              <td class="text-right">
                <button class="btn btn-sm btn-outline-danger remove-enrollment" data-enrollment-id="${enrollment.id}">
                  <i class="bi bi-trash"></i>
                </button>
              </td>
            `;
            tableBody.appendChild(row);
          });
          attachRemoveListeners();
        } else {
          tableBody.innerHTML = `
            <tr>
              <td colspan="5" class="text-center text-gray-500 py-4">
                <em>${t('No students are currently enrolled in this course session.')}</em>
              </td>
            </tr>
          `;
        }
      } catch (error) {
        console.error('Error loading enrollments:', error);
        tableBody.innerHTML = `
          <tr>
            <td colspan="5" class="text-center text-red-500 py-4">
              <em>${t('Error loading enrollments. Please try again.')}</em>
            </td>
          </tr>
        `;
      }
    }

    function attachRemoveListeners() {
      document.querySelectorAll('.remove-enrollment').forEach((button) => {
        button.addEventListener('click', async function () {
          if (!window.confirm(t('Are you sure you want to remove this student?'))) {
            return;
          }

          try {
            const response = await fetch(
              replaceNumericPathSegment(config.removeEnrollmentPattern, 0, this.dataset.enrollmentId),
              { method: 'POST', headers: csrfHeaders() }
            );
            const data = await parseJsonResponse(response);
            if (!response.ok || !data.success) {
              throw new Error(data.error || t('Failed to remove enrollment'));
            }
            this.closest('tr').remove();
          } catch (error) {
            console.error('Error removing enrollment:', error);
            alert(t(error.message || 'An error occurred while removing the student.'));
          }
        });
      });
    }

    const checkGroupName = debounce(async function (groupName) {
      const groupNameInput = document.getElementById('groupName');
      const groupNameFeedback = document.getElementById('groupNameFeedback');
      const submitButton = document.querySelector('#newSessionForm button[type="submit"]');
      const courseId = document.getElementById('newSessionForm').dataset.courseId;

      if (!groupName.trim()) {
        groupNameInput.classList.remove('is-valid', 'is-invalid');
        groupNameFeedback.textContent = '';
        submitButton.disabled = true;
        return;
      }

      try {
        const response = await fetch(
          `${config.checkGroupNameUrl}?group_name=${encodeURIComponent(groupName)}&course_id=${encodeURIComponent(courseId)}`
        );
        const data = await parseJsonResponse(response);

        if (!response.ok) {
          throw new Error(data.error || `${t('Failed to validate session name')} (${response.status})`);
        }

        if (data.available) {
          groupNameInput.classList.remove('is-invalid');
          groupNameInput.classList.add('is-valid');
          groupNameFeedback.textContent = t('Session name is available');
          groupNameFeedback.className = 'valid-feedback text-sm';
          submitButton.disabled = false;
        } else {
          groupNameInput.classList.remove('is-valid');
          groupNameInput.classList.add('is-invalid');
          groupNameFeedback.textContent = data.error || t('This session name already exists for this course');
          groupNameFeedback.className = 'invalid-feedback text-sm';
          submitButton.disabled = true;
        }
      } catch (error) {
        console.error('Error checking session name:', error);
        groupNameInput.classList.remove('is-valid', 'is-invalid');
        groupNameFeedback.textContent = '';
        submitButton.disabled = false;
      }
    }, 300);

    const newSessionForm = document.getElementById('newSessionForm');
    if (newSessionForm) {
      newSessionForm.addEventListener('submit', async function (event) {
        event.preventDefault();
        const courseId = document.getElementById('courseId').value;
        const groupName = document.getElementById('groupName').value.trim();
        const submitButton = this.querySelector('button[type="submit"]');

        submitButton.disabled = true;
        submitButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${t('Creating...')}`;

        try {
          const response = await fetch(
            replacePattern(config.createCourseInstancePattern, '__COURSE_ID__', courseId),
            {
              method: 'POST',
              headers: csrfHeaders({ 'Content-Type': 'application/json' }),
              body: JSON.stringify({ group_name: groupName }),
            }
          );
          const data = await parseJsonResponse(response);
          if (!response.ok || !data.success) {
            throw new Error(data.error || t('Failed to create session'));
          }
          window.location.reload();
        } catch (error) {
          console.error('Error creating course session:', error);
          alert(t(error.message || 'An error occurred while creating the course session.'));
        } finally {
          submitButton.disabled = false;
          submitButton.innerHTML = t('Create Session');
        }
      });
    }

    const groupNameInput = document.getElementById('groupName');
    if (groupNameInput) {
      groupNameInput.addEventListener('input', (event) => checkGroupName(event.target.value.trim()));
    }

    const bulkEnrollmentForm = document.getElementById('bulkEnrollmentForm');
    if (bulkEnrollmentForm) {
      bulkEnrollmentForm.addEventListener('submit', async function (event) {
        event.preventDefault();
        const courseInstanceId = document.getElementById('currentCourseInstanceId').value;
        const emailList = document.getElementById('emailList');
        const emails = emailList.value.split(',').map((email) => email.trim()).filter(Boolean);

        if (!emails.length) {
          alert(t('Please enter at least one email address.'));
          return;
        }

        const submitButton = this.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${t('Adding...')}`;

        try {
          const response = await fetch(replacePattern(config.bulkEnrollPattern, '__COURSE_INSTANCE_ID__', courseInstanceId), {
            method: 'POST',
            headers: csrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ emails }),
          });
          const data = await parseJsonResponse(response);

          if (!response.ok || !data.success) {
            throw new Error(data.error || t('Failed to enroll students'));
          }

          emailList.value = '';
          await loadEnrollments(courseInstanceId);

          let message = t(`Successfully enrolled ${data.success_count} students.`);
          if (data.error_count > 0) {
            message += `\n\n${t('Errors:')}\n${data.error_details.join('\n')}`;
          }
          alert(message);
        } catch (error) {
          console.error('Error enrolling students:', error);
          alert(t(error.message || 'An error occurred while enrolling students.'));
        } finally {
          submitButton.disabled = false;
          submitButton.innerHTML = `<i class="bi bi-person-plus mr-1"></i>${t('Add Students')}`;
        }
      });
    }

    function formatGeneratedRoster(accounts) {
      const header = ['username', 'temporary_password'];
      const rows = (accounts || []).map((account) => [
        account.username || '',
        account.password || '',
      ]);
      return [header, ...rows]
        .map((row) => row.map((value) => String(value).replace(/\s+/g, ' ').trim()).join('\t'))
        .join('\n');
    }

    const anonymousEnrollmentForm = document.getElementById('anonymousEnrollmentForm');
    if (anonymousEnrollmentForm) {
      anonymousEnrollmentForm.addEventListener('submit', async function (event) {
        event.preventDefault();
        const courseInstanceId = document.getElementById('currentCourseInstanceId').value;
        const countInput = document.getElementById('anonymousStudentCount');
        const prefixInput = document.getElementById('anonymousUsernamePrefix');
        const passwordMatchesUsernameInput = document.getElementById('anonymousPasswordMatchesUsername');
        const rosterOutput = document.getElementById('anonymousRosterOutput');
        const rosterText = document.getElementById('anonymousRosterText');
        const count = Number.parseInt(countInput.value, 10);
        const maxCount = Number.parseInt(countInput.max, 10) || 500;

        if (!Number.isInteger(count) || count < 1 || count > maxCount) {
          alert(t(`Generate between 1 and ${maxCount} accounts at a time.`));
          return;
        }

        const submitButton = this.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${t('Generating...')}`;

        try {
          const response = await fetch(
            replacePattern(config.generateAnonymousStudentsPattern, '__COURSE_INSTANCE_ID__', courseInstanceId),
            {
              method: 'POST',
              headers: csrfHeaders({ 'Content-Type': 'application/json' }),
              body: JSON.stringify({
                count,
                prefix: prefixInput.value.trim() || 'anon',
                password_mode: passwordMatchesUsernameInput && passwordMatchesUsernameInput.checked ? 'username' : 'random',
              }),
            }
          );
          const data = await parseJsonResponse(response);

          if (!response.ok || !data.success) {
            throw new Error(data.error || t('Failed to generate anonymous accounts'));
          }

          if (rosterText) {
            rosterText.value = formatGeneratedRoster(data.accounts || []);
          }
          if (rosterOutput) {
            rosterOutput.classList.remove('hidden');
          }
          await loadEnrollments(courseInstanceId);
        } catch (error) {
          console.error('Error generating anonymous accounts:', error);
          alert(t(error.message || 'An error occurred while generating anonymous accounts.'));
        } finally {
          submitButton.disabled = Boolean(countInput && countInput.disabled);
          submitButton.innerHTML = `<i class="bi bi-person-badge mr-1"></i>${t('Generate Accounts')}`;
        }
      });
    }

    const copyAnonymousRosterButton = document.getElementById('copyAnonymousRosterButton');
    if (copyAnonymousRosterButton) {
      copyAnonymousRosterButton.addEventListener('click', async function () {
        const rosterText = document.getElementById('anonymousRosterText');
        if (!rosterText || !rosterText.value.trim()) return;
        const originalText = this.innerHTML;
        try {
          await navigator.clipboard.writeText(rosterText.value);
          this.innerHTML = `<i class="bi bi-check2 mr-1"></i>${t('Copied')}`;
          window.setTimeout(() => {
            this.innerHTML = originalText;
          }, 1400);
        } catch (_error) {
          rosterText.focus();
          rosterText.select();
          document.execCommand('copy');
        }
      });
    }

    const downloadAnonymousRosterButton = document.getElementById('downloadAnonymousRosterButton');
    if (downloadAnonymousRosterButton) {
      downloadAnonymousRosterButton.addEventListener('click', function () {
        const rosterText = document.getElementById('anonymousRosterText');
        if (!rosterText || !rosterText.value.trim()) return;
        const sessionName = (document.getElementById('manageEnrollmentModalLabel')?.textContent || 'anonymous-roster')
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/^-+|-+$/g, '')
          .slice(0, 80) || 'anonymous-roster';
        const blob = new Blob([rosterText.value], { type: 'text/tab-separated-values;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${sessionName}-logins.tsv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      });
    }

    const manageEnrollmentModal = document.getElementById('manageEnrollmentModal');
    if (manageEnrollmentModal) {
      manageEnrollmentModal.addEventListener('show.bs.modal', function (event) {
        const button = event.relatedTarget;
        document.getElementById('manageEnrollmentModalLabel').textContent =
          `${button.getAttribute('data-course-title')} - ${button.getAttribute('data-group-name')}`;
        document.getElementById('currentCourseInstanceId').value = button.getAttribute('data-course-instance-id');
        const rosterOutput = document.getElementById('anonymousRosterOutput');
        const rosterText = document.getElementById('anonymousRosterText');
        if (rosterOutput) rosterOutput.classList.add('hidden');
        if (rosterText) rosterText.value = '';
        const prefixInput = document.getElementById('anonymousUsernamePrefix');
        const passwordMatchesUsernameInput = document.getElementById('anonymousPasswordMatchesUsername');
        if (prefixInput) prefixInput.value = 'anon';
        if (passwordMatchesUsernameInput) passwordMatchesUsernameInput.checked = true;
        loadEnrollments(button.getAttribute('data-course-instance-id'));
      });
    }

    initializeSessionActionRows();

    document.querySelectorAll('.new-session-btn').forEach((button) => {
      button.addEventListener('click', function () {
        createNewSession(this.dataset.courseId);
      });
    });

    document.querySelectorAll('.delete-course-btn').forEach((button) => {
      button.addEventListener('click', function () {
        showDeleteCourseConfirmation(this.dataset.courseId);
      });
    });

    document.querySelectorAll('.delete-session-btn').forEach((button) => {
      button.addEventListener('click', function () {
        showDeleteSessionConfirmation(this);
      });
    });

    document.getElementById('deleteSessionConfirmText')?.addEventListener('input', function () {
      const confirmButton = document.getElementById('confirmDeleteSessionButton');
      if (confirmButton) {
        confirmButton.disabled = this.value.trim() !== 'DELETE SESSION';
      }
    });

    document.getElementById('confirmDeleteSessionButton')?.addEventListener('click', function () {
      const confirmInput = document.getElementById('deleteSessionConfirmText');
      if (confirmInput?.value.trim() !== 'DELETE SESSION') return;
      deleteCourseSession(this.dataset.courseInstanceId || confirmInput.dataset.courseInstanceId);
    });

    document.querySelectorAll('.copy-lti-url').forEach((button) => {
      button.addEventListener('click', function () {
        openLtiSetup(this);
      });
    });

    document.querySelectorAll('[data-session-activity-button]').forEach((button) => {
      button.addEventListener('click', function () {
        openSessionActivity(this);
      });
    });

    document.getElementById('sessionActivitySearch')?.addEventListener('input', debounce(renderSessionActivityTable, 120));
    document.getElementById('sessionActivityTypeFilter')?.addEventListener('change', renderSessionActivityTable);
    document.getElementById('downloadSessionActivityButton')?.addEventListener('click', downloadSessionActivityCsv);
    document.querySelectorAll('[data-activity-sort]').forEach((button) => {
      button.addEventListener('click', function () {
        const key = this.dataset.activitySort;
        if (sessionActivityState.sortKey === key) {
          sessionActivityState.sortDirection = sessionActivityState.sortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          sessionActivityState.sortKey = key;
          sessionActivityState.sortDirection = key === 'created_at' ? 'desc' : 'asc';
        }
        renderSessionActivityTable();
      });
    });

    document.querySelectorAll('.lti-copy-btn').forEach((button) => {
      button.addEventListener('click', function () {
        copyInputValue(this.dataset.copyInput, this);
      });
    });

    const ltiPlatformRegistrationForm = document.getElementById('ltiPlatformRegistrationForm');
    if (ltiPlatformRegistrationForm) {
      const issuerInput = ltiPlatformRegistrationForm.elements.issuer;
      const platformInput = ltiPlatformRegistrationForm.elements.platform;
      if (issuerInput) {
        issuerInput.addEventListener('input', debounce(() => {
          fillMoodleEndpointDefaults(ltiPlatformRegistrationForm);
        }, 250));
        issuerInput.addEventListener('blur', () => {
          fillMoodleEndpointDefaults(ltiPlatformRegistrationForm);
        });
      }
      if (platformInput) {
        platformInput.addEventListener('change', () => {
          syncLtiPlatformHelp(ltiPlatformRegistrationForm);
          fillLtiEndpointDefaults(ltiPlatformRegistrationForm);
        });
      }
      document.querySelectorAll('[data-lti-fill-defaults]').forEach((button) => {
        button.addEventListener('click', () => {
          fillLtiEndpointDefaults(ltiPlatformRegistrationForm, button.dataset.ltiFillDefaults);
        });
      });
      ['auth_login_url', 'auth_token_url', 'key_set_url', 'auth_audience'].forEach((name) => {
        const input = ltiPlatformRegistrationForm.elements[name];
        if (!input) return;
        input.addEventListener('input', () => {
          input.dataset.ltiAutofilled = 'false';
        });
      });
      syncLtiPlatformHelp(ltiPlatformRegistrationForm);
      ltiPlatformRegistrationForm.addEventListener('submit', function (event) {
        event.preventDefault();
        fillLtiEndpointDefaults(this);
        saveLtiPlatformRegistration(this);
      });
    }

    const legacySearchInput = document.getElementById('legacyGroupsSearch');
    const legacyClearBtn = document.getElementById('clearLegacySearch');
    const legacyEmptyMsg = document.getElementById('legacyGroupsEmpty');
    const legacyContainer = document.getElementById('legacyGroupsContainer');
    const legacyLoading = document.getElementById('legacyGroupsLoading');
    const legacyMeta = document.getElementById('legacyGroupsMeta');
    const legacyCount = document.getElementById('legacyGroupsCount');
    const legacySection = document.getElementById('legacyGroupsSection');

    function filterLegacyGroups() {
      if (!legacySearchInput || !legacyContainer) return;

      const searchTerm = legacySearchInput.value.toLowerCase().trim();
      const legacyCards = Array.from(legacyContainer.querySelectorAll('.legacy-group-card'));
      let visibleCount = 0;

      legacyCards.forEach((card) => {
        const groupName = card.dataset.groupName || '';
        const groupLogin = card.dataset.groupLogin || '';
        const matches = !searchTerm || groupName.includes(searchTerm) || groupLogin.includes(searchTerm);
        card.style.display = matches ? '' : 'none';
        if (matches) visibleCount += 1;
      });

      if (legacyEmptyMsg) {
        legacyEmptyMsg.classList.toggle('hidden', visibleCount !== 0);
      }
      legacyContainer.classList.toggle('hidden', visibleCount === 0);
      if (legacyClearBtn) {
        legacyClearBtn.classList.toggle('hidden', !searchTerm);
      }
    }

    function renderLegacyGroups(groups) {
      if (!legacyContainer) return;

      const normalizedGroups = Array.isArray(groups) ? groups.map((group) => ({
        groupName: group.group_name || group.group_login || 'Untitled Group',
        groupLogin: group.group_login || '',
        courseIds: Array.isArray(group.course_ids) ? group.course_ids.map((courseId) => String(courseId)) : [],
      })) : [];

      if (legacyMeta) {
        legacyMeta.textContent = normalizedGroups.length
          ? t(`${normalizedGroups.length} course${normalizedGroups.length === 1 ? '' : 's'} available`)
          : t('No linked legacy courses were found.');
      }

      if (legacyCount) {
        legacyCount.textContent = String(normalizedGroups.length);
      }

      if (legacyLoading) {
        legacyLoading.classList.add('hidden');
      }

      if (!normalizedGroups.length) {
        if (legacySection) legacySection.classList.add('hidden');
        legacyContainer.innerHTML = '';
        legacyContainer.classList.add('hidden');
        if (legacyEmptyMsg) legacyEmptyMsg.classList.add('hidden');
        if (legacySearchInput) {
          legacySearchInput.value = '';
          legacySearchInput.disabled = true;
        }
        if (legacyClearBtn) legacyClearBtn.classList.add('hidden');
        return;
      }

      if (legacySection) legacySection.classList.remove('hidden');

      legacyContainer.innerHTML = normalizedGroups.map((group) => `
        <div class="legacy-group-card" data-group-name="${escapeHtml(group.groupName.toLowerCase())}" data-group-login="${escapeHtml(group.groupLogin.toLowerCase())}">
          <div class="card border border-gray-200 dark:border-gray-700 h-full flex flex-col p-4">
            <h6 class="font-semibold mb-2 legacy-group-title" title="${escapeHtml(group.groupName)}">${escapeHtml(group.groupName)}</h6>
            <div class="flex-1 mb-3">
              ${group.groupLogin ? `
                <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">
                  <span class="font-medium">Group ID:</span>
                  <code class="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded">${escapeHtml(group.groupLogin)}</code>
                </p>
              ` : ''}
              ${group.courseIds.length ? `
                <p class="text-sm text-gray-500 dark:text-gray-400 mb-0">
                  <span class="font-medium">Course IDs:</span> ${escapeHtml(group.courseIds.join(', '))}
                </p>
              ` : ''}
            </div>
            <div class="flex flex-col gap-2 mt-auto">
              <a href="${escapeHtml(buildLegacyDashboardUrl(group))}" class="btn btn-sm btn-primary w-full">
                <i class="bi bi-graph-up-arrow mr-1"></i>View Dashboard
              </a>
              ${group.groupLogin ? `
                <button type="button"
                        class="btn btn-sm btn-outline-primary w-full"
                        data-course-resources-trigger
                        data-group-login="${escapeHtml(group.groupLogin)}"
                        data-group-name="${escapeHtml(group.groupName)}">
                  <i class="bi bi-folder mr-1"></i>View Resources
                </button>
              ` : `
                <p class="text-xs text-gray-500 dark:text-gray-400">
                  Group login metadata is unavailable here. Open the dashboard and enter IDs manually if needed.
                </p>
              `}
            </div>
          </div>
        </div>
      `).join('');

      legacyContainer.classList.remove('hidden');
      if (legacyEmptyMsg) legacyEmptyMsg.classList.add('hidden');
      if (legacySearchInput) legacySearchInput.disabled = false;
      if (resourcesClient) resourcesClient.bindTriggers(legacyContainer);
      filterLegacyGroups();
    }

    async function loadLegacyGroups() {
      if (!config.legacyGroupsUrl || !legacyContainer) {
        return;
      }

      if (legacyLoading) legacyLoading.classList.remove('hidden');
      if (legacyMeta) legacyMeta.textContent = t('Loading linked legacy courses...');
      if (legacySearchInput) legacySearchInput.disabled = true;

      console.info('[ModuLearn Legacy] Loading instructor legacy groups', {
        endpoint: config.legacyGroupsUrl,
      });

      try {
        const response = await fetch(config.legacyGroupsUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const data = await parseJsonResponse(response);

        console.info('[ModuLearn Legacy] Instructor legacy groups response', {
          endpoint: config.legacyGroupsUrl,
          status: response.status,
          data,
        });

        if (!response.ok || !data.success) {
          throw new Error(data.error || `${t('Failed to load legacy groups')} (${response.status})`);
        }

        renderLegacyGroups(data.groups || []);
      } catch (error) {
        console.error('Error loading instructor legacy groups:', error);
        if (legacyLoading) legacyLoading.classList.add('hidden');
        if (legacyContainer) legacyContainer.classList.add('hidden');
        if (legacyMeta) legacyMeta.textContent = error.message || t('Failed to load linked legacy courses.');
        if (legacyEmptyMsg) {
          legacyEmptyMsg.classList.remove('hidden');
          legacyEmptyMsg.querySelector('p').textContent = error.message || t('Failed to load linked legacy courses.');
        }
        if (legacyCount) legacyCount.textContent = '0';
      }
    }

    if (legacySearchInput) {
      legacySearchInput.addEventListener('input', filterLegacyGroups);
    }
    if (legacyClearBtn) {
      legacyClearBtn.addEventListener('click', () => {
        if (!legacySearchInput) return;
        legacySearchInput.value = '';
        filterLegacyGroups();
        legacySearchInput.focus();
      });
    }

    loadLegacyGroups().catch((error) => console.error('Unexpected legacy group hydration failure:', error));

    const importJsonModal = document.getElementById('importJsonCourseModal');
    const jsonFileInput = document.getElementById('jsonFileInput');
    const jsonTextInput = document.getElementById('jsonTextInput');
    const importJsonSubmitBtn = document.getElementById('importJsonSubmitBtn');
    const jsonImportError = document.getElementById('jsonImportError');
    const jsonImportSuccess = document.getElementById('jsonImportSuccess');
    const filePreview = document.getElementById('filePreview');
    const filePreviewContent = document.getElementById('filePreviewContent');

    function resetImportJsonState() {
      if (jsonFileInput) jsonFileInput.value = '';
      if (jsonTextInput) jsonTextInput.value = '';
      if (jsonImportError) jsonImportError.classList.add('hidden');
      if (jsonImportSuccess) jsonImportSuccess.classList.add('hidden');
      if (filePreview) filePreview.classList.add('hidden');
      if (importJsonSubmitBtn) {
        importJsonSubmitBtn.disabled = false;
        importJsonSubmitBtn.innerHTML = `<i class="bi bi-upload mr-1"></i>${t('Import Course')}`;
      }
    }

    if (importJsonModal) {
      importJsonModal.addEventListener('hidden.bs.modal', resetImportJsonState);
    }

    if (jsonFileInput) {
      jsonFileInput.addEventListener('change', function (event) {
        const file = event.target.files[0];
        if (!file) {
          filePreview.classList.add('hidden');
          return;
        }

        if (file.type !== 'application/json' && !file.name.endsWith('.json')) {
          jsonImportError.textContent = t('Please select a valid JSON file.');
          jsonImportError.classList.remove('hidden');
          jsonFileInput.value = '';
          filePreview.classList.add('hidden');
          return;
        }

        const reader = new FileReader();
        reader.onload = function (readerEvent) {
          try {
            const parsed = JSON.parse(readerEvent.target.result);
            filePreviewContent.textContent = JSON.stringify(parsed, null, 2);
            filePreview.classList.remove('hidden');
            jsonImportError.classList.add('hidden');
          } catch (error) {
            jsonImportError.textContent = `${t('Invalid JSON file:')} ${error.message}`;
            jsonImportError.classList.remove('hidden');
            filePreview.classList.add('hidden');
          }
        };
        reader.readAsText(file);
      });
    }

    const formatJsonBtn = document.getElementById('formatJsonBtn');
    if (formatJsonBtn) {
      formatJsonBtn.addEventListener('click', function () {
        try {
          const parsed = JSON.parse(jsonTextInput.value.trim());
          jsonTextInput.value = JSON.stringify(parsed, null, 2);
          jsonImportError.classList.add('hidden');
        } catch (error) {
          jsonImportError.textContent = `${t('Invalid JSON:')} ${error.message}`;
          jsonImportError.classList.remove('hidden');
        }
      });
    }

    const clearJsonBtn = document.getElementById('clearJsonBtn');
    if (clearJsonBtn) {
      clearJsonBtn.addEventListener('click', function () {
        jsonTextInput.value = '';
        jsonImportError.classList.add('hidden');
      });
    }

    if (importJsonSubmitBtn) {
      importJsonSubmitBtn.addEventListener('click', async function () {
        jsonImportError.classList.add('hidden');
        jsonImportSuccess.classList.add('hidden');

        let courseData = null;
        const activeTab = document.querySelector('#importJsonTabs .nav-link.active');
        if (activeTab && activeTab.id === 'upload-tab') {
          const file = jsonFileInput.files[0];
          if (!file) {
            jsonImportError.textContent = t('Please select a JSON file.');
            jsonImportError.classList.remove('hidden');
            return;
          }

          try {
            courseData = JSON.parse(await file.text());
          } catch (error) {
            jsonImportError.textContent = `${t('Error reading file:')} ${error.message}`;
            jsonImportError.classList.remove('hidden');
            return;
          }
        } else {
          try {
            courseData = JSON.parse(jsonTextInput.value.trim());
          } catch (error) {
            jsonImportError.textContent = `${t('Invalid JSON format:')} ${error.message}`;
            jsonImportError.classList.remove('hidden');
            return;
          }
        }

        if (!courseData.id && !courseData.name) {
          jsonImportError.textContent = t('Invalid course structure: missing required fields (id or name).');
          jsonImportError.classList.remove('hidden');
          return;
        }

        importJsonSubmitBtn.disabled = true;
        importJsonSubmitBtn.innerHTML = `<span class="spinner-border spinner-border-sm"></span> ${t('Importing...')}`;

        try {
          const response = await fetch(config.createCourseUrl, {
            method: 'POST',
            headers: csrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ course_data: courseData }),
          });
          const data = await parseJsonResponse(response);
          if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to import course');
          }

          jsonImportSuccess.classList.remove('hidden');
          window.setTimeout(() => window.location.reload(), 1000);
        } catch (error) {
          console.error('Error importing course:', error);
          jsonImportError.textContent = `${t('Error:')} ${error.message}`;
          jsonImportError.classList.remove('hidden');
          importJsonSubmitBtn.disabled = false;
          importJsonSubmitBtn.innerHTML = `<i class="bi bi-upload mr-1"></i>${t('Import Course')}`;
        }
      });
    }

    const importCourseButton = document.getElementById('importCourseButton');
    if (importCourseButton) {
      importCourseButton.addEventListener('click', async function () {
        const button = this;
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = t('Connecting...');

        try {
          const tokenResponse = await fetch(config.generateCourseAuthUrl, {
            method: 'POST',
            headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          });
          const tokenData = await parseJsonResponse(tokenResponse);

          if (!tokenResponse.ok || tokenData.error) {
            const errorMessage = tokenData.error || t('Failed to authenticate with course-authoring');
            if (tokenData.password_mismatch) {
              const shouldReset = window.confirm(
                t('Password mismatch detected in course-authoring.\n\nWould you like ModuLearn to generate a new password so you can sync the external account?')
              );
              if (shouldReset) {
                const resetResponse = await fetch(config.resetCourseAuthoringPasswordUrl, {
                  method: 'POST',
                  headers: csrfHeaders({ 'Content-Type': 'application/json' }),
                });
                const resetData = await parseJsonResponse(resetResponse);
                if (resetResponse.ok && resetData.success) {
                  alert(`${t('Password reset successful.\n\nNew password:')}\n${resetData.new_password}\n\n${t('Share this with the course-authoring administrator so the accounts can be synced.')}`);
                } else {
                  alert(t(resetData.error || 'Failed to reset course-authoring password.'));
                }
              }
            } else {
              alert(t(errorMessage));
            }
            button.disabled = false;
            button.innerHTML = originalText;
            return;
          }

          button.innerHTML = t('Logging in...');

          try {
            const loginResponse = await fetch(config.courseAuthoringXLoginUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({ token: tokenData.token }),
            });

            if (!loginResponse.ok) {
              throw new Error(t('Direct x-login failed'));
            }

            window.setTimeout(() => {
              window.location.href = config.courseAuthoringAppUrl;
            }, 100);
          } catch (error) {
            const proxyResponse = await fetch(config.proxyCourseAuthoringXLoginUrl, {
              method: 'POST',
              headers: csrfHeaders({ 'Content-Type': 'application/json' }),
              credentials: 'include',
              body: JSON.stringify({ token: tokenData.token }),
            });
            const proxyData = await parseJsonResponse(proxyResponse);
            if (!proxyResponse.ok || proxyData.error) {
              throw new Error(proxyData.error || t('Failed to establish a course-authoring session.'));
            }

            alert(t('Course-authoring session was prepared through the ModuLearn proxy. Redirecting now.'));
            window.location.href = config.courseAuthoringAppUrl;
          }
        } catch (error) {
          console.error('Error connecting to course-authoring:', error);
          alert(t(error.message || 'An error occurred while connecting to course-authoring.'));
          button.disabled = false;
          button.innerHTML = originalText;
        }
      });
    }
  });
})();
