(function () {
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function createClient(config) {
    const cache = {};

    function patternUrl(groupLogin) {
      return (config.resourceApiPattern || '').replace('__GROUP_LOGIN__', encodeURIComponent(groupLogin));
    }

    function showLoading() {
      const resourcesList = document.getElementById('courseResourcesList');
      if (!resourcesList) return;

      resourcesList.innerHTML = `
        <li class="text-center py-10 px-4">
          <div class="spinner-border loading-spin text-blue-600" role="status">
            <span class="sr-only">Loading resources...</span>
          </div>
          <p class="text-gray-400 mt-3 text-sm">Loading resources...</p>
        </li>
      `;
    }

    function showError(message) {
      const resourcesList = document.getElementById('courseResourcesList');
      if (!resourcesList) return;

      resourcesList.innerHTML = `
        <li class="text-center py-10 px-4">
          <i class="bi bi-exclamation-triangle text-yellow-500 text-3xl"></i>
          <p class="text-red-500 mt-3 text-sm">${escapeHtml(message)}</p>
        </li>
      `;
    }

    function openResource(url) {
      window.open(url, '_blank', 'noopener,noreferrer');
    }

    function renderResources(resources) {
      const resourcesList = document.getElementById('courseResourcesList');
      if (!resourcesList) return;

      if (!resources.length) {
        resourcesList.innerHTML = `
          <li class="text-center py-10 px-4">
            <i class="bi bi-inbox text-3xl text-gray-300"></i>
            <p class="text-gray-400 mt-3 text-sm">No resources available for this course.</p>
          </li>
        `;
        return;
      }

      resourcesList.innerHTML = resources.map((resource) => {
        const isMasteryGrids = resource.resource_type === 'masterygrids';
        const iconClass = isMasteryGrids ? 'bi-grid-3x3-gap' :
          resource.resource_type === 'folder' ? 'bi-folder' : 'bi-file-earmark';
        const badgeColor = isMasteryGrids ? 'badge-primary' :
          resource.resource_type === 'folder' ? 'badge-secondary' : 'badge-info';
        const resourceUrl = resource.show_url_direct || resource.show_url || resource.URL || resource.url || '';

        return `
          <li class="list-group-item list-group-item-action resource-item" data-resource-url="${escapeHtml(resourceUrl)}">
            <div class="flex justify-between items-center">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <i class="bi ${iconClass}"></i>
                  <strong class="truncate">${escapeHtml(resource.Title || resource.title || 'Untitled resource')}</strong>
                  ${resourceUrl ? '<i class="bi bi-box-arrow-up-right text-gray-400 text-xs"></i>' : ''}
                </div>
                ${(resource.Description || resource.description) ? `<small class="text-gray-400 block mt-1 truncate">${escapeHtml(resource.Description || resource.description)}</small>` : ''}
              </div>
              <div class="ml-3 shrink-0">
                <span class="badge ${badgeColor}">${escapeHtml(resource.resource_type || 'resource')}</span>
              </div>
            </div>
          </li>
        `;
      }).join('');

      resourcesList.querySelectorAll('.resource-item').forEach((item) => {
        item.addEventListener('click', () => {
          const url = item.dataset.resourceUrl;
          if (url) {
            openResource(url);
          }
        });
      });
    }

    async function loadResources(groupLogin, groupName) {
      const groupNameEl = document.getElementById('courseResourcesGroupName');
      if (groupNameEl) {
        groupNameEl.textContent = groupName || groupLogin;
      }

      if (cache[groupLogin]) {
        renderResources(cache[groupLogin]);
        return;
      }

      showLoading();

      try {
        const endpoint = patternUrl(groupLogin);
        console.info('[ModuLearn Legacy] Loading course resources', {
          groupLogin,
          endpoint,
        });

        const response = await fetch(endpoint);
        const data = await response.json();

        console.info('[ModuLearn Legacy] Course resources response', {
          groupLogin,
          endpoint,
          status: response.status,
          data,
        });

        if (!response.ok || !data.success) {
          throw new Error(data.error || `Failed to load resources (${response.status})`);
        }

        cache[groupLogin] = data.resources || [];
        renderResources(cache[groupLogin]);
      } catch (error) {
        console.error('Error loading course resources:', error);
        showError(error.message || 'Failed to load course resources.');
      }
    }

    function openCourseResourcesModal(groupLogin, groupName) {
      const modalElement = document.getElementById('courseResourcesModal');
      if (!modalElement || typeof bootstrap === 'undefined' || !bootstrap.Modal) {
        return;
      }

      const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
      modal.show();
      loadResources(groupLogin, groupName);
    }

    function bindTriggers(root) {
      (root || document).querySelectorAll('[data-course-resources-trigger]').forEach((trigger) => {
        trigger.addEventListener('click', () => {
          openCourseResourcesModal(trigger.dataset.groupLogin || '', trigger.dataset.groupName || '');
        });
      });
    }

    return {
      bindTriggers,
      openCourseResourcesModal,
    };
  }

  window.ModuLearnCourseResources = {
    init(config) {
      const client = createClient(config || {});
      window.openCourseResourcesModal = client.openCourseResourcesModal;
      return client;
    },
  };
})();
