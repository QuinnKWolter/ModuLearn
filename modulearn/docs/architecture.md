# Architecture and data ownership

Maintained against the repository on 2026-10-19. Start at [the documentation index](../README.md).

## Source map

| Area | Responsibility / entry points |
| --- | --- |
| `accounts/` | Custom User, login/signup/profile, KnowledgeTree linkage |
| `courses/` | Reusable course structure, sessions, enrollment, configuration, progress, recommendation management |
| `dashboard/` | Instructor/student dashboards, native analytics, legacy KT/MasteryGrids analytics |
| `recruitment/` | Studies, participant sessions, conditions and recruitment entry/credit |
| `lti/` | Inbound LMS launches, platform registrations and identity mappings; shared launch cache/outcome models |
| `modulearn/views_lti.py` | Outbound external-tool launches and signed outcome handling |
| `modulearn/views_proxy.py` | Allowlisted upstream proxy and provider response capture |
| `modulearn/core/` | Navigation, role snapshots, shared context |
| `modulearn/learning/services/` | Progress, provider adapters, access rules, plugins, recommendations, catalog |
| `modulearn/learning/selectors/` | Course/dashboard/analytics/timeline read models |
| `modulearn/integrations/` | External configuration and course-authoring helpers |
| `main/` | Public pages and interface translation catalogs |

Paths above are relative to the Django project (`modulearn/`). Keep Django app labels and public route names stable when reorganizing internals.

## Ownership and invariants

- `Course → Unit → Module` is the reusable, shared outline. Editing a session's configuration changes that course's shared structure, including order, visibility and locks.
- `CourseInstance` is one offering/section; `Enrollment` binds a user to that exact session. Never resolve an ambiguous callback to an arbitrary enrollment.
- `ModuleProgress` stores normalized progress (0–1), score (0–100), attempts, completion timestamps and state; `CourseProgress` stores the rollup. `ModuleProgressEvent` preserves the event ledger, including individual attempt scores and raw payloads. Access logs and form answers are separate records.
- Normal progress writes use `modulearn.learning.services.progress.apply_progress_snapshot()`. Selectors shape reads; templates should not reconstruct tracking semantics.
- `StaticRecommendationSet` belongs to a session. `RecommendationActivation`, `RecommendationProgress`, and `RecommendationEvent` isolate practice by enrollment and original problem. Recommendation-only modules never contribute course credit. See [recommendations](recommendation-package-format.md).
- Instructor testing enrollments use `is_instructor_preview`; their saved grades/practice must stay out of student rosters, analytics, research exports and external grade forwarding. An instructor enrolled as a student in another session retains normal student tracking there.
- `Study`, `StudyCondition`, `ParticipantSession`, `RecruitmentSource` and assignment slots govern research participation. Study-owned backing courses use the same delivery engine, with participant confinement and research edit locks.
- `LTIUserIdentity` and `LTIPlatformRegistration` handle inbound identity/trust. `LTILaunchCache` and `LTIOutcomeLog` bind outbound callbacks to launches. Keep the two LTI directions separate.

## Identity and roles

`User.is_instructor` is authoritative for instructor navigation and takes precedence over student and participant flags. Django group names and KT group membership do not choose the navbar dashboard. Automated KT/LTI synchronization must not demote existing instructors; metadata/password/profile updates use field-scoped saves to avoid overwriting concurrent Admin role edits.

`User.get_display_name()` prefers profile `full_name`, then first/last names, then username. Numeric-only name candidates are treated as identifiers. Stored external identity fields are not rewritten to repair display issues.

When Admin and the browser disagree, compare the exact Profile username and role first, then deployed revision, database mount, workers and proxy destination. Do not merge accounts or infer instructor access from an email/display name.

## UI boundaries

`templates/base.html` provides the full shell; `templates/content_base.html` provides embedded activity pages. Reuse shared includes and `static/css/design-system.css`. Home is role-aware; audience information belongs on Info. Embedded recommendation frames suppress duplicate application chrome. See [development](development.md) for localization and extension rules, and [courses](courses.md) for instructor workflows.
