# Study authoring, rehearsal, and participant flow

Requirement and acceptance map for Gillian's October 19–27 email chain and the remediation-study preregistration supplied October 28, 2026. Platform features are separate from unpublished content and experimental decisions.

## Requirements and resolution conditions

| Request | Code / implementation | Resolution condition |
| --- | --- | --- |
| Edit study details | Researcher-only `/r/study/<id>/setup/`, `recruitment/studio.py` | Title, description, version and protocol notes save atomically before participant entry. Duplicate a data-bearing study to revise its protocol. |
| Edit conditions | Same editor; stable `StudyCondition` records | Edit names, descriptions, IDs and active status. Renaming IDs updates branch/condition-unlock references. Recruitment settings no longer recreate conditions. |
| Delete units / undo changes | Confirmed deletion, Discard Changes, template export/import | Reject external unlock dependencies; cascade associated branch rules. Discard resets unsaved fields. Saved deletion is not undoable: export first. |
| Participant-perspective preview | Disposable study clone and actual temporary participant identity | No instructor bypass. Original participants/counts/data unchanged. Exit restores the researcher and deletes rehearsal data. |
| Straight to consent | Entry → resume → first visible main activity | Approved consent is first; no dashboard or course chooser intervenes. |
| Remove Back to Course / distractions | Guided player, form shell and central access policy | No course navbar, ordinary recommendations or arbitrary Next Activity. Copied activity URLs cannot skip the current step. |
| Correctness-driven routing | Provider adapters → canonical progress events → Adaptive Branching → study cursor | Cupcake scored attempts now reach branching. Incorrect → first matching condition rule → remediation → original. Correct → matching success rule or next main activity. Never infer correctness from visible output. |
| Three intervention conditions | Failure rules scoped to practice/similar/matched | Same main sequence; only assigned remediation. Practice returns after one scored submission, examples after reported completion. Further original mistakes repeat intervention; researchers must confirm that policy. |
| Scroll content editor | Activity Builder flex-body/textarea overflow | Long modal bodies and textareas scroll within viewport. |
| Markdown / rich text | `study_text.study_markdown`, form renderer | Bold, italic, inline/fenced code, headings, bullets. Raw HTML escaped. Deliberately limited Markdown, not arbitrary HTML or a full rich-text editor. |
| Timed sections | `Unit.time_limit_seconds`, persisted `ParticipantSession.flow_state` deadlines | Starts on first launch, survives refresh, continues through remediation. Expiry advances sections without fabricated completion/grades; late grade-changing events are rejected and logged separately. |
| Duplicate Flow Mapper schema | Copy rules across conditions; Duplicate Study | Existing rules retained; full clones remap activities and preserve forms/conditions/timers. Clone recruitment disabled and credit codes cleared. |
| Reusable JSON and usable UI | Export Template / existing study import + Study Setup | Configuration round trips without participant data. JSON is optional, not the sole authoring interface. |
| Individual random assignment | New independent `random` strategy | New studies default to cryptographic independent choice, persisted at entry. Existing balanced/hash/schedule configurations unchanged. Balanced counter is not random. |
| Eight main questions / twelve practice candidates | Researcher selection + catalog/Flow Mapper | Supply final eight, mappings and delivery URLs. Rehearsal Q01/Q09 are illustrative, not final selections. |
| Publish Cupcake Python / WEAT materials | Provider/catalog authors, then catalog import | Real URLs must be pilot-tested for wrong/correct answers, restoration and example completion. Unpublished YAML/WEAT files and URLs were not supplied. |
| Static vs AI feedback | Research decision | Retain static/provider feedback unless an AI-feedback design is explicitly approved. Not silently implemented. |
| Baseline confidence, interest, experience, pretest | Native forms or approved Smart Content | Insert approved wording from missing `indices.docx`; placeholders are not final instruments. |
| Post-session distraction, interest, confidence, judgments, expected test/average scores, confidence in estimates | Native forms | Use explicit 0–10 choices for second-order judgments. Existing five-point Likert is not a substitute. Approved wording remains required. |
| Two short-answer transfer questions, randomized order | Per-form Shuffle Questions option | Stable per-enrollment shuffled order across reloads; saved responses. Final questions and `rubric.docx` required. Form completion/100 is not rubric-scored programming performance. |
| Incorrect-attempt covariate and learning trajectories | Study analytics + streamed event CSV | Incorrect scored attempts per activity/participant, distinct activities with errors, chronological scores/correctness/conditions. Views are not failures. |
| Instruction time and idle adjustment | Launch/focus/blur/provider events and transitions | Raw timing evidence exported. Deadline is elapsed time, not attention. Winsorization and regression remain researchers' analysis, not silent log transformations. |
| Copy/paste and keystroke evidence | Native-form input summaries + existing provider telemetry | Cumulative per-visit counts and response lengths; no clipboard contents or unrelated typing. Use latest snapshot per visit ID, not sum of cumulative snapshots. External frames expose only provider-supported events. |
| Exclusions / outside assistance | Researcher review | Input evidence is not proof of cheating. No automatic accusation or exclusion. Incomplete runs retained. |
| Prolific: US adults, $6, ~30 minutes, 300 qualifying completers | Prolific setup and researcher monitoring | Configure age/location/payment in Prolific. Entry cap is not a count of qualifying completers. Researchers apply inclusion criteria and stop at the registered target. |
| Treatment blinding | Participant UI omits condition labels | Participant and preview screens show only authored content; previews add a fixed Exit Preview button. Diagnostic simulation and trace endpoints remain restricted to isolated previews. Avoid condition-revealing activity titles in final materials. |
| Pilot readiness | Reusable rehearsal command + real-provider verification | Test all three conditions, correct/incorrect, return, refresh, timers, exports and recruitment completion. Simulation does not certify upstream scoring. |

