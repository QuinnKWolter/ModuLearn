# Course Instances, Sessions, Modules, and Access Control Analysis

Date: 2026-05-17
Repository scope: `modulearn/`

## 1. Scope and intent

This document maps the current system for:

- creating and importing reusable course structures
- creating course sessions (instances) from those structures
- managing module types inside units
- enforcing visibility and lock/unlock rules
- tracking progress, access, and timeline events across student and instructor workflows

It is intended to serve as a baseline for upcoming change requests.

## 2. Terminology mapping in this codebase

- Course structure: `Course` + `Unit` + `Module` (shared blueprint)
- Course session: `CourseInstance` (named `group_name`, shown as "session" in UI)
- Enrollment context: `Enrollment` (student in one course instance)
- Module state: `ModuleProgress` + `ModuleProgressEvent` + `ModuleAccessLog`

Important: configuration UI is opened from a specific `CourseInstance`, but most content controls are stored on `Unit` and `Module` at the course-structure level.

## 3. Primary source files

Core backend:

- `courses/models.py`
- `courses/views.py`
- `courses/urls.py`
- `courses/utils.py`
- `modulearn/learning/services/access_rules.py`
- `modulearn/learning/services/progress.py`
- `modulearn/learning/selectors/courses.py`
- `modulearn/learning/selectors/dashboard.py`
- `modulearn/learning/selectors/timelines.py`

LTI and tool-launch integration:

- `modulearn/views_lti.py` (outbound tool consumer)
- `lti/views.py` (inbound LMS provider flow)
- `lti/models.py`
- `lti/services.py`
- `lti/config.py`

Frontend templates and JS:

- `dashboard/templates/dashboard/instructor_dashboard.html`
- `dashboard/templates/dashboard/components/courses_section.html`
- `dashboard/templates/dashboard/components/session_management_section.html`
- `dashboard/templates/dashboard/components/session_accordion_item.html`
- `dashboard/templates/dashboard/components/modals.html`
- `static/js/dashboard/instructor-dashboard.js`
- `courses/templates/courses/course_configuration.html`
- `courses/templates/courses/course_detail.html`
- `courses/templates/courses/module_frame.html`
- `courses/templates/courses/module_form.html`
- `courses/templates/courses/module_resource.html`
- `static/js/courses/module-frame.js`
- `static/js/courses/create-semester-course.js`

## 4. Data model map (authoring, sessions, module delivery)

### 4.1 Course structure and session models

- `Course` (`courses/models.py:24`)
  - `id` (string PK), `title`, `description`
  - m2m instructors
  - `total_modules()` counts modules for the full course structure

- `CourseInstance` (`courses/models.py:37`)
  - FK `course`
  - `group_name` (session label), `active`, created timestamp
  - m2m instructors
  - optional Canvas/LTI context fields
  - unique together: `(course, group_name)`

- `Unit` (`courses/models.py:69`)
  - FK `course`
  - ordering and control fields: `order`, `is_visible`, `is_locked`, `unlock_rule`

- `Module` (`courses/models.py:94`)
  - FK `unit`
  - type and control fields: `module_type`, `order`, `is_visible`, `is_locked`, `unlock_rule`
  - content fields: `content_url`, `content_file`, `content_data`
  - integration metadata: `provider_id`, `supported_protocols`, `resource_link_id`
  - module types:
    - `imported`
    - `external_link`
    - `file`
    - `form`

### 4.2 Enrollment and progress models

- `Enrollment` (`courses/models.py:180`)
  - student in one `CourseInstance`
  - unique together: `(student, course_instance)`

- `ModuleProgress` (`courses/models.py:192`)
  - FK `enrollment`, `module`, `user`
  - normalized progress (`0.0-1.0`), score (`0-100`), completion, attempts, state payload
  - LTI passback fields on module-level record

- `CourseProgress` (`courses/models.py:416`)
  - one-to-one with `Enrollment`
  - rollups: overall progress, score, module counts, completion timestamp

- `ModuleProgressEvent` (`courses/models.py:665`)
  - event ledger for timeline/analytics
  - event types: `launch`, `progress`, `completion`, `outcome`, `reopened`

### 4.3 Module forms and access logs

- `ModuleForm`, `ModuleFormQuestion`, `ModuleFormSubmission`, `ModuleFormAnswer` (`courses/models.py:552+`)
  - supports form/survey modules directly in sequence
  - question types include likert, single/multiple choice, short/long answer

- `ModuleAccessLog` (`courses/models.py:630`)
  - logs access events used for analytics and unlock predicates
  - event types: `view`, `launch`, `download`, `form_submit`, `unlock_denied`

### 4.4 Auto-provisioning behavior

