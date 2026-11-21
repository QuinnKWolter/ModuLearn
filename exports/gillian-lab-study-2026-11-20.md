# Gillian lab study — researcher draft content revision

Import `gillian-lab-study-2026-11-20.json` as a **study template** when creating a new study. It supersedes the November 16 package for administrative content. The original package remains available for comparison. This revision has **8 units, 45 activities, 3 conditions, and 24 failure connections**. Recruitment remains disabled and completion codes remain blank.

## What changed

Condition names and stable labels now match `code-writing-remediations-modulearn-study-export.json`:

| Name | Label |
| --- | --- |
| More Practice | `more_practice` |
| Similar Example | `similar_example` |
| Matched Example | `matched_example` |

All 24 branch condition references were updated together. Internal activity role tags remain unchanged; those identify intervention types rather than participant assignment labels.

The following descriptions, form instructions, questions, answer options, required flags, and submission controls are copied exactly from the supplied draft:

| Placement | Draft activity | Revision |
| --- | --- | --- |
| 01 Consent, first | Consent | Replaces the consent placeholder with the full supplied consent text and acknowledgment. |
| 01 Consent, second | Instructions | Adds the draft's separate instruction acknowledgment after consent. |
| 02 Baseline | Pretest | Replaces placeholder baseline items with the six supplied motivation/background questions. The draft title is retained; this survey is distinct from the four coding pre-test activities in Unit 03. |
| 06 Post-session Questionnaire | Post-study motivation questions | Replaces placeholder measures with the fifteen supplied questions. |
| 08 Debrief | Debrief | Copies the draft's description, continuation instructions, and acknowledgment. |

The real coding pre/post-tests, all eight learning/remediation pairs, activity URLs, order, completion rules, Next pacing, original-problem retries, and untimed sections remain unchanged. The source's empty coding posttest placeholder and incomplete branching were not copied. Its database IDs, recruitment links, and participant records were not imported. The existing [November guide](gillian-lab-study-2026-11-16.md) documents the retained exercise mapping and behavior.

## Remaining draft decisions

These are present in the supplied material, not newly invented content:

- Consent retains bracketed screening alternatives and multiple duration, payment amount, and payment schedule choices. It mentions screening and payment behavior that this template does not implement automatically.
- Instructions and Debrief still contain generic directions rather than full study-specific text.
- The baseline enjoyment item retains `[interested/excited]` in its answer options.
- All 21 motivation scale items retain the source's **multiple-answer** question type. Confirm whether each should instead accept only one answer before recruiting.
- The draft does not include the earlier expected-test-score estimates and confidence-in-estimate questions. Those former placeholders are replaced by the supplied questionnaire, not silently appended or invented.

The five administrative activities remain marked `requires_material_replacement: true` for review. That metadata is a reminder, not an automatic recruitment guard. Finalize these decisions in Study Setup/Course Configure and explicitly enable recruitment only when ready.

## Validation and use

The content was compared directly with the supplied JSON. Package regression tests exercise import → export → reimport, all eight intervention/retry paths for each renamed condition, the added Instructions step, and preservation of all exercise definitions and imported form content. This revision changes study data, not application behavior.

After deploying the current code, create a **new study** using this JSON, review the copied administrative pages in participant preview, finalize the remaining draft text and response controls, and configure the recruitment/completion settings. Importing it does not rewrite an existing production study or its participant assignments.
