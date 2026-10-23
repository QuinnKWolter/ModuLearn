# Testing and provider acceptance

## Automated checks

From the Django project with dependencies and a test-safe environment configured:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Tests use a disposable database; configure or block external integrations rather than relying on live student accounts. Focused suites include `courses.test_configuration_submission`, `courses.test_static_recommendations`, `courses.test_recommendation_package`, `courses.test_recommendation_practice`, `courses.test_cupcake_tracking`, `dashboard.test_analytics_drilldown`, `dashboard.test_direct_database`, `lti.test_outcome_security`, and `lti.test_platform_defaults`. Run the owning app's tests as scope warrants.

Anonymous roster creation: run `node --test tests/js/anonymous-roster.test.cjs` for sequential batches, interrupted responses, credential retention and duplicate-submit protection. `courses.tests.CourseProgressTests.test_anonymous_roster_batches_initialize_full_course_progress` verifies successive batches against a 300-module course. The dashboard sends five accounts per request because password hashing plus progress initialization for a whole roster can exceed the production worker timeout. Successful batches remain committed if a later batch fails; inspect the refreshed roster before requesting the remainder. Do not automatically retry an unanswered request, which may already have committed. A local 100-account/300-module benchmark took 33.74 seconds on 2026-10-23; production timeout diagnosis still requires its worker logs.

Recent local checks (2026-10-19): 45 recommendation tests plus browser checks for the unified modal-to-sidebar flow, return-on-collapse, persisted completion, feedback, Spanish/mobile, Escape/focus and reduced motion; viewport checks with tall fixture content and verified-source resize messages at desktop, mobile and landscape sizes; 13 analytics tests plus lazy expansion/history/search browser checks; 100 account/direct-database/LTI cleanup tests. These are scoped historical results, not a claim that the full current suite or production has just passed. Controlled UI progress submissions do not certify real provider grading.

Grading/unit configuration checks (2026-10-23): `courses.test_grading_units` covers completion policies, points, individual and combined deductions, preview/save isolation, instructor exclusion, schedules, bulk summaries and portable unit imports (duplicate titles, files/forms, local and external prerequisites). The broader 101-test course/configuration/analytics run and 58-test provider/progress/recommendation/LTI run passed. Chromium checks verified live previews, saved policies, combined requirements, mobile width, Spanish, bulk grading toggles, and unit export/import through the interface. These checks used isolated local fixtures, not production students.

## Integration lab access

The testing interface is direct-URL only: `/courses/instance/SESSION_ID/integration-testing/` (prepend `/modulearn` in production). It requires that session's instructor membership and exposes only the signed-in instructor's test evidence; ordinary students and other instructors are denied. It is not linked in navigation. Opening diagnostics does not award credit.

Local catalog lab was session 26; the user-created production lab was session 44. Verify the session in your environment rather than recreating it. Local SQL fixture `courses/fixtures/temple_sql_course.json` contains 8 units/118 placements; its public inventory is [SQL inventory](sql-course-inventory-2026-10-17.csv). Representative SQL-KnoT, AnnEx and DBQA interactions saved local grades/completion; SQL-TUTOR remained blocked by `ERROR_SCODE_INVALID`, with no alternative catalog protocol found. Query Examples are optional for the requested SQL acceptance scope.

## Inventory and evidence

The 2026-10-17 inventory contained **4,097 records, 16 providers, 12 content types, and 40 provider/type/protocol combinations**. **31 combinations had verified local completion** (two through documented QuizPET alternatives); six have upstream/setup blockers, two have only broken catalog records, and one has an undeclared protocol. These are representative integration tests, not an assertion that all 4,097 individual exercises work.

- [Representative coverage matrix](catalog-testing-2026-10-17/coverage.csv), dated 2026-10-17. It contains public activity URLs and local test IDs, not production identities. Raw catalog/evidence JSON snapshots were removed during documentation consolidation; generate a new inventory for fresh tests.