- Enrollment post-save signal (`courses/models.py:703`)
  - creates `CourseProgress`
  - creates one `ModuleProgress` row per course module for that enrollment

## 5. Access control and hide/lock rule engine

### 5.1 Rule storage format

- Stored in `Unit.unlock_rule` and `Module.unlock_rule` JSON fields.
- Builder helper (`modulearn/learning/services/access_rules.py:24`) writes:
  - `{ "mode": "all", "conditions": [ { "type": "...", "target_id": ... } ] }`
  - or `{}` for no rule.

### 5.2 Access evaluation order

Unit evaluation (`evaluate_unit_access`, `access_rules.py:82`):

1. hidden check (`is_visible`)
2. unlocked if `is_locked` is false
3. if locked, unlock via rule predicate

Module evaluation (`evaluate_module_access`, `access_rules.py:92`):

1. hidden check (`is_visible`)
2. inherit locked reason if unit itself blocked
3. unlocked if `is_locked` is false
4. if locked, unlock via module rule

Student access gate helper in views:

- `_user_can_access_module` (`courses/views.py:111`) uses enrollment + both evaluators.
- Instructors bypass lock/hide access checks.

### 5.3 Supported rule predicates in engine

Supported in `_condition_passes` (`access_rules.py:119+`):

- `module_accessed` / `resource_accessed`
- `module_completed` / `form_completed` / `survey_completed` / `quiz_completed`
- `unit_accessed`
- `unit_completed`
- `previous_unit_accessed`
- `previous_unit_completed`

UI currently exposes only a subset in `course_configuration.html`:

- no condition
- previous unit accessed/completed
- selected module accessed/completed

## 6. End-to-end flow map

### 6.1 Importing/creating reusable course structures

Path A: import JSON from instructor dashboard:

1. Modal in `dashboard/components/modals/import_json_modal.html`
2. JS posts `{ course_data }` to `courses:create_course` (`static/js/dashboard/instructor-dashboard.js:705`)
3. `create_course` view (`courses/views.py:350`) calls `create_course_from_json` (`courses/utils.py:65`)
4. Creates/updates:
   - `Course`
   - `Unit` rows from JSON units
   - `Module` rows as `module_type='imported'`

Path B: "semester course" import page:

1. `courses:create_semester_course` renders `create_semester_course.html`
2. JS fetches external export URL, then posts into `courses:create_course` (`static/js/courses/create-semester-course.js`)

### 6.2 Creating course sessions (instances)

Instructor dashboard "New Session" flow:

1. Click from `courses_section.html`
2. Modal `newSessionModal` in `dashboard/components/modals.html`
3. Live availability check via `courses:check_group_name`
4. POST to `courses:create_course_instance` with `group_name`
5. Backend creates `CourseInstance`, links instructor

### 6.3 Configuring visibility, locking, ordering, and adding modules

Entry point:

- `courses:course_configuration` (`courses/views.py:167`) for an instance.

Action `update_structure`:

- `_update_course_structure_controls` (`courses/views.py:199`)
- updates every unit/module:
  - title, description, order
  - `is_visible`, `is_locked`
  - `unlock_rule` via `build_unlock_rule`

Action `add_module`:

- `_create_custom_module` (`courses/views.py:234`)
- allowed manual types: `external_link`, `file`, `form`
- form modules also create `ModuleForm` + questions
- syncs progress rows for existing enrollments via `sync_module_progress_for_course`

### 6.4 Student course session view

Route:

- `courses:course_detail` (`courses/views.py:144`)
- context generated by `build_course_detail_context` (`selectors/courses.py:9`)

Behavior:

- hidden units/modules filtered out for students
- lock state computed per enrollment
- module status badges built from progress + access state
- module links disabled when locked

### 6.5 Module launch behavior by module type

Single route:

- `courses:launch_iframe_module` (`courses/views.py:373`)

Flow:

1. Permission and lock/hide check
2. `ModuleProgress.get_or_create_progress(...)`
3. Log launch (`ModuleAccessLog`, plus progress launch event for non-instructors)
4. Type dispatch:
   - `form` -> `module_form.html` + submit handling in `_handle_form_module`
   - `file` -> `module_resource.html` + download log
   - `external_link` -> `module_resource.html`
   - `imported` -> iframe flow in `module_frame.html`

Imported module iframe specifics:

- protocol selection from `supported_protocols` (`Module.select_launch_protocol`)
- URL transformations for specific tools in `launch_iframe_module`
- LTI tools route through `/lti/tool-launch/` (`reverse('lti_launch')`)
- non-LTI tools get session params appended (`grp`, `usr`, `sid`, `cid`)

