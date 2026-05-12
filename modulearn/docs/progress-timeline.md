# Progress And Timeline Model

## Core progress models

### `ModuleProgress`

Tracks one learner’s progress for one module inside one enrollment context.

Important fields:

- `progress`: normalized `0.0 - 1.0`
- `score`: normalized `0 - 100`
- `is_complete`
- `completed_at`
- `attempts`
- `success`
- `state_data`

### `CourseProgress`

Rolls up the enrollment-level view of course completion.

Important fields:

- `overall_progress`: displayed as a percentage
- `overall_score`: average score across course modules
- `modules_completed`
- `total_modules`
- `completed_at`

### `ModuleProgressEvent`

The event ledger for timeline views and instructor activity feeds.

Important fields:

- `module_progress`
- `user`
- `module`
- `course_instance`
- `event_type`
- `source`
- `progress`
- `score`
- `success`
- `payload`
- `created_at`

## Event types

- `launch`
- `progress`
- `completion`
- `outcome`
- `reopened`

## Mutation contract

Use `modulearn.learning.services.progress.apply_progress_snapshot()` for progress writes.

That function:

- clamps progress/score values
- sets `completed_at` the first time a module is completed
- emits `reopened` when a completed module becomes incomplete again
- recomputes `CourseProgress`
- triggers grade passback when configured
- records event-ledger entries

## Read models

Use `modulearn.learning.selectors.timelines` for timeline queries:

- `get_student_timeline()`
- `get_course_timeline_for_student()`
- `get_course_instance_recent_activity()`

These selectors return presentation-ready event dictionaries used by dashboards and course detail pages.