| Provider | Content types | Findings |
| --- | --- | --- |
| AnnEx | BehaviorExample; CodeConstruction | Real annotation interactions complete and save progress. |
| CodeCheck | FreeCodingProblems | SPLICE Java submission saves 100%; selected LTI resource returns Resource not found. |
| CodeWorkout | FreeCodingProblems | Signed launch reaches provider; course offering unavailable. |
| CTAT | Question | Sole catalog record marked broken; no working representative claimed. |
| Cupcake | CodeCompletionProblem; CodeConstruction; FreeCodingProblems; PredictingFinalResult | HTML and SPLICE representatives completed. Graded problems save scores; worked examples save reading completion without inventing a score. |
| DBQA | CodeVisualization | Signed launch renders; query-step adapter saves completion locally. Real server-side LTI outcome still requires HTTPS testing. |
| JSVEE | CodeVisualization | Final animation step saves completion. Legacy PITT delivery uses supported HTML/SPLICE conversion. |
| PCEX | CodeCompletionProblem; CodeConstruction; CodeConstruction&CompletionBundle | Worked examples and correctly submitted challenges save 100% across HTML/PITT/SPLICE. Bundle evidence covers selected worked example, not every bundled challenge. |
| PCRS | FreeCodingProblems | Wrong and correct Python submissions recorded, then 100% completion, for HTML/PITT. UNKNOWN-protocol records are not guessed. |
| QuizJET | PredictingFinalResult | HTML/PITT submissions save 100% completion. |
| QuizPET | PredictingFinalResult | Original Variables4 examples return upstream HTTP 500. Alternative nested-loop exercise completes and saves 100% for HTML/PITT, including instructor testing. |
| ReadingMirror | ReadingMirror | Catalog records marked broken; no working representative claimed. |
| SQL-KnoT | FreeCodingProblems | Submitted SQL query saves 100% completion. |
| WebEx | BehaviorExample | Selected legacy HTML/PITT endpoints time out; completion unverified. |
| jsParsons | ParsonsProblem | Real correctly ordered/indented solution saves 100%; legacy route converted to supported ACOS transport. |
| OpenDSA | OpenDSA Problem; OpenDSA Slideshow | Origin-only Referer fixes provider URI error. Separate window reaches provider, which requires instructor initialization before learner access. Grade callback unverified. |

HTML is a delivery method, not a generic grading contract. Provider adapters or SPLICE messages supply grades/events where available. LTI 1.1 Basic Outcomes provides a score; it does **not** supply every keystroke, submission body, or intermediate event. Diagnostics never infer lost work solely from a launch without a score. Browser transport conversions do not establish native support for every legacy PITT variant.

## What to provide when production is ready

1. The deployed revision and public HTTPS base URL (expected `https://adapt2.sis.pitt.edu/modulearn/`).
2. A separate integration test session ID and instructor/student test access. Do not use Bita's live class as the integration lab. Local session 26 is not assumed to exist in production.
3. Confirmation that provider keys/secrets are installed in the webapp environment. The supplied credentials are reused locally in ignored `.venv/catalog-testing/lti-local.env`; this file is not a deployment artifact. Configure server secrets privately, never paste them into reports.
4. For OpenDSA, initialize/register the test exercises with its provider-side instructor workflow. Current ModuLearn test launches deliberately use Learner role to test the student activity path; do not globally change learner roles to bypass setup.
5. For CodeWorkout, provide a valid offering/term for this registration. Optional `CODEWORKOUT_COURSENAME`, `CODEWORKOUT_COURSENUMBER`, `CODEWORKOUT_COURSELABEL`, `CODEWORKOUT_COURSETERM` replace the old consumer's legacy defaults. For CodeCheck LTI, obtain a currently valid LTI resource URL; its SPLICE alternative works.

## Production preparation, in order

Deploy using [the deployment guide](deployment-adapt2.md), including migration `courses.0027_instructor_testing_enrollment` and collected static assets. Restart/recreate the webapp after environment changes. No database reset, container-volume deletion, progress repair, or `docker-compose down` is required for this test.

The relevant direct-tool environment variable families are:

| Tool | Required credentials | Optional endpoint override |
| --- | --- | --- |
| CodeCheck | `CODECHECK_KEY`, `CODECHECK_SECRET` | `CODECHECK_LAUNCH` |
| CodeWorkout | `CODEWORKOUT_KEY`, `CODEWORKOUT_SECRET` | `CODEWORKOUT_LAUNCH` |
| DBQA | `DBQA_KEY`, `DBQA_SECRET` | `DBQA_LAUNCH` |
| OpenDSA problems | `OPENDSA_PROBLEMS_KEY`, `OPENDSA_PROBLEMS_SECRET` | `OPENDSA_PROBLEMS_LAUNCH` |
| OpenDSA slideshows | `OPENDSA_SLIDESHOWS_KEY`, `OPENDSA_SLIDESHOWS_SECRET` | `OPENDSA_SLIDESHOWS_LAUNCH` |
| CTAT | `CTAT_KEY`, `CTAT_SECRET` | `CTAT_LAUNCH` |
| CodeLab / CodeOcean | `CODELAB_KEY`, `CODELAB_SECRET` / `CODEOCEAN_KEY`, `CODEOCEAN_SECRET` | corresponding `_LAUNCH` |

CodeLab and CodeOcean are available configurations, not additional verified catalog providers. The old ACOS Heroku LTI registration has not been added as a verified direct tool; current jsParsons works through its ACOS catalog delivery. Do not copy the old Node consumer's hardcoded callback URLs or dated course context into the new deployment. Direct registrations take precedence over imported `paws_` launch aliases when their keys are configured. `LTI_FORWARD_TO_UM` controls optional legacy UM forwarding independently of local grade saving; leave production's intended setting explicit.

