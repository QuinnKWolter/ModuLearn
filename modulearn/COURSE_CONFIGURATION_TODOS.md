# Course Configuration TODOs

## Audit
- Existing course structure is `Course -> Unit -> Module`.
- Imported modules currently carry launch metadata but no type, order, visibility, lock, or authoring state.
- Student display is built by `modulearn.learning.selectors.courses.build_course_detail_context`.
- Student launches enter through `courses.views.launch_iframe_module`.
- Progress rows and progress events already exist, but a clean access log table is needed for unlock rules and class/student access reporting.

## Implementation TODOs
- [x] Add additive model fields for unit/module order, visibility, locking, and unlock-rule JSON.
- [x] Add custom module support for external links, uploaded files, and form/survey modules.
- [x] Add flexible form-builder models for questions, submissions, and answers.
- [x] Add module access logs with per-student and per-class indexes.
- [x] Add access-rule evaluation for module/unit accessed, completed, and previous-unit gates.
- [x] Filter hidden content and mark locked content in the student course view.
- [x] Block direct launch access to hidden/locked student modules.
- [x] Add instructor configuration UI for structure controls, unlock rules, and new modules.
- [x] Add student-facing rendering/submission for form modules and uploaded resources.
- [x] Add focused tests and run Django verification.
