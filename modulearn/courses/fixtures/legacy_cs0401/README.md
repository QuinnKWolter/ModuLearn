# CS0401 legacy assessment package

Source: local `D:/pretest-2018-cs0401`, authored by Roya Hosseini / PAWS Lab. Inspected 2026-11-01.

`assessments.json` is the normalized inventory: two ordered units, ten questions each, provider URLs without learner/session identifiers, source hashes, and public prompt/code snapshots. `source/` preserves the seven supplied HTML documents for provenance only; they are never served or executed. Obsolete jQuery, CSS, fonts and logging scripts are not runtime dependencies.

## What is and is not included

Each test contains five QuizJET Java tracing questions and five PCRS Java coding questions (booleans, conditionals, arrays, nested loops, methods). Pre/post variants differ; they are not duplicates. The archive contains **no pre-survey or post-survey instruments**. The separately supplied Qualtrics surveys are now reconstructed in `surveys/`; see its README for complete content, consent differences, records, and reuse instructions.

The local archive is a navigation wrapper, not the question/grader source. This migration replaces its navigation, identity and records with ModuLearn. QuizJET and PCRS remain external question/grading engines. The snapshot is reference material, not an executable Java grading sandbox. QuizJET can generate values dynamically; each submitted code instance is logged. An offline/native grading migration would require the original question definitions and test harnesses.

## Reuse

Run `python manage.py build_legacy_assessment_course --output <directory>` with existing `RITEL_DEMO_Teacher` and `RITEL_DEMO_Student` accounts, or specify `--teacher` and `--student`. This creates a separate course; it refuses to overwrite an existing course and never changes credentials. Use `--course-id` for another independent copy.

The command exports `pretest-unit.json`, `posttest-unit.json`, and `course.json`. Import an individual unit with Course Configuration → Import Unit. Each question retains an independent activity and progress history. Unit instructions preserve the original guidance about ordering, revisiting mistakes and using no extra help. They replace the old Done-page instruction with automatic per-question saving. Unlike the old wrapper, opening the last question does not imply that earlier questions were submitted. These assessment activities use `completion_rule: "submission"`: one graded submission, correct or otherwise, completes an activity. Opening it never counts. Questions 2–10 are locked until the preceding activity is complete; retries remain enabled. Each unit starts independently. Scores, correctness and every submission remain distinct from completion. Portable prerequisite references are remapped when importing the unit.

## Identity and records

Users sign in to ModuLearn. Launches automatically supply provider-required compatibility parameters; none are stored as a hard-coded learner identity in the package. There are no calls to legacy `pretestServices/GetPastAttempts`, `ProcessAttempt`, or `aggregate2/TrackAction` from this wrapper. Existing upstream engines may themselves contact their legacy infrastructure.

QuizJET records answer text, the displayed code instance, correctness, attempt score and event timestamp. PCRS records submitted code/request data, raw score/max score, returned test details and event timestamp. Both retain attempts and best progress per enrollment/activity, plus ModuLearn launch/focus/blur events. Typed code means the code **submitted**, not a guaranteed keystroke-by-keystroke history or autosaved unsubmitted editor draft. Raw history is available through the existing instructor activity timeline and event exports. Additional completion events can accompany one submission; use the attempts counter and outcome payloads, not total event-row count, to count attempts.

Completion, grading and analytics use the existing provider adapters. No new schema or alternate logging store was introduced. The full provider engines still need network access and trusted CA certificates. PCRS requires session cookies: requests without retaining them can loop through login redirects; ModuLearn's proxy keeps those cookies isolated from its own session.

## Local verification

The dedicated local test server uses `.venv/legacy-assessment.sqlite3` on port 8787. Production and existing local courses are unchanged. `courses.test_legacy_assessments` checks both unit imports and wrong/correct answer histories for all twenty mapped activities, including code payloads, timestamps and refusal to overwrite a course. Browser submission verification is separate from these adapter tests.

Verified live on 2026-11-01: incorrect/correct QuizJET submissions in both pre/post modes; PCRS pre-test partial/full results 5/7 and 7/7; PCRS post-test partial/full results 7/8 and 8/8. Database inspection confirmed scores, answers, code payloads and timestamps. QuizJET assessment-mode response parsing was added because these pages intentionally omit visible Correct/Wrong labels and instead return a provider outcome iframe. 37 focused regression tests passed. The test account retains diagnostic attempts so instructors can inspect the history.

## Updating existing copies

The new `Module.completion_rule` model field defaults to `provider` for all existing activities. Migration `courses.0033_module_completion_rule` is required. In configuration, expand an activity and choose **Completion Rule → First Submission (Any Score)**. This changes completion, not correctness; do not use completion percentage as test accuracy. Recorded attempt events retain the current attempt score, while the progress record may retain a best score.

For the two previously imported CS0401 units, preview a targeted update:

    python manage.py configure_legacy_assessment_completion --instance-id <ID>

Then apply with `--apply --output <directory>`. It requires the original `legacy_assessment` metadata and exactly ten ordered questions per unit. It updates only these units, never replaces answers, and backfills incomplete activities only from existing QuizJET/PCRS submission evidence. It preserves scores, attempts, payloads, and original submission timestamps; an audit event records each completion repair. Content settings are course-level and therefore shared by that course's sessions. Re-running is idempotent. Export/import appends units: do not re-import over existing learner records to update them.

Submission recognition uses the existing provider attempt adapters (including QuizJET/QuizPET, PCRS, Cupcake checks, PCEX, SQL-KnoT, SPLICE grades and LTI outcomes). Native form/survey final submissions are explicit. Passive launch/focus/view messages do not satisfy this rule. Providers must emit a recognized submission/result before submission-based completion can be used. Raw provider output remains in the original event payload; no missing historical answer or keystroke data is fabricated.
