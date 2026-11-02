# Native CS0401 survey units

Captured with user-authorized dummy responses on 2026-11-01:
- Pre: https://pitt.co1.qualtrics.com/jfe/form/SV_bBiUs28oqC5pAnI
- Post: https://pitt.co1.qualtrics.com/jfe/form/SV_0SONxocJu2utGtM

`pre-survey.json` contains all 16 observed pages / 39 response fields (each matrix row counts separately). `post-survey.json` contains the introduction and six questions. Original wording, choice labels and codes, question IDs, export tags, required responses, multi-select and self-description options are preserved. Opening-page captures retain the source HTML for provenance. No runtime session tokens or respondent data are included in the unit packages.

## Native behavior

Each survey is one ungraded form activity. A dedicated paged renderer uses the existing form questions, submissions, answers and activity-history schema. No Qualtrics requests occur when taking the native copy. Next/Back saves answers and timestamps; reload resumes the last saved page. Changes that have not reached Next/Back are not autosaved. Final submission records a single completed attempt, with no correctness or numerical score. Records include source IDs/tags, option codes/labels, selected text-entry values, page/row order and timestamps. Instructors can inspect submissions and page events in the existing activity history and exports.

The observed random ordering of SR1/PCS and NC/LC/Trust sections is reproduced, and declared randomized matrix rows are shuffled once per participant/activity. Navigation boundaries remain attached to page positions. Without the owner's QSF export we cannot prove undisplayed branches or server-side scoring/recode settings; no aggregate psychological scores are invented. Formatting is native and responsive rather than a pixel-for-pixel copy of Qualtrics branding. Blank intermediate scale anchors retain their raw empty labels; the interface supplies accessible numeric positions.

**Intentional consent correction:** the live decline route still asks the six interest/confidence questions before ending. The native copy instead stops immediately on decline, retains only the consent decision, and does not award completion. A surrounding study's consent/withdrawal routing must still be configured separately.

## Consent document

`ConsentVolunteer2024.pdf` is an unchanged copy of the supplied three-page document, included inside the pre-survey unit export. Its displayed approval interval is April 26, 2024–April 25, 2025; it concerns Personalized Information Access, STUDY19040225. Researchers must provide the appropriate current document before recruitment. This is not automatically consent for the separate Python remediation experiment. The copied anonymity statement is original wording: native records remain associated with the ModuLearn enrollment and are not automatically anonymized at storage time.

## Install / reuse

With an existing testing course session:

    python manage.py build_legacy_survey_units --instance-id <ID> --output <directory>

This appends two units without replacing existing content or responses and refuses to run twice on a course containing these surveys. It exports `pre-survey-unit.json`, `post-survey-unit.json` (including the PDF), and a refreshed `course.json`. Import individual packages through Course Configure → Import Unit. Deploy the native survey renderer before importing. All response fields also exist as standard form questions; the advanced page layout and source-code mappings live in `content_data.survey`. Do not reorder/delete questions through the ordinary flat form editor without updating those mappings. A general visual survey-layout editor is not included.

## Verification

`courses.test_surveys` verifies complete submissions, required and invalid responses, stale-page protection, resume/back, decline without completion, no numerical score, no duplicate submission, export/import of both surveys and the PDF, and refusal to overwrite. Local Playwright completed both surveys as the demo teacher (16 and 7 pages), with desktop/mobile matrix rendering and no JavaScript exceptions. RITEL_DEMO_Student has no submitted survey responses and is ready for manual testing.

Dummy Qualtrics runs were authorized. The query marker was `test_run=MODULEARN_COPY_TEST_20261101`; any free text was marked `MODULEARN_COPY_TEST_20261101`. Qualtrics may not persist the query parameter, and some runs contained no free text. Do not assume all dummy responses are identifiable by that marker alone. The separate local run notes list captured session identifiers and the extra partial/earlier test runs for the survey owner to review.
