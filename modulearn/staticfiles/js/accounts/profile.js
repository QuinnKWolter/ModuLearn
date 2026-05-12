(function () {
  document.addEventListener('DOMContentLoaded', function () {
    const app = document.getElementById('profilePageApp');
    if (!app) return;

    const resourcesClient = window.ModuLearnCourseResources
      ? window.ModuLearnCourseResources.init({ resourceApiPattern: app.dataset.resourceApiPattern || '' })
      : null;

    if (resourcesClient) {
      resourcesClient.bindTriggers(app);
    }

    const searchInput = document.getElementById('ktGroupsSearch');
    const clearButton = document.getElementById('clearKtGroupsSearch');
    const emptyMessage = document.getElementById('ktGroupsEmpty');
    const groupsList = document.getElementById('ktGroupsList');

    if (!searchInput || !groupsList) return;

    const items = Array.from(groupsList.querySelectorAll('.kt-group-item'));

    function filterGroups() {
      const query = searchInput.value.toLowerCase().trim();
      let visibleCount = 0;

      items.forEach((item) => {
        const name = item.dataset.groupName || '';
        const login = item.dataset.groupLogin || '';
        const matches = !query || name.includes(query) || login.includes(query);
        item.classList.toggle('hidden', !matches);
        if (matches) visibleCount += 1;
      });

      if (emptyMessage) {
        emptyMessage.classList.toggle('hidden', !(query && visibleCount === 0));
      }
      if (clearButton) {
        clearButton.classList.toggle('hidden', !query);
      }
    }

    searchInput.addEventListener('input', filterGroups);
    if (clearButton) {
      clearButton.addEventListener('click', function () {
        searchInput.value = '';
        filterGroups();
        searchInput.focus();
      });
    }

    filterGroups();
  });
})();