## Researcher workflow

1. Instructor Dashboard → Manage Studies → **Study Setup & Preview**. Existing studies remain unchanged until guided flow is enabled; duplicate studies with data to revise them.
2. Edit details/conditions/assignment. Open **Activities & Flow Mapper**. Put consent first, then baseline, learning, questionnaire, test and debrief. Import published activities from the catalog.
3. Add one failure rule per condition for each main question. Lowest priority number wins. Failure/score-below targets are omitted from the main sequence, even when a rule is disabled. Remediation returns automatically; do not add another failure rule to return.
4. Guided flow owns navigation instead of ordinary completion locks/calendar schedules. Visibility and condition-equals filters apply. Use section timers for study duration limits.
5. Set section seconds (0 = untimed), optionally shuffle final-test form questions, and save. Discard resets unsaved changes.
6. Preview each condition. This browser temporarily becomes a participant; **Exit Preview** restores the researcher. Preview uses the same content-only layout as participants, without navigation, footer, condition labels, or visible timer/diagnostic controls. Server deadlines and logging remain active. Exit removes the copy; closing the tab without Exit leaves it until the preview is exited/cleaned up.
7. Use Participant Analytics and Download Events for actual data. Existing activity history contains form responses. Event export streams rows and escapes spreadsheet-formula prefixes.
8. Replace placeholders and test real provider callbacks before activating recruitment/completion codes. Preview never issues recruitment credit.

## Reusable rehearsal and deployment

```bash
python manage.py migrate
python manage.py build_study_preview_lab --teacher RITEL_DEMO_Teacher
```

The command prints the setup URL and retains an existing lab on repeat runs. It never changes account passwords. The recruitment-disabled lab has consent/baseline placeholders, illustrative Q01/Q09, three remediation paths, post-session placeholder, a 60-second final-test demonstration and debrief. Forms substitute for unpublished providers and do not execute Python; use branch simulation to test correctness routing.

Deploy code/image, migrations and collected static assets using the normal deployment flow. No SSH, additional service, provider secret or production data repair is required. Existing courses and existing studies default to their previous behavior.

## Question-bank audit and outstanding study materials

