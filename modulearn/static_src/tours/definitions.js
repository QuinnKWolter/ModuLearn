/* Content lives here; selectors are stable data-tour anchors, not CSS layout classes.
 * Bump version when the meaning/order changes. Copy goes through the shared catalog.
 * modal is an explicit, read-only preparation step; no arbitrary scripts or writes.
 */
export function definitions(t) {
  const step = (id, title, description, extra = {}) => ({id, target: `[data-tour="${id}"]`, title, description, ...extra});
  return {
    home: {version: 1, steps: [
      step('home-mission', t('ModuLearn'), t('Learning activities, teaching tools, and research workflows share one platform.')),
      step('home-actions', t('Your next step'), t('Sign in to use your own workspace. When signed in, your account determines the dashboard you see.')),
      step('home-about', t('Explore both perspectives'), t('The Info page explains learning, teaching, and research without requiring an account. Open its page guide to explore all three.')),
    ]},
    overview: {version: 1, steps: [
      step('info-learning', t('For learning'), t('Students open a course, attempt available activities, and review their progress. Optional practice can support them along the way.')),
      step('info-teaching', t('For teaching'), t('Instructors assemble activities into units, set grading and access rules, and review student work.')),
      step('info-research', t('For research'), t('Researchers configure conditions and branching, rehearse the participant experience, and export study records.')),
    ]},
    instructor: {version: 2, steps: [
      step('instructor-courses', t('Courses and studies'), t('Select a course session, study, or linked legacy course in the sidebar. Search narrows the list without changing your selection.')),
      step('instructor-structures', t('Create and import'), t('Create a teaching session or study here. The Import menu brings in existing content.')),
      step('instructor-panel', t('Session controls'), t('The selected item brings its configuration, people, activity records, and analytics into this panel.')),
      step('instructor-studies', t('Studies'), t('Studies have their own participant flow. Use Study Setup to manage conditions and preview what participants will see.')),
    ]},
    student: {version: 1, steps: [
      step('student-sessions', t('Your course sessions'), t('Each session keeps your course progress together. Expand a session to find its activities and recent work.')),
      step('student-open', t('Open Session'), t('Open your session to choose an available activity. Use the page guide there to learn about progress and prerequisites.'), {optional: true, details: true}),
    ]},
    course: {version: 1, steps: [
      step('course-progress', t('Your course progress'), t('Graded activities determine course progress when grading is configured. Practice is tracked separately; if nothing is marked graded, all eligible activities count.')),
      step('course-units', t('Units and activities'), t('Expand a unit to see its activities. A lock means its access conditions are not yet met, or its availability dates prevent access.')),
      step('course-activity', t('Choose an activity'), t('Stars identify graded activities. Completed activities turn green. Open an available activity when you are ready to work.'), {optional: true, details: true}),
    ]},
    configuration: {version: 1, steps: [
      step('config-units', t('Course structure explorer'), t('Select a unit to edit its activities. Use the add controls to build your course, and reorder content to set its sequence.')),
      step('config-tools', t('Configuration utilities'), t('These controls manage grading, timezone, unit imports, instructors, plugins, and exports.')),
      step('config-grades', t('Grades'), t('Choose which activities count toward grades here. Grade weighting controls how completed work contributes to the final grade.'), {modal: 'courseGradesModal'}),
      step('config-save', t('Save Configuration'), t('Save your own edits when ready. This guide only highlights controls; it never saves or changes your course.')),
      step('config-preview', t('Preview'), t('Review the course layout here. Use Activity Preview to test individual content, or Study Setup for a full participant rehearsal.')),
    ]},
    study: {version: 1, steps: [
      step('study-settings', t('Study Setup'), t('Set the study details and participant flow here. Changes to an active research protocol may be restricted.')),
      step('study-preview', t('Participant preview'), t('Choose a condition and start a fresh preview to rehearse the participant experience. Page guides are hidden inside participant sessions.')),
      step('study-data', t('Research Data'), t('Review participant analytics and export the recorded events here. Guide usage never becomes a student attempt or study event.')),
    ]},
  };
}
