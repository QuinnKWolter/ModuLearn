/* Aggregate drill-down. Uses the shared analytics renderer and its loaded data. */
function cellActivityMetrics(values = {}) {
  const progress = clampPercent(values.p || 0);
  const complete = values.is_complete ?? (Number(values.p || 0) >= 1);
  const attempts = values.attempts ?? values.a ?? null;
  const score = values.score == null ? null : Number(values.score);
  return {progress, complete, attempts, score,
    status: complete ? 'Completed' : progress > 0 ? 'In progress' : Number(attempts) > 0 ? 'Attempted' : 'Not started'};
}

function analyticsText(text, params = {}) {
  return escapeHtml(window.ModuLearnI18n?.t(text, params) || text.replace(/\{(\w+)\}/g, (match, key) => params[key] ?? match));
}

function renderCellExercises(learner, topicId, resourceId, activities, averages) {
  if (!activities.length) return `<p class="p-4">${analyticsText('No activities in this cell.')}</p>`;
  return `<div class="overflow-x-auto"><table class="table table-sm w-full mb-0">
    <thead><tr>${['Activity', 'Status', 'Progress', 'Score', 'Attempts', 'Class average progress', 'Details'].map(label => `<th>${analyticsText(label)}</th>`).join('')}</tr></thead>
    <tbody>${activities.map(activity => {
      const metrics = cellActivityMetrics(learner?.state?.activities?.[topicId]?.[resourceId]?.[activity.id]?.values);
      const average = clampPercent(averages[activity.id] || 0);
      const difference = metrics.progress - average;
      return `<tr>
        <td class="max-w-xs break-words" title="${escapeHtml(activity.name || activity.id)}">${escapeHtml(activity.name || activity.id)}</td>
        <td>${analyticsText(metrics.status)}</td><td class="font-semibold">${metrics.progress}%</td>
        <td>${metrics.score === null || !Number.isFinite(metrics.score) ? '—' : `${Math.round(metrics.score)}%`}</td>
        <td>${metrics.attempts === null ? '—' : escapeHtml(metrics.attempts)}</td>
        <td>${average}%<div class="text-xs text-gray-500 dark:text-gray-400">${analyticsText('{delta} pp vs class', {delta: `${difference > 0 ? '+' : ''}${difference}`})}</div></td>
        <td><button type="button" class="module-capture-btn" data-module-capture
          data-learner-id="${escapeHtml(learner.id)}" data-module-id="${escapeHtml(activity.id)}"
          data-participant-session-uuid="${escapeHtml(learner.participant_session_uuid || '')}"
          title="${analyticsText('View raw capture history')}">${analyticsText('Raw')}</button></td></tr>`;
    }).join('')}</tbody></table></div>`;
}

