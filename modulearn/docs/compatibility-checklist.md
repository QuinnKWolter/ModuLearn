# Compatibility Checklist

Use this checklist before shipping refactor work.

## Public routes

- Keep all existing route names stable.
- Preserve major page entry points under `accounts/`, `courses/`, `dashboard/`, `lti/`, and root `main/`.

## Role behavior

- Students still reach `dashboard:student_dashboard`.
- Instructors still reach `dashboard:instructor_dashboard`.
- Instructor-only actions remain permission-protected.

## Invite and enrollment behavior

- Invite-code self-enrollment still works with existing email/code flow.
- Enrollment creation still produces exactly one `Enrollment`, one `CourseProgress`, and one per-module progress set.

## Analytics and legacy surfaces

- `dashboard:modulearn_analytics_dashboard` remains available.
- `dashboard:legacy_dashboard` remains available.
- KnowledgeTree resource modal and group lookup still work.

## LTI and external tool behavior

- Inbound LMS launch/provider endpoints remain reachable.
- Outbound tool-consumer launch and outcome endpoints remain reachable.
- Grade/outcome passback remains wired.

## Proxy behavior

- Allowlisted hosts still proxy correctly.
- HTML rewriting still preserves supported legacy activity flows.
- Proxy routes still respect script-name prefixes.
