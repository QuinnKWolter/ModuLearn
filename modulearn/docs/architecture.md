# Architecture

## Current shape

The live Django project is the `modulearn/` repository root. The external `modulearn-storage` directory is only used for persisted storage such as SQLite files.

The application keeps Django app labels stable for migration safety, but the internal source of truth is moving toward three domain packages:

- `modulearn.core`
- `modulearn.learning`
- `modulearn.integrations`

## Django apps

### `accounts`

- Custom `User` model
- Signup, login, logout, profile
- KnowledgeTree account linkage and password synchronization

### `courses`

- Native course structures: `Course`, `Unit`, `Module`
- Teaching sessions: `CourseInstance`
- Enrollment and invite codes
- Progress storage and launch flows
- LTI outcomes and Caliper endpoints tied to courses

### `dashboard`

- Student dashboard
- Instructor dashboard
- Native ModuLearn analytics
- Legacy MasteryGrids analytics
- KnowledgeTree helper/API views

### `lti`

- Inbound LMS-to-ModuLearn launch provider
- LTI 1.1 and 1.3 configuration/login/launch helpers
- Launch cache and outcome logging models

### `main`

- Marketing and static pages

## Internal domain packages

### `modulearn.core`

- `context_processors.py`: app-shell metadata, script-name awareness, primary navigation
- `navigation.py`: user-aware primary nav definitions

### `modulearn.learning`

- `services/progress.py`: canonical progress mutation logic, course rollups, event-ledger emission
- `selectors/dashboard.py`: student/instructor dashboard context shaping
- `selectors/courses.py`: course detail shaping
- `selectors/timelines.py`: event-ledger read models for students and instructors

### `modulearn.integrations`

- `config.py`: script-prefix and external-host helpers
- `course_authoring.py`: course-authoring URLs and redirect targets

## UI system

The UI is now organized around:

- `templates/base.html`: marketing + authenticated shell
- `templates/content_base.html`: embedded/iframe shell
- `static/css/design-system.css`: tokens, layout primitives, cards, forms, badges, tables, timeline styling
- `static/js/app-shell.js`: theme toggle and mobile nav

Shared reusable UI partials live under `templates/includes/`.

## Data flow

### Progress mutations

Progress updates should flow through `modulearn.learning.services.progress.apply_progress_snapshot()` so that:

- module progress stays normalized
- completion timestamps are durable
- reopen events are recorded when progress regresses
- `CourseProgress` rollups stay in sync
- `ModuleProgressEvent` entries are emitted consistently

### Timeline reads

Timeline UI reads should come from `modulearn.learning.selectors.timelines`, not from hand-built view logic.

## Compatibility boundaries

Public route names and route entry points remain stable. Thin Django views may delegate to new selectors and services, but templates, LMS configurations, invite workflows, and integration endpoints should keep working while internals are reorganized.