function handleCellClick(topicId, resourceId, topicName, resourceName) {
  const classAvg = responseData.groups?.find(g => g.name === 'Class Average');
  if (!classAvg) return;
  const activities = (responseData.topics || []).find(t => String(t.id) === String(topicId))?.activities?.[resourceId] || [];
  const students = (responseData.learners || []).map(learner => {
    const metrics = activities.map(activity => cellActivityMetrics(learner?.state?.activities?.[topicId]?.[resourceId]?.[activity.id]?.values));
    return {learner, pct: clampPercent(learner?.state?.topics?.[topicId]?.values?.[resourceId]?.p || 0),
      completed: metrics.filter(m => m.complete).length,
      attempted: metrics.filter(m => m.complete || m.progress > 0 || Number(m.attempts) > 0).length};
  }).sort((a, b) => b.pct - a.pct || String(a.learner.id).localeCompare(String(b.learner.id)));
  const averages = {};
  activities.forEach(activity => {
    averages[activity.id] = students.length ? students.reduce((sum, {learner}) => sum + (Number(learner?.state?.activities?.[topicId]?.[resourceId]?.[activity.id]?.values?.p) || 0), 0) / students.length : 0;
  });
  const modalId = 'analyticsCellModal';
  document.getElementById(modalId)?.remove();
  const classPct = clampPercent(classAvg?.state?.topics?.[topicId]?.values?.[resourceId]?.p || 0);
  document.body.insertAdjacentHTML('beforeend', `
    <div class="modal-overlay hidden fixed inset-0 z-[60] items-center justify-center bg-black/50 p-4" id="${modalId}" role="dialog" aria-modal="true" aria-labelledby="cellModalTitle" aria-hidden="true">
      <div class="modal-backdrop-close absolute inset-0"></div>
      <div class="relative bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden">
        <header class="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 id="cellModalTitle" class="text-lg font-bold">${escapeHtml(topicName)} · ${escapeHtml(resourceName)}</h2>
          <button type="button" data-bs-dismiss="modal" class="text-2xl p-2" aria-label="${analyticsText('Close')}">&times;</button>
        </header>
        <div class="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
          <div class="flex flex-wrap gap-4 text-sm">
            <span><strong>${classPct}%</strong> ${analyticsText('Class average progress')}</span>
            <span><strong>${students.filter(s => s.attempted > 0).length}/${students.length}</strong> ${analyticsText('Students with recorded work')}</span>
            <span><strong>${activities.length}</strong> ${analyticsText('Activities')}</span>
          </div>
          <p class="text-sm text-gray-500 dark:text-gray-400">${analyticsText('Expand a student to see exercises, scores, attempts, and comparison with the class. A dash means no grade was recorded.')}</p>
          <label class="block"><span class="text-sm font-semibold">${analyticsText('Find a student')}</span>
            <input type="search" class="form-control mt-1" data-cell-student-filter placeholder="${analyticsText('Name or username')}" autocomplete="off"></label>
          <div class="space-y-2" data-cell-students>
            ${students.map((student, index) => `<details class="student-resource-detail" data-cell-student="${index}">
              <summary class="flex flex-wrap gap-2 items-center justify-between cursor-pointer">
                <span class="min-w-0"><span class="font-semibold break-words">${escapeHtml(student.learner.name || student.learner.id)}</span>
                ${student.learner.name && student.learner.name !== student.learner.id ? `<span class="block text-xs text-gray-500 dark:text-gray-400">${escapeHtml(student.learner.id)}</span>` : ''}</span>
                <span class="text-sm">${analyticsText('{done}/{total} completed', {done: student.completed, total: activities.length})} · <strong>${student.pct}%</strong> <span aria-hidden="true">⌄</span></span>
              </summary><div class="mt-3" data-cell-exercises></div>
            </details>`).join('')}
          </div>
          <p class="text-sm text-gray-500" data-cell-empty ${students.length ? 'hidden' : ''}>${analyticsText('No students match.')}</p>
        </div>
      </div>
    </div>`);
  const modal = document.getElementById(modalId);
  // Build exercise rows only on expansion. Raw logs still load only on demand.
  modal.querySelectorAll('[data-cell-student]').forEach(details => {
    details.addEventListener('toggle', () => {
      if (!details.open || details.dataset.loaded) return;
      const student = students[Number(details.dataset.cellStudent)];
      details.querySelector('[data-cell-exercises]').innerHTML = renderCellExercises(student.learner, topicId, resourceId, activities, averages);
      details.dataset.loaded = 'true';
    });
  });
  modal.querySelector('[data-cell-student-filter]').addEventListener('input', event => {
    const query = event.target.value.trim().toLocaleLowerCase();
    let visible = 0;
    modal.querySelectorAll('[data-cell-student]').forEach(details => {
      const learner = students[Number(details.dataset.cellStudent)].learner;
      const matches = `${learner.name || ''} ${learner.id}`.toLocaleLowerCase().includes(query);
      details.hidden = !matches;
      if (matches) visible += 1;
    });
    modal.querySelector('[data-cell-empty]').hidden = visible > 0;
  });
  new bootstrap.Modal(modal).show();
}
