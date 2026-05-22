(function () {
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

  function parseJsonResponse(response) {
    return response.json().catch(() => ({}));
  }

  document.addEventListener('DOMContentLoaded', function () {
    const app = document.getElementById('instructorDashboardApp');
    if (!app) return;

    const config = {
      csrfToken: app.dataset.csrfToken || '',
      courseDetailsPattern: app.dataset.courseDetailsPattern || '',
      courseDeletePattern: app.dataset.courseDeletePattern || '',
      getEnrollmentsPattern: app.dataset.getEnrollmentsPattern || '',
      removeEnrollmentPattern: app.dataset.removeEnrollmentPattern || '',
      bulkEnrollPattern: app.dataset.bulkEnrollPattern || '',
      createCourseInstancePattern: app.dataset.createCourseInstancePattern || '',
      checkGroupNameUrl: app.dataset.checkGroupNameUrl || '',
      createCourseUrl: app.dataset.createCourseUrl || '',
      generateCourseAuthUrl: app.dataset.generateCourseAuthUrl || '',
      resetCourseAuthoringPasswordUrl: app.dataset.resetCourseAuthoringPasswordUrl || '',
      proxyCourseAuthoringXLoginUrl: app.dataset.proxyCourseAuthoringXLoginUrl || '',
      resourceApiPattern: app.dataset.resourceApiPattern || '',
      ltiLaunchPath: app.dataset.ltiLaunchPath || '',
      courseAuthoringXLoginUrl: app.dataset.courseAuthoringXLoginUrl || '',
      courseAuthoringAppUrl: app.dataset.courseAuthoringAppUrl || '',
    };

    const resourcesClient = window.ModuLearnCourseResources
      ? window.ModuLearnCourseResources.init({ resourceApiPattern: config.resourceApiPattern })
      : null;

    if (resourcesClient) {
      resourcesClient.bindTriggers(app);
    }

    function csrfHeaders(extraHeaders) {
      return Object.assign({ 'X-CSRFToken': config.csrfToken }, extraHeaders || {});
    }

    function createNewSession(courseId) {
      document.getElementById('courseId').value = courseId;
      document.getElementById('groupName').value = '';
      document.getElementById('groupName').classList.remove('is-valid', 'is-invalid');
      document.getElementById('groupNameFeedback').textContent = '';
      document.getElementById('newSessionForm').dataset.courseId = courseId;
      bootstrap.Modal.getOrCreateInstance(document.getElementById('newSessionModal')).show();
    }

    async function showDeleteCourseConfirmation(courseId) {
      const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteCourseModal'));
      const confirmButton = document.getElementById('confirmDeleteButton');
      const instancesList = document.getElementById('instancesListGroup');
      const noInstancesMessage = document.getElementById('noInstancesMessage');
      const courseInstancesList = document.getElementById('courseInstancesList');

      modal.show();
      document.getElementById('courseToDelete').textContent = 'Loading...';
      confirmButton.disabled = true;
      instancesList.innerHTML = '';
      noInstancesMessage.classList.add('hidden');
      courseInstancesList.classList.remove('hidden');

      try {
        const response = await fetch(replacePattern(config.courseDetailsPattern, '__COURSE_ID__', courseId));
        const data = await parseJsonResponse(response);
        if (!response.ok || data.error) {
          throw new Error(data.error || `Failed to load course details (${response.status})`);
        }

        document.getElementById('courseToDelete').textContent = data.course.title;
        if (data.instances && data.instances.length) {
          data.instances.forEach((instance) => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.textContent = `${instance.group_name} (${instance.enrollment_count} students enrolled)`;
            instancesList.appendChild(li);
          });
          courseInstancesList.classList.remove('hidden');
          noInstancesMessage.classList.add('hidden');
        } else {
          courseInstancesList.classList.add('hidden');
          noInstancesMessage.classList.remove('hidden');
          noInstancesMessage.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">This course has no active sessions.</p>';
        }

        confirmButton.disabled = false;
        confirmButton.onclick = () => deleteCourse(courseId);
      } catch (error) {
        console.error('Error fetching course details:', error);
        document.getElementById('courseToDelete').textContent = 'Error loading course details';
        courseInstancesList.classList.add('hidden');
        noInstancesMessage.classList.remove('hidden');
        noInstancesMessage.innerHTML = `<div class="alert alert-danger">Error: ${error.message || 'Failed to load course details'}</div>`;
      }
    }

    async function deleteCourse(courseId) {
      const confirmButton = document.getElementById('confirmDeleteButton');
      confirmButton.disabled = true;
      confirmButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';

      try {
        const response = await fetch(replacePattern(config.courseDeletePattern, '__COURSE_ID__', courseId), {
          method: 'POST',
          headers: csrfHeaders({ 'Content-Type': 'application/json' }),
        });
        const data = await parseJsonResponse(response);

        if (!response.ok || !data.success) {
          throw new Error(data.error || 'Failed to delete course');
        }

        window.location.reload();
      } catch (error) {
        console.error('Error deleting course:', error);
        alert(`Error: ${error.message || 'Failed to delete course'}`);
        confirmButton.disabled = false;
        confirmButton.innerHTML = '<i class="bi bi-trash mr-1"></i>Delete Course';
      }
    }

    async function loadEnrollments(courseInstanceId) {
      const tableBody = document.getElementById('enrollmentTableBody');
      if (!tableBody) return;

      tableBody.innerHTML = `
        <tr>
          <td colspan="4" class="text-center text-gray-400 py-4">
            <span class="spinner-border mr-2"></span>Loading...
          </td>
        </tr>
      `;

      try {
        const response = await fetch(replacePattern(config.getEnrollmentsPattern, '__COURSE_INSTANCE_ID__', courseInstanceId));
        const data = await parseJsonResponse(response);

        if (!response.ok) {
          throw new Error(data.error || `Failed to load enrollments (${response.status})`);
        }

        tableBody.innerHTML = '';
        if (data.enrollments && data.enrollments.length) {
          data.enrollments.forEach((enrollment) => {
            const row = document.createElement('tr');
            row.innerHTML = `
              <td>${enrollment.student.email}</td>
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
              <td colspan="4" class="text-center text-gray-500 py-4">
                <em>No students are currently enrolled in this course session.</em>
              </td>
            </tr>
          `;
        }
      } catch (error) {
        console.error('Error loading enrollments:', error);
        tableBody.innerHTML = `
          <tr>
            <td colspan="4" class="text-center text-red-500 py-4">
              <em>Error loading enrollments. Please try again.</em>
            </td>
          </tr>
        `;
      }
    }

    function attachRemoveListeners() {
      document.querySelectorAll('.remove-enrollment').forEach((button) => {
        button.addEventListener('click', async function () {
          if (!window.confirm('Are you sure you want to remove this student?')) {
            return;
          }

          try {
            const response = await fetch(
              replacePattern(config.removeEnrollmentPattern, '__ENROLLMENT_ID__', this.dataset.enrollmentId),
              { method: 'POST', headers: csrfHeaders() }
            );
            const data = await parseJsonResponse(response);
            if (!response.ok || !data.success) {
              throw new Error(data.error || 'Failed to remove enrollment');
            }
            this.closest('tr').remove();
          } catch (error) {
            console.error('Error removing enrollment:', error);
            alert(error.message || 'An error occurred while removing the student.');
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
          throw new Error(data.error || `Failed to validate session name (${response.status})`);
        }

        if (data.available) {
          groupNameInput.classList.remove('is-invalid');
          groupNameInput.classList.add('is-valid');
          groupNameFeedback.textContent = 'Session name is available';
          groupNameFeedback.className = 'valid-feedback text-sm';
          submitButton.disabled = false;
        } else {
          groupNameInput.classList.remove('is-valid');
          groupNameInput.classList.add('is-invalid');
          groupNameFeedback.textContent = data.error || 'This session name already exists for this course';
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
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Creating...';

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
            throw new Error(data.error || 'Failed to create session');
          }
          window.location.reload();
        } catch (error) {
          console.error('Error creating course session:', error);
          alert(error.message || 'An error occurred while creating the course session.');
        } finally {
          submitButton.disabled = false;
          submitButton.innerHTML = 'Create Session';
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
          alert('Please enter at least one email address.');
          return;
        }

        const submitButton = this.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Adding...';

        try {
          const response = await fetch(replacePattern(config.bulkEnrollPattern, '__COURSE_INSTANCE_ID__', courseInstanceId), {
            method: 'POST',
            headers: csrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ emails }),
          });
          const data = await parseJsonResponse(response);

          if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to enroll students');
          }

          emailList.value = '';
          await loadEnrollments(courseInstanceId);

          let message = `Successfully enrolled ${data.success_count} students.`;
          if (data.error_count > 0) {
            message += `\n\nErrors:\n${data.error_details.join('\n')}`;
          }
          alert(message);
        } catch (error) {
          console.error('Error enrolling students:', error);
          alert(error.message || 'An error occurred while enrolling students.');
        } finally {
          submitButton.disabled = false;
          submitButton.innerHTML = '<i class="bi bi-person-plus mr-1"></i>Add Students';
        }
      });
    }

    const manageEnrollmentModal = document.getElementById('manageEnrollmentModal');
    if (manageEnrollmentModal) {
      manageEnrollmentModal.addEventListener('show.bs.modal', function (event) {
        const button = event.relatedTarget;
        document.getElementById('manageEnrollmentModalLabel').textContent =
          `${button.getAttribute('data-course-title')} - ${button.getAttribute('data-group-name')}`;
        document.getElementById('currentCourseInstanceId').value = button.getAttribute('data-course-instance-id');
        loadEnrollments(button.getAttribute('data-course-instance-id'));
      });
    }

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

    document.querySelectorAll('.copy-lti-url').forEach((button) => {
      button.addEventListener('click', function () {
        const ltiUrl = new URL(config.ltiLaunchPath, window.location.origin);
        ltiUrl.searchParams.set('course_id', this.dataset.courseInstanceId);

        navigator.clipboard.writeText(ltiUrl.toString()).then(() => {
          const tooltip = new bootstrap.Tooltip(button, {
            title: 'URL Copied!',
            trigger: 'manual',
          });
          tooltip.show();
          window.setTimeout(() => tooltip.dispose(), 1500);
        }).catch((error) => {
          console.error('Failed to copy URL:', error);
          alert('Failed to copy URL to clipboard.');
        });
      });
    });

    const legacySearchInput = document.getElementById('legacyGroupsSearch');
    const legacyClearBtn = document.getElementById('clearLegacySearch');
    const legacyEmptyMsg = document.getElementById('legacyGroupsEmpty');
    const legacyContainer = document.getElementById('legacyGroupsContainer');
    const legacySection = document.getElementById('legacyGroupsSection');
    if (legacySearchInput && legacyContainer) {
      const legacyCards = Array.from(legacyContainer.querySelectorAll('.legacy-group-card'));
      if (legacyCards.length === 0) {
        if (legacySection) {
          legacySection.classList.add('hidden');
        }
        if (legacyEmptyMsg) {
          legacyEmptyMsg.classList.add('hidden');
        }
      } else {
        if (legacySection) {
          legacySection.classList.remove('hidden');
        }

        const filterLegacyGroups = () => {
          const searchTerm = legacySearchInput.value.toLowerCase().trim();
          let visibleCount = 0;

          legacyCards.forEach((card) => {
            const groupName = card.dataset.groupName || '';
            const groupLogin = card.dataset.groupLogin || '';
            const matches = !searchTerm || groupName.includes(searchTerm) || groupLogin.includes(searchTerm);
            card.style.display = matches ? '' : 'none';
            if (matches) visibleCount += 1;
          });

          if (legacyEmptyMsg) {
            legacyEmptyMsg.classList.toggle('hidden', !(searchTerm && visibleCount === 0));
          }
          legacyContainer.classList.toggle('hidden', Boolean(searchTerm && visibleCount === 0));
          if (legacyClearBtn) {
            legacyClearBtn.classList.toggle('hidden', !searchTerm);
          }
        };

        legacySearchInput.addEventListener('input', filterLegacyGroups);
        if (legacyClearBtn) {
          legacyClearBtn.addEventListener('click', () => {
            legacySearchInput.value = '';
            filterLegacyGroups();
            legacySearchInput.focus();
          });
        }
      }
    }

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
        importJsonSubmitBtn.innerHTML = '<i class="bi bi-upload mr-1"></i>Import Course';
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
          jsonImportError.textContent = 'Please select a valid JSON file.';
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
            jsonImportError.textContent = `Invalid JSON file: ${error.message}`;
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
          jsonImportError.textContent = `Invalid JSON: ${error.message}`;
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
            jsonImportError.textContent = 'Please select a JSON file.';
            jsonImportError.classList.remove('hidden');
            return;
          }

          try {
            courseData = JSON.parse(await file.text());
          } catch (error) {
            jsonImportError.textContent = `Error reading file: ${error.message}`;
            jsonImportError.classList.remove('hidden');
            return;
          }
        } else {
          try {
            courseData = JSON.parse(jsonTextInput.value.trim());
          } catch (error) {
            jsonImportError.textContent = `Invalid JSON format: ${error.message}`;
            jsonImportError.classList.remove('hidden');
            return;
          }
        }

        if (!courseData.id && !courseData.name) {
          jsonImportError.textContent = 'Invalid course structure: missing required fields (id or name).';
          jsonImportError.classList.remove('hidden');
          return;
        }

        importJsonSubmitBtn.disabled = true;
        importJsonSubmitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Importing...';

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
          jsonImportError.textContent = `Error: ${error.message}`;
          jsonImportError.classList.remove('hidden');
          importJsonSubmitBtn.disabled = false;
          importJsonSubmitBtn.innerHTML = '<i class="bi bi-upload mr-1"></i>Import Course';
        }
      });
    }

    const importCourseButton = document.getElementById('importCourseButton');
    if (importCourseButton) {
      importCourseButton.addEventListener('click', async function () {
        const button = this;
        const originalText = button.innerHTML;
        button.disabled = true;
        button.innerHTML = 'Connecting...';

        try {
          const tokenResponse = await fetch(config.generateCourseAuthUrl, {
            method: 'POST',
            headers: csrfHeaders({ 'Content-Type': 'application/json' }),
          });
          const tokenData = await parseJsonResponse(tokenResponse);

          if (!tokenResponse.ok || tokenData.error) {
            const errorMessage = tokenData.error || 'Failed to authenticate with course-authoring';
            if (tokenData.password_mismatch) {
              const shouldReset = window.confirm(
                'Password mismatch detected in course-authoring.\n\nWould you like ModuLearn to generate a new password so you can sync the external account?'
              );
              if (shouldReset) {
                const resetResponse = await fetch(config.resetCourseAuthoringPasswordUrl, {
                  method: 'POST',
                  headers: csrfHeaders({ 'Content-Type': 'application/json' }),
                });
                const resetData = await parseJsonResponse(resetResponse);
                if (resetResponse.ok && resetData.success) {
                  alert(`Password reset successful.\n\nNew password:\n${resetData.new_password}\n\nShare this with the course-authoring administrator so the accounts can be synced.`);
                } else {
                  alert(resetData.error || 'Failed to reset course-authoring password.');
                }
              }
            } else {
              alert(errorMessage);
            }
            button.disabled = false;
            button.innerHTML = originalText;
            return;
          }

          button.innerHTML = 'Logging in...';

          try {
            const loginResponse = await fetch(config.courseAuthoringXLoginUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({ token: tokenData.token }),
            });

            if (!loginResponse.ok) {
              throw new Error('Direct x-login failed');
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
              throw new Error(proxyData.error || 'Failed to establish a course-authoring session.');
            }

            alert('Course-authoring session was prepared through the ModuLearn proxy. Redirecting now.');
            window.location.href = config.courseAuthoringAppUrl;
          }
        } catch (error) {
          console.error('Error connecting to course-authoring:', error);
          alert(error.message || 'An error occurred while connecting to course-authoring.');
          button.disabled = false;
          button.innerHTML = originalText;
        }
      });
    }
  });
})();
