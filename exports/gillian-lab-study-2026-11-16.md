# Gillian lab study — November 2026

Import `gillian-lab-study-2026-11-16.json` as a **study template**, not as a course or unit. It contains 8 units, 44 activities, 3 conditions, and 24 condition-specific failure connections. Recruitment is disabled and credit codes are blank. Existing courses and participant records are not changed by importing a new study.

## Sequence and mappings

Consent → baseline questionnaire → pre-test → learning session → post-session questionnaire → post-test → debrief.

- Pre-test, in order: Q09, Q10, Q13, Q14.
- Post-test, in order: M01, M02, H01, H02.

| Learning problem | Similar coding problem / worked example | Matched worked example |
| --- | --- | --- |
| Q11 | M03 | Q11 |
| Q12 | M04 | Q12 |
| M05 | M10 | M05 |
| Q15 | H03 | Q15 |
| Q16 | H04 | Q16 |
| H05 | H09 | H05 |
| H06 | H10 | H06 |
| H07 | H08 | H07 |

The repeated Q11/M03 and H06/H10 diagram rows are represented once. This November mapping supersedes the earlier Q09–Q16 learning-sequence draft. It also uses the diagram's four post-test items rather than the earlier preregistration's two randomized transfer items; researchers should reconcile that design change before recruitment.

## Participant behavior

1. A correct learning submission stays on its feedback. **Next** moves to the following learning problem.
2. An incorrect submission stays on its feedback. **Next** opens the assigned intervention: another coding problem, a similar worked example, or the original problem's worked example.
3. Additional practice requires one scored submission, correct or incorrect. Worked examples permit Next without requiring a scored answer. The participant decides when to leave.
4. **Next returns to the original problem for a retry**, as Quinn requested. A further incorrect submission repeats the intervention. A new submission made before Next updates the pending route; paired completion callbacks cannot override the submission's route.
5. Pre/post-test activities count as complete after a scored submission, regardless of correctness; Next advances in the specified order. The provider's own feedback is still displayed. This package does not impose blinded test feedback or prevent editing/resubmission.

The remediation library is excluded from the ordinary sequence. Participant titles are neutral. Preview shows the same content-only ModuLearn shell with a prominent Exit Preview button. Third-party content can still contain provider-owned controls/notices.

## Researcher controls

- Study Setup: **Wait for Next after activity feedback**, **Retry the original problem after remediation**, section time limits, and per-activity **Allow Next without a submission** (enabled only for worked examples in this template). Activity controls are collapsed by section.
- Flow Mapper: search connections, filter by condition, inspect a selected activity's connections, optionally show all connections, and edit source/target/trigger/threshold. Changes save atomically.
- Copy Connections Between Conditions adds separate rules sharing the existing activities; it does not clone their content. Choose the destination condition and change targets afterward. Duplicate Study copies the entire protocol. Export/import provides a portable full copy.
- Activity Preview sits at the top of each expanded activity. Its themed modal combines unsaved description, instructions, questions and continuation text using the participant templates. Form introductions also render Markdown.

## Timing and evidence

All sections are untimed by default. Each `study_transition` event records `from`, `to`, `reason`, `trigger_event_id`, `visit_started_at`, and `elapsed_seconds`. Duration includes time reviewing feedback and background/idle time; it is not an attention metric. Refresh keeps the visit start; a return to the original creates a new visit. Existing attempt scores, correctness, provider interactions and native form input summaries remain logged. Early abandonment may have launch/interaction evidence but no closing transition.

An explicit worked-example Next acknowledgment logs completion with source `participant_acknowledgement` and `meaning=finished_reviewing_not_assessed`; it does not invent an attempt, score, or correct answer. Download Events includes these payloads. Preview data is disposable and excluded from recruitment; Exit Preview deletes the rehearsal copy.

## Production steps

1. Deploy the code, run migrations (including `recruitment.0009_study_participant_pacing`), and publish collected static assets using the normal reload/deployment process.
2. Sign in as the researcher. Instructor Dashboard → Manage Studies → Create Study → Optional Template JSON. Upload the JSON beside this guide and create a **new** study.
3. Open Study Setup. Confirm the two pacing/retry options are checked. Leave section seconds at zero unless the research team specifies time limits.
4. Replace the four clearly marked draft activities: consent, baseline questionnaire, post-session questionnaire, and debrief. Approved final instruments/wording were not supplied. Check withdrawal/decline handling, response scales, and eligibility wording before recruiting.
5. Review the mapping above, repeated-failure policy, and provider feedback on tests. Preview all three conditions. Check wrong → feedback → Next → intervention → Next → original retry → correct → Next, plus pre/post-test order.
6. Verify the real provider scoring and saved responses in the HTTPS environment, then configure recruitment and completion codes. Do not enable recruitment while replacement markers remain.

Existing guided studies also acquire participant-paced Next by default with the migration; ordinary courses are unaffected. The setting can be changed before participant data exists. Duplicate data-bearing studies to revise their protocol.

## Verification scope

All 28 supplied Cupcake catalog records and 28 worked-example URLs returned HTTP 200 on November 16, 2026. Package tests import/re-export/re-import the JSON and exercise every learning/remediation/retry pair in all three conditions using canonical progress events. Additional tests cover waiting for Next, wrong pre-test submissions, untimed duration, section expiry, stale Next requests, safe Markdown, and atomic connection editing. HTTP availability and simulated routing do not certify every upstream grader or the study's scientific instruments.

Local live-browser verification passed Q11 incorrect (0/100) → feedback retained → Next → Q11 matched worked example → explanation interaction → Next → Q11 retry → correct (100/100) → feedback retained → Next → Q12. Database inspection confirmed both attempts, worked-example interactions, acknowledgment, and timed transitions. The original editor reopened with its starter text for the retry. This was a disposable preview, removed through Exit Preview. The combined recruitment/translation/targeted-configuration suite passed 88 tests; JavaScript syntax and migration consistency checks passed.

November 19 browser rehearsal: all three conditions passed real Q11 incorrect submission → Next → M03 coding practice / M03 similar example / Q11 matched example → Next → original retry → correct submission → Next → Q12. Example explanations were opened. A separate non-preview participant session matched the preview content and layout except for the reserved Exit Preview area. Provider-owned controls remain inside the embedded activities. Rehearsal data was disposable; this does not certify every upstream exercise or replace production verification. Study-only course status messages, dark background, orphan preview buttons and filtered mapper spacing were corrected during this pass.
