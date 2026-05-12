# Page Inventory

## Marketing pages

- `main:home` -> `main/templates/main/home.html`
- `main:about` -> `main/templates/main/about.html`
- `main:contact` -> `main/templates/main/contact.html`
- `404` -> `templates/404.html`
- `500` -> `templates/500.html`

## Auth and account pages

- `accounts:login` -> `accounts/templates/accounts/login.html`
- `accounts:signup` -> `accounts/templates/accounts/signup.html`
- `accounts:profile` -> `accounts/templates/accounts/profile.html`
- `registration/login.html` -> compatibility wrapper around the shared login template

## Learning pages

- `courses:course_list` -> legacy redirect to role-specific dashboards
- `courses:course_detail` -> session detail and unit/module list
- `courses:module_detail` -> compatibility redirect to the embedded launch wrapper
- `courses:launch_iframe_module` -> embedded launch wrapper
- `courses:preview_iframe_module` -> instructor preview wrapper
- `courses:enroll_with_code` -> invite/self-enrollment flow
- `courses:create_semester_course` -> semester/session creation flow

## Dashboard pages

- `dashboard:student_dashboard` -> learner home and timeline
- `dashboard:instructor_dashboard` -> instructor control surface
- `dashboard:modulearn_analytics_dashboard` -> native analytics
- `dashboard:legacy_dashboard` -> MasteryGrids / KnowledgeTree analytics

## Integration and utility pages

- `lti:launch` -> inbound LMS launch
- `lti:login` -> LTI 1.3 login
- `lti:config` -> LMS XML config
- `lti_launch` -> outbound tool-consumer auto-submit page
- `lti_outcome` -> outbound tool outcome callback

## Role workflows

### Student workflow

1. Land on `dashboard:student_dashboard`
2. Open a session from the student dashboard
3. Launch a module from `courses:course_detail` or an existing `courses:module_detail` compatibility link
4. Accumulate progress, score, and timeline events
5. Review completion history on dashboard or course detail timeline panels

### Instructor workflow

1. Land on `dashboard:instructor_dashboard`
2. Import or create course structures
3. Create course sessions
4. Manage enrollments or create invite codes
5. Open native analytics or legacy analytics as needed

### Legacy workflow

1. Open `dashboard:legacy_dashboard`
2. Select or auto-populate a KnowledgeTree group and course
3. Review MasteryGrids data
4. Open KnowledgeTree resources via the shared course-resources modal

## Partial templates worth reusing

- `templates/includes/page_header.html`
- `templates/includes/timeline_panel.html`
- `templates/includes/app_nav.html`
- `templates/includes/app_footer.html`
- `dashboard/templates/dashboard/components/*`

When adding a page, prefer these shared partials before creating new one-off template fragments.
