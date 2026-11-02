# Courses, analytics and studies

For guided participant flow, study editing, timers, isolated previews and the remediation-study acceptance matrix, see [Study authoring and rehearsal](studies.md).

## Course configuration

Course structure is shared across its sessions; enrollments, grades and recommendation settings are session-specific. Units/modules support ordering, visibility, locks and access rules. Student course lists load collapsed. Server-side access checks enforce hidden/locked content even when a launch URL is copied directly.

Add Module is available in the structure sidebar and beside each unit's expand/collapse controls. Supported authoring choices include external links, files, forms/quizzes and Smart Learning Content. SLC metadata (including the displayed content-type label) is editable. The catalog supports cards/table views, search, sorting, full metadata, demos in separate windows and prospective filter counts. Zero-count options disable and available choices sort first. Per-user browser session storage retains filter/layout choices. Catalog selection fills the module form; save to create the module.

Configuration packs text controls into `structure_controls`, leaving CSRF/action/files as normal form fields. This prevents large courses exceeding Django's field-count limit without raising that limit globally. Save validation and writes remain atomic; preserve multipart handling and research locks.

The trash button beneath Order in Unit Details marks a unit for deletion, like the activity trash button. Undo is available until Save Configuration. Saving removes the unit, its remaining activities and their learner records across all sessions of the course. Activities moved out before saving survive. Dependent unlock rules and unit grading references are cleared, and course totals are recalculated. Courses locked for active research remain protected.

Unit and activity locks offer accessed/completed rules for the previous unit, previous activity, selected earlier unit, or selected earlier activity. Previous activity follows visible course order across unit boundaries and skips recommendation-only content; for a unit it means the last visible activity before that unit. Relative rules follow reordering. Explicit targets are validated against the submitted order to prevent forward or self-dependencies. Accessed means recorded access (for a unit, access to every visible course activity); completion uses the activity's configured completion rule and the unit's graded requirements. Pre-tests configured for First Submission therefore unlock a following unit after all required questions have a submission, irrespective of correctness; attempt scores remain unchanged. Full course exports remap selected-unit references on import. An individual unit export cannot include an external unit prerequisite: it imports locked with a warning until a new prerequisite is selected.

## Plugins

The registry and normalization helpers live in `modulearn.learning.services.course_plugins`. General course plugin settings use `Course.plugin_config`; **static recommendations are the session-scoped exception**, stored in `StaticRecommendationSet`. See [the recommendation guide](recommendation-package-format.md). Dynamic recommendation registry entries are not evidence of an implemented personalized ranking service.

Guided Sequence applies initial linear visibility/unlock defaults only on disabled→enabled transition. Subsequent normal saves do not overwrite instructor customization. The next-module control uses existing access evaluation.

Adaptive Branching uses `ModuleBranchRule` and durable `EnrollmentModuleUnlock` rows. Source events may match success/failure, score thresholds or completion, optionally scoped to study condition. Scores use 0–100; ordinary unscored viewing must not count as failure. Rules execute through the canonical progress service and `adaptive_branching.handle_progress_event()`. Course exports preserve normalized plugin config and branch rules; recommendation datasets are installed separately. Review the outstanding access-policy work in [development](development.md) before changing branch/denominator behavior.

## Analytics and logs

The native class-average grid opens details for one unit/type intersection. Search students, expand a student to see exercises, and select Raw for recorded history. Rows are built lazily; data queries are batched. Saved score, attempts, completion and class-average comparison are available. A null score means ungraded, distinct from 0%; attempts with zero progress are still Attempted.

Per-student and aggregate views share status semantics. Instructor testing and recommendation-only content stay out of student class aggregates. Legacy KT analytics is a separate data path. Recommendation research logs provide separate normal-course events, practice events and practice summaries with filtered CSV exports.

A launch, iframe load or saved state does not prove a successful submission. Diagnose reported missing credit with session, user, module, timestamp and actual attempt/provider payloads; do not infer lost grades from launch-only flags. Audit/repair commands are documented in [development](development.md).

## Research studies

ModuLearn research recruitment is Study-owned. A `Study` has a backing course session for module playback, but courses and ordinary course sessions no longer expose Prolific setup directly.

### Study setup

Instructors create and manage studies from:

