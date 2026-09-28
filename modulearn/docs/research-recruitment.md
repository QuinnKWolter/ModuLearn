# Research Recruitment Links

ModuLearn research recruitment is Study-owned. A `Study` has a backing course session for module playback, but courses and ordinary course sessions no longer expose Prolific setup directly.

## Study Setup

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

## Prolific Entry Flow

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
- redirects to the reduced-access study sessions page.

Anonymous participants are intentionally restricted. They are redirected away from profiles and dashboards, cannot browse the normal course hub, cannot enroll in other sessions, and can only resume assigned study sessions/modules.

## Conditions

Study conditions are configured on the Study, not on a course session. Current assignment strategies are:

- `balanced`: assigns the least-filled condition first.
- `hash`: deterministic assignment from the participant id.
- `schedule`: claims preallocated `RecruitmentAssignmentSlot` rows.

Module unlock rules can still target participant conditions through the course-structure editor, but the condition comes from the Study-owned `ParticipantSession`.

## Completion

The Study modal shows the end-of-study credit URL:

```text
https://<host>/r/study/<study_id>/complete-current/
```

Add that URL as the final link/module in the study flow. It resolves the logged-in participant's Study session and redirects to Prolific with the configured completion code:

```text
https://app.prolific.com/submissions/complete?cc=<completion_code>
```

For Prolific credit to work end to end:

- the Study's Prolific source must have a completion code configured,
- the participant must enter through the generated Study launch URL,
- the participant must click the end-of-study credit link while logged into the provisioned participant account.

The legacy `/r/prolific/<source_id>/` and `/r/complete-current/<course_instance_id>/` routes remain as compatibility fallbacks for older rows, but new UI should use Study routes only.

## SONA

SONA configuration is temporarily disabled in the instructor UI and rejected by the source-creation endpoint. Existing SONA model fields and services remain in place, but new SONA sources should not be created until the SONA flow is re-enabled.

## Local Testing

Use the generated Study launch URL and replace the placeholders with stable 24-character hex values, for example:

```text
?PROLIFIC_PID=aaaaaaaaaaaaaaaaaaaaaaaa&STUDY_ID=bbbbbbbbbbbbbbbbbbbbbbbb&SESSION_ID=cccccccccccccccccccccccc
```

For preview/simulation runs where Prolific gives you only one participant link, `PROLIFIC_PID` may also be a synthetic id beginning with `test`, `demo`, or `pilot`, for example:

```text
?PROLIFIC_PID=test-participant-01&STUDY_ID=bbbbbbbbbbbbbbbbbbbbbbbb&SESSION_ID=testsession01
```

Reusing the same `SESSION_ID` resumes the same `ParticipantSession`. To simulate a new participant, change both `PROLIFIC_PID` and `SESSION_ID`; keep `STUDY_ID` the same for the same Prolific study. Synthetic participant IDs skip remote Prolific submission verification even if `PROLIFIC_API_TOKEN` is configured.