### 6.6 Form module submission and completion

`_handle_form_module` (`courses/views.py:694`):

- validates required answers
- saves submission + answers
- calls `apply_progress_snapshot(... completion ...)`
- logs `ModuleAccessLog.EVENT_FORM_SUBMIT`
- redirects back to course detail

### 6.7 Progress updates and timeline events

SPLICE/postMessage path:

- `module_frame.js` listens for `SPLICE.reportScoreAndState`
- posts to `courses:update_module_progress/<module_id>/`
- backend `update_module_progress` updates module + course progress

Canonical mutation logic:

- `apply_progress_snapshot` (`learning/services/progress.py:109`)
- clamps values, sets completion timestamps, recomputes course rollups, emits events

### 6.8 Outbound LTI outcome path

- Launch endpoint: `/lti/tool-launch/` in `modulearn/views_lti.py`
- Launch context cached in `LTILaunchCache` with `module_id`, `user_id`, `course_instance_id`
- Outcome endpoint `/lti/outcome/` parses score, updates local `ModuleProgress`, optionally forwards to UM service

## 7. Frontend wiring summary

Instructor workspace:

- `instructor_dashboard.html` sets URL patterns in `data-*` attributes
- `static/js/dashboard/instructor-dashboard.js` drives:
  - create session modal
  - session-name availability checks
  - delete course confirmation
  - manage enrollment modal and bulk enrollment
  - JSON import
  - course-authoring auth bridge

Course configuration UI:

- `course_configuration.html`:
  - structure controls form (`action=update_structure`)
  - add-module form (`action=add_module`)
  - inline question builder for form modules

Student session UI:

- `course_detail.html`:
  - unit accordions
  - module open/locked rendering
  - visibility chips shown to instructors

Module run-time UI:

- `module_frame.html` + `module-frame.js`
  - iframe launch
  - blocked-iframe fallback notice
  - SPLICE state/progress bridge

## 8. Notable behavior constraints and risks

1. Session-specific screen, course-global writes
- `course_configuration` is opened for a single instance but writes to `Unit`/`Module` on `Course`.
- Effect: one instructor’s lock/hide/order edits affect all sessions of that course.

2. Progress update instance ambiguity
- `update_module_progress` identifies instance by first active enrollment for that course (`courses/views.py:1212+`), not by explicit instance in request.
- In multi-session enrollment scenarios, module progress may attach to the wrong instance.

3. Visibility changes do not immediately recompute all rollups
- Structure update flow does not batch-recompute `CourseProgress` after hide/show toggles.
- Rollup counts can remain stale until another progress mutation occurs.

4. "Create Semester Session" entrypoint requires `course_id` query to work
- Dashboard links to `courses:create_semester_course` without `course_id`, while page JS expects `courseExportUrl`.
- Current result is an immediate error state when opened without query data.

5. Lock rules in UI are narrower than engine capability
- Engine supports unit-based and additional completion predicates, but configuration UI only exposes selected-module and previous-unit options.

6. Unlock rule builder always emits single-condition `"mode": "all"`
- Data model supports richer combinations, but current UI/backend builder does not expose multi-condition or `mode="any"`.

7. Several views exist but are not routed in `courses/urls.py`
- `unenroll`, `duplicate_course_instance`, and `delete_course_instance` are defined but not reachable via URL patterns.

8. `create_enrollment_code` endpoint is routed but not used by current dashboard JS
- Primary instructor flow is bulk enrollment; invite-code creation UI is currently absent.

9. `create_course_from_json` merge strategy is title-based
- Existing units/modules are matched by `title`; stable external IDs are not used.
- Renames/restructure can produce stale or merged records.

10. Access checks depend on enrollment-scoped logs/progress
- Unlock logic is correctly enrollment-specific, but only if progress writes and access logs resolve to the same intended instance.

## 9. Test coverage snapshot

Relevant tests in `courses/tests.py` cover:

- enrollment signal creates `CourseProgress` and module rows
- completion timestamps and progress events
- hidden-module filtering in course context
- locked-module launch denial + denial logging
- form submission updates completion + logs access

Dashboard tests (`dashboard/tests.py`) are basic page/redirect checks and do not cover session creation or configuration controls.

## 10. Change-planning implications

Before implementing requested updates, key design decision points are:

1. Should hide/lock/order/module additions be per-course-instance or remain shared across all sessions?
2. Should module progress updates carry explicit `course_instance_id` to remove ambiguity?
3. Should lock-rule authoring support full predicate set and multi-condition logic?
4. Should invite-code creation remain API-only or be restored to active UI workflow?

Those decisions will define migration shape, API adjustments, and frontend refactors.