```text
Instructor Dashboard -> Studies -> Create Study
```

Creating a study also creates a dedicated backing course/session with default modules:

- Consent
- Instructions
- Pretest
- Main Study Task placeholder
- Posttest
- Debrief

Those modules are edited from the study row's **Modules** button, which opens the normal course-structure editor for the backing study session.

### Prolific entry

Prolific settings live in the Instructor Dashboard **Studies** modal. A Prolific Study ID is not required to generate the ModuLearn URL; leave it blank until Prolific creates the study if needed.

The generated external study URL has this shape:

```text
https://<host>/r/study/<study_slug>/launch/?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

Paste that full URL into Prolific's **What is the URL of your study?** field. Prolific fills the placeholders when a participant launches the study.

Expected parameters:

- `PROLIFIC_PID`: Prolific participant id, stored as a string.
- `STUDY_ID`: Prolific study id, stored as a string and checked against the configured source when present.
- `SESSION_ID`: Prolific submission id, stored as a string and used as the idempotency key for resuming the same participant session.

All three values are validated as 24-character hexadecimal identifiers before ModuLearn provisions anything. URL parameters are identifiers, not secrets.

On accepted entry, ModuLearn:

- creates or resumes an anonymous participant `User`,
- creates or resumes the learner `Enrollment` in the Study's backing course session,
- creates or resumes a `ParticipantSession`,
- assigns the participant to one of the Study conditions,
- logs the entry attempt,
- signs the participant in,
- redirects directly to the participant's resume activity (consent first in a new study).

Anonymous participants are intentionally restricted. They are redirected away from profiles and dashboards, cannot browse the normal course hub, cannot enroll in other sessions, and can only resume assigned study sessions/modules.

### Conditions

Study conditions are configured on the Study, not on a course session. Current assignment strategies are:

- `random`: independent random assignment (default for new studies).
- `balanced`: assigns the least-filled condition first.
- `hash`: deterministic assignment from the participant id.
- `schedule`: claims preallocated `RecruitmentAssignmentSlot` rows.

Module unlock rules can still target participant conditions through the course-structure editor, but the condition comes from the Study-owned `ParticipantSession`.

### Completion

The Study modal shows the end-of-study credit URL:

```text
https://<host>/r/study/<study_id>/complete-current/
```

Legacy, non-guided studies can use that URL as their final credit link. Guided studies automatically complete after their last step and reject premature completion. The endpoint resolves the logged-in participant's Study session and redirects to Prolific with the configured completion code:

```text
https://app.prolific.com/submissions/complete?cc=<completion_code>
```

For Prolific credit to work end to end:

- the Study's Prolific source must have a completion code configured,
- the participant must enter through the generated Study launch URL,
- the participant finishes the guided flow, or clicks the legacy credit link while logged into the provisioned participant account.

The legacy `/r/prolific/<source_id>/` and `/r/complete-current/<course_instance_id>/` routes remain as compatibility fallbacks for older rows, but new UI should use Study routes only.

### SONA

SONA configuration is temporarily disabled in the instructor UI and rejected by the source-creation endpoint. Existing SONA model fields and services remain in place, but new SONA sources should not be created until the SONA flow is re-enabled.

### Local testing

Prefer the isolated **Study Setup & Preview** workflow described in [studies](studies.md). The legacy synthetic-link method below creates participant records in the target study and should only be used on a disposable study.

Use the generated Study launch URL and replace the placeholders with stable 24-character hex values, for example:

```text
?PROLIFIC_PID=aaaaaaaaaaaaaaaaaaaaaaaa&STUDY_ID=bbbbbbbbbbbbbbbbbbbbbbbb&SESSION_ID=cccccccccccccccccccccccc
```

For preview/simulation runs where Prolific gives you only one participant link, `PROLIFIC_PID` may also be a synthetic id beginning with `test`, `demo`, or `pilot`, for example:

```text
?PROLIFIC_PID=test-participant-01&STUDY_ID=bbbbbbbbbbbbbbbbbbbbbbbb&SESSION_ID=testsession01
```

Reusing the same `SESSION_ID` resumes the same `ParticipantSession`. To simulate a new participant, change both `PROLIFIC_PID` and `SESSION_ID`; keep `STUDY_ID` the same for the same Prolific study. Synthetic participant IDs skip remote Prolific submission verification even if `PROLIFIC_API_TOKEN` is configured.

## Unit packages, access dates, and completion grades

Course Configuration now exports a selected unit and imports a unit JSON as a **new unit**, preserving existing units and learner work. The standard format is `schema: "modulearn.unit.v2"` with a `unit` object and package-local module `ref` values. It includes module metadata, forms, embedded files, graded flags, schedules and local prerequisites/adaptive branches. Duplicate exercise titles remain distinct. An unresolved external prerequisite stays locked and produces a warning; cross-unit adaptive branches require reconfiguration. Learner data and recommendation assignments are never copied. Verified legacy `format: "modulearn.unit.v1", ready: true` URL packages are accepted by the UI too; the existing checksum-based CLI remains available for those older packages.

Unit **Opens at** and **Closes at** use the course timezone selected from the top-level clock control (the site timezone is the default). Changing timezone preserves existing instants; later schedule edits use the new zone. Ambiguous/nonexistent daylight-saving times are rejected. Opening is inclusive; closing is exclusive. Dates apply in addition to prerequisite rules, and dynamic module unlocks cannot bypass them. Instructor previews remain accessible. Dates restrict access, not historical evidence: already received scores and delayed provider callbacks are retained. Unit structure, dates, and graded flags belong to the course and therefore affect its sessions. Grade-weighting policies belong to an individual session.

Ordinary modules start **graded**. Configuration offers individual toggles, all graded/all practice, and a dynamically populated problem-type selector. Save configuration to apply bulk changes. Hidden modules/units and recommendation-only content do not count toward grades. Practice retains attempts, scores, completion and logs, with separate completion counts. Existing recommendation progress remains isolated.

The **Grade weighting** page previews active students only, excluding instructor testing. Preview edits never persist; **Save grading rules** recalculates saved course summaries in that session without changing exercise records or proactively sending grades to an external LMS. Subsequent supported grade callbacks use the saved policy.

- Default: completed visible graded exercises / all visible graded exercises.
- Unit-target mode: each nonempty unit contributes `min(completed / total / target_fraction, 1) × weight`, divided by the sum of those weights. A blank unit target inherits the current default. A zero-weight unit contributes no base credit, but its configured deductions still apply.
- Optional course points scale the base percentage; otherwise deductions are percentage points.
- A configurable missed-unit deduction applies to each unit with graded material but zero completions. Each unit can also have an incomplete-unit deduction unless **all** its graded exercises are completed. Deductions add and the result is clamped between zero and the maximum.
- When at least one visible ordinary activity is graded, practice-only/empty units incur no deductions. Visibility and grading changes recalculate all affected sessions.

For a five-point course with a 50% target in every unit: choose unit-target mode, set course points to `5`, default target to `50`, and set the missed-unit deduction as desired. For a single point deducted if either X or Y is incomplete, add one combined completion requirement selecting X and Y with a deduction of `1`. For independent penalties instead, use each unit's incomplete-unit deduction. Combined and individual deductions add together when both are configured.

Migration `0028` adds these fields and recalculates historical **course summaries** using completion-based grades. It does not overwrite exercise scores or logs. Include the migration, templates, JavaScript, CSS and translations in deployment; publish collected static assets as usual.


### Graded progress and analytics

A star marks activities that count toward completion. If **none of the visible ordinary activities** are marked graded, all visible ordinary activities count equally. Hidden and recommendation-only activities remain excluded. This fallback does not change module flags or exercise records. Migration `0029` refreshes cached summaries for courses affected by the fallback; it preserves session grading policies and does not send LMS grades.

Course/unit bars and analytics overall progress count completed eligible activities. Practice remains separately inspectable, including partial exercise progress, attempt scores and raw history. **Exercise progress and score are distinct**: providers can report partial completion separately from correctness; the course grade additionally applies the session's completion targets and deductions.

Analytics **Units** counts nonempty graded units meeting their configured completion target (100% in default module-completion mode). Last Active combines recorded access logs, interaction timestamps and progress records with evidence of work; enrolling alone is not activity. Resource colors are stable by activity type, including across graded/practice groups.

The interaction timeline starts collapsed. Its overview loads only after opening the Interaction Timeline tab; detailed events load on first expansion of an activity, scoped to that student and course session. The chart shows recorded progress/attempt signals and saved completion dates, with zoom, pan, reset, a type legend and clickable activity lines/list. It cannot reconstruct interactions that were never logged. Raw capture details remain available separately.


Configuration's **Grades** modal groups bulk graded/practice selections and the grade-weighting link. Save selections before opening weighting. Module star toggles use the same compact icon controls as visibility, locks and retries; labels expand on hover, keyboard focus, briefly after toggling, or while that module is open. Unit schedules live behind a clock toggle and appear side by side when populated. Migration `0030` adds the course timezone; course exports preserve it. Practice logging remains independent of these controls.

Generated classroom logins use `prefix-` followed by a two-character session code and four random, lowercase, ambiguity-reduced characters (for example `ns-k7m4wx`). The session code is stable across renames and cycles through its short namespace; every full username is still checked for case-insensitive uniqueness. Existing accounts are unchanged. Generation retains bounded server batches, displays a progress indicator, and reveals all confirmed credentials together when finished (or when interrupted, with the error warning). Copy feedback pulses the icon without changing its width and announces success for assistive technology.

### Activity terminology and quiz/form authoring

The interface calls individual learning items **Activities**. Internal `Module` model names, URLs, JSON fields, and provider/tracking identifiers stay unchanged for compatibility. Course titles and provider-supplied content retain their original wording.

The add-activity quiz/form builder includes compact question summaries, accessible field labels, move-up/down, duplication, collapse-all and an interactive student preview. Optional instructions/submission settings collapse separately. Empty prompts and choice questions with fewer than two distinct options are flagged before saving. Existing question types and submission/completion behavior are unchanged; this is not a new automatic answer-scoring engine.

Configuration shows yellow graded stars in both its structure sidebar and activity panel, synchronized with the grading toggle. Student listings use an outline star for unfinished graded activities, a yellow earned star on completed activities (including practice), softened completed cards and crossed-out titles. Completion state still comes from the existing progress records.


## Cupcake partial test progress

Free-coding `answerChecked` events with a complete, consistent boolean `testCasesResults` list now record an equal-weight test percentage (3/4 = 75%). The latest accepted attempt supplies the score; activity progress retains the best percentage. Completion still requires Cupcake's overall `isCorrect=true`. Hidden tests contribute their reported boolean results, never inferred output. Invalid/missing test arrays retain the previous overall pass/fail behavior. Recommendation practice uses the same adapter but remains separate from course credit. Completion-based course grades, unit bars and completion counts still require completed activities.

To reconcile historical **course activity** attempts, including ungraded classroom practice, run `python manage.py backfill_cupcake_partial_progress --sessions 42 43 --modules 3796 3797 3798 3799 3800` after verifying those IDs in the destination. Default mode is read-only PREVIEW. It prints each affected username/session/activity, before/after score and progress, changed attempt IDs, skipped records, and a plan SHA256. Progress values are fractions (0.75 = 75%). After a database-consistent backup, repeat with `--apply --expect-sha256 <preview-sha256>`; changed plans abort. Applications are atomic and audited; repeated runs are no-ops. Accepted attempt counts, completion flags/times, raw provider payloads, saved work and access timestamps are preserved. No provider submissions, recommendation activations or external LMS grade passbacks are replayed. This command does not backfill separate recommendation-practice records. Missing/mixed/malformed/contradictory evidence and mismatched attempt counters are skipped for manual review, not guessed. Existing scores/progress are never lowered during historical reconciliation. The existing `repair_cupcake_progress` command handles previously unprocessed events; this partial-score command only updates already accepted attempts.

## Reusable CS0401 pre/post assessments

The normalized legacy assessment package and provenance are in `courses/fixtures/legacy_cs0401/`. Use `build_legacy_assessment_course --output <directory>` to create a separate demo course and export its two unit packages; it never overwrites a course. `exports/legacy-cs0401/` contains the ready-to-import units and whole-course export. Students use ordinary ModuLearn enrollment, while the existing proxy supplies provider compatibility parameters. QuizJET/PCRS remain the external grading engines; the original archive does not include their graders or any pre/post survey instruments. See the package README for the exact logging scope and verification.