Ensure the reverse proxy passes the correct public Host and `X-Forwarded-Proto: https`, strips untrusted forwarded headers, and preserves `/modulearn`. The diagnostic page must show exactly:

`https://adapt2.sis.pitt.edu/modulearn/lti/outcome/`

This POST endpoint must be reachable by provider servers without browser login, VPN, or an interactive challenge. It authenticates the OAuth signature and XML body hash. A GET returning HTTP 405 is expected and does not test a callback. The launch endpoint remains authenticated. Keep system clocks synchronized. Launch contexts currently expire after 24 hours: start a fresh launch before testing a delayed callback.

After deployment, check migrations before creating the lab:

```bash
sudo docker exec modulearn__webapp bash -c 'cd /modulearn && python manage.py showmigrations courses'
```

If no lab exists yet, with the two demo accounts already present, create a **new isolated course** and export its live catalog inventory to persistent media:

```bash
sudo docker exec modulearn__webapp bash -c 'cd /modulearn && python manage.py build_catalog_testing_course --create --course-id slc-integration-lab-https --teacher RITEL_DEMO_Teacher --student RITEL_DEMO_Student --output /modulearn/media/integration-testing'
```

This command intentionally refuses to replace an existing course ID. Record the new session ID printed at the end. The catalog is queried afresh, so selected records can differ from the local snapshot. The inventory contains public catalog metadata, not credentials. Do not put student evidence exports in public media.

## Joint HTTPS test procedure

1. Sign in as the instructor and open `/modulearn/courses/instance/SESSION_ID/integration-testing/`. Confirm HTTPS callback URL and empty test evidence for a fresh lab.
2. Launch a working registered LTI activity from this page. For tools refusing iframe embedding, use **Open In A New Window**. Complete an actual answer. Record provider, activity, account and timestamp.
3. Return and refresh. Confirm a cached LTI launch, an accepted outcome, the expected normalized score (callback scale 0–1; course score scale 0–100), and saved module progress. A browser completion message alone is insufficient. DBQA's local step adapter can save progress without a server-side outcome; inspect both columns.
4. Download the instructor evidence JSON. It excludes OAuth parameters, secrets, raw payloads and session/source IDs. It contains only that instructor's records. Outcome association relies on the launch cache; collect it before expired launch contexts are purged.
5. Repeat with the student account. Inspect that student in the existing instructor progress/log interfaces; students cannot open integration diagnostics. Confirm instructor test results are absent from student analytics and recent student activity.
6. Test a wrong answer followed by a correct answer, reopen the activity to verify persistence, and retry a recommendation separately where configured. Recommendation practice must not alter course credit. Use a lab with recommendations for this check; the fresh catalog lab does not manufacture a recommendation dataset.
7. If no callback arrives, provide the instructor JSON plus a short server log window around the timestamp. Review logs before sharing: old logging paths may contain identifiers/launch parameters. Do not reset progress or ask students to redo coursework merely because a callback is missing.

```bash
sudo docker logs --since 10m modulearn__webapp 2>&1 | grep -E 'LTI Outcome|LTI Launch|ERROR' | tail -100
```

## Local verification boundary

Automated tests cover authenticated resource-bound launches, signed outcomes, tampered/unsigned rejection, finite score validation, identical signed retry idempotence, exact session isolation, and instructor diagnostics authorization/redaction. A 139-test regression run passed; a subsequent 60-test focused run passed after the diagnostics percentage display and OpenDSA compatibility changes.

Real browser tests verify provider interactions and persisted local progress as recorded in the matrix. A real provider-originated server-to-server LTI grade callback remains **pending public HTTPS**, by design; localhost cannot establish it. No claim of complete catalog support is made for broken catalog records, unavailable upstream services, provider registrations awaiting setup, or untested internal provider events.

OpenDSA compatibility reference: its [current controller](https://github.com/OpenDSA/OpenDSA-LTI/blob/master/app/controllers/lti_controller.rb) identifies the LMS from `request.referrer`; the launch response now permits origin-only disclosure for that provider. Other launches retain the existing referrer policy.

## Graded completion and analytics checks

`courses.test_grading_units` and `dashboard.test_analytics_drilldown` cover mixed graded/practice courses, the no-graded fallback, unit targets, completion versus scores, bounded grade recalculation queries, Last Active evidence, lazy interaction detail and access restrictions.

Before production acceptance, check a mixed course and an all-ungraded course: stars and course/unit totals should agree; practice details should remain inspectable. Open a class-average cell and expand a student. In the individual Interaction Timeline, confirm units/activities begin collapsed, chart zoom/pan/reset work, and selecting an activity reveals its history. The chart requires historical progress signals or saved completion timestamps; it does not fabricate missing history. Apply migration `0029` and publish the new `analytics-timeline.js` with collected static assets.