Reference outputs (line breaks shown as `/`): Q01 `18`; Q02 `60`; Q03 `14`; **Q04 `15.0`**; Q05 `30 / 45`; Q06 `5 / 9`; Q07 `24 / 16`; Q08 `10 / 13 / 13`; Q09 `1`; Q10 `Affordable`; Q11 `Small`; Q12 `High`; Q13 `40`; Q14 `5 / 4`; Q15 `90 / 10`; Q16 `5`; Q17 `C`; Q18 `15 / 10 / 20`; Q19 `0 / 5`; Q20 `25 / 2`.

Q04's output cell says `15`, but Python 3 prints `15.0`; its explanation is already correct. Fix the provider's expected output. Q16's knowledge-component label mentions two if/else blocks, but the second has no else; prompt, code and output agree.

Still needed: final eight IDs and all remediation pairings; published Cupcake/WEAT URLs or actual authoring files; approved consent/debrief; `indices.docx`; final transfer questions and `rubric.docx`; section durations; confirmation of repeated-failure/remediation stopping policy. The 30-minute participation estimate does not specify section limits.

## Verification

`recruitment.tests.test_study_studio` covers condition routing, return, skipping, late callbacks, timers, hidden content, completion/access guards, simulation isolation, clones, Markdown and randomization. Existing recruitment/Cupcake suites provide regression checks. Browser rehearsals exercise desktop/mobile setup and participant navigation. Unpublished providers still need an actual activity pilot.

## Eight-problem experiment template

Share/import `exports/python-remediation-study-template.json` using **Manage Studies → Create Study → Optional Template JSON** (the study importer, not course/unit import). This is a draft configuration template, not approved participant materials. It contains seven units, 38 activities and 24 condition-specific failure branches. Independent random assignment is configured; Prolific recruitment is disabled and completion codes are empty.

The main sequence is consent → baseline measures/pretest → eight learning problems → post-session questionnaire → two shuffled transfer questions → debrief. The remediation library is excluded from the normal sequence. For each `Learning Problem NN`, targets `Learning Activity NN.1`, `.2`, `.3` are additional practice, similar example and matched example respectively. Neutral titles avoid revealing the assigned condition. Details and outstanding decisions are also embedded in the study's protocol notes.

1. Import as a new study. Open Study Setup and Activities & Flow Mapper.
2. Choose the final eight bank items. **Edit each existing Smart Content activity in place**, setting its URL and provider metadata. Select appropriate practice items from the remaining twelve; replace each similar/matched example with the approved WEAT delivery URL. Do not delete/re-add the slots: rules reference existing activity identities. Prefer SPLICE delivery when available and verify its callbacks.
3. Replace every bracketed form placeholder with the approved consent, questionnaire, pretest, transfer and debrief material. Expand baseline/post questionnaires to their actual item counts and response scales. The supplied 0–10 second-order confidence choices are intentional. Final written responses require rubric scoring; form submission completion is not exam accuracy.
4. Set approved section time limits if any (currently all untimed). Confirm repeat-error policy: each new original error repeats its remediation; additional practice returns after one scored submission regardless of correctness. Consent decline/withdrawal instructions must be supplied; this template does not invent an automated screening policy.
5. Preview every condition with the real activities and check incorrect/correct callbacks, example completion, original retries, saved responses and event exports. Only then configure Prolific eligibility/payment/completion codes and enable recruitment. The 300-person target is qualifying completers, not an entry cap.

`recruitment.tests.test_experiment_template` imports the actual distributed JSON, re-exports/re-imports it, checks conditions and final-question shuffle settings, and exercises all eight error/remediation/retry paths for each of the three conditions. These are canonical-event routing tests; unpublished provider integrations are not certified by the template.

### Published material mapping (2026-10-29)

Quinn approved Q09–Q16 as the eight main activities, paired in order with M01–M04 and H01–H04 for additional practice. The distributed JSON now contains these 16 published Cupcake SPLICE URLs and catalog identities. The other 12 variants are documented as reserves, not assigned to the baseline or transfer test. See `exports/python-remediation-study-mapping.md` for the complete inventory and comparison caveats. All 16 worked-example targets remain connected placeholders pending real WEAT/example URLs. The template is not ready for recruitment until these and the remaining approved instruments are provided and tested.
