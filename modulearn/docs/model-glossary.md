# Model Glossary

## Accounts

### `accounts.User`

Custom auth model with:

- role flags (`is_student`, `is_instructor`)
- display name (`full_name`)
- Canvas/LTI identifiers
- KnowledgeTree linkage fields
- course-authoring password storage

## Courses domain

### `courses.Course`

Reusable course structure.

### `courses.CourseInstance`

An active offering/session of a course, often tied to a semester or section.

### `courses.Unit`

A grouping of modules within a course.

### `courses.Module`

A launchable learning object. Supports native URLs, SPLICE state reporting, and LTI-related metadata.

### `courses.Enrollment`

A student-to-course-instance relationship.

### `courses.ModuleProgress`

Module-level learner progress and score state.

### `courses.CourseProgress`

Enrollment-level rollup of course progress and completion.

### `courses.ModuleProgressEvent`

Timeline/event-ledger record for launches, completions, outcomes, and reopen events.

### `courses.EnrollmentCode`

Invite/self-enrollment credential tied to a course instance and email address.

### `courses.StudentScore`

Legacy score storage for certain LTI/course outcome flows.

### `courses.CaliperEvent`

Raw Caliper analytics event storage.

## LTI domain

### `lti.LTILaunchCache`

Durable cache for outbound tool-consumer launches so outcome callbacks can be resolved back to local entities.

### `lti.LTIOutcomeLog`

Audit trail for outbound tool-consumer outcome callbacks.
