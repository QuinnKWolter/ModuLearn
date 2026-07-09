# Research Recruitment Links

ModuLearn supports reduced-access research participants through `recruitment` sources attached to a `CourseInstance`.

## Prolific Entry Flow

Instructors create or update the Prolific source from the course configuration recruitment modal. The generated external study URL has this shape:

```text
https://<host>/r/prolific/<source_id>/?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

Prolific fills those placeholders when a participant launches the study.

In the UI, instructors get this link from:

```text
Instructor Dashboard -> course session card -> Configure -> Study Recruitment icon/modal -> Participant entry link
```

They should paste it into Prolific as the external study URL and enable URL parameters. The same modal also shows the end-of-study credit link:

```text
https://<host>/r/complete-current/<course_instance_id>/
```

Add that URL as the final link/module in the course. It only works for a participant who entered through a recruitment link and is still logged into the corresponding anonymous participant account.

Expected parameters:

- `PROLIFIC_PID`: Prolific participant id, stored as a string.
- `STUDY_ID`: Prolific study id, stored as a string and checked against the configured source when present.
- `SESSION_ID`: Prolific submission id, stored as a string and used as the idempotency key for resuming the same participant session.

All three values are validated as 24-character hexadecimal identifiers before ModuLearn provisions anything. URL parameters are treated as identifiers, not secrets.

On accepted entry, ModuLearn:

- creates or resumes an anonymous participant `User`,
- creates or resumes the learner `Enrollment`,
- creates or resumes a `ParticipantSession`,
- assigns the participant to the session/source condition,
- logs the entry attempt,
- signs the participant in,
- redirects to the reduced-access study sessions page.

Anonymous participants are intentionally restricted. They are redirected away from profiles and dashboards, cannot browse the normal course hub, cannot enroll in other sessions, and can only resume assigned study sessions/modules.

## Session Conditions

Study conditions are treated as one-to-one with study sessions/sources. The recruitment modal exposes a single **Session condition** field. If an old value contains comma-separated labels, ModuLearn uses the first label for compatibility.

Use separate course sessions when you need separate conditions such as `control` and `treatment`. Unlock rules can still target participant conditions through the course configuration UI.

## Completion

Course pages can link to:

```text
/r/complete-current/<course_instance_id>/
```

That endpoint resolves the logged-in participant's active `ParticipantSession`, calculates the completion outcome, and redirects to Prolific using the configured completion code:

```text
https://app.prolific.com/submissions/complete?cc=<completion_code>
```

For Prolific credit to work end to end:

- the Prolific source must have a completion code configured,
- the participant must enter through the generated Prolific entry URL,
- the participant must click the end-of-study credit link while logged into the provisioned participant account.

The Prolific study id is used during entry validation. The completion redirect itself depends on the stored participant session and completion code.

## Local Testing

Use the generated Prolific URL and replace the placeholders with stable 24-character hex values, for example:

```text
?PROLIFIC_PID=aaaaaaaaaaaaaaaaaaaaaaaa&STUDY_ID=bbbbbbbbbbbbbbbbbbbbbbbb&SESSION_ID=cccccccccccccccccccccccc
```

Reusing the same `SESSION_ID` should resume the same `ParticipantSession`. Changing `SESSION_ID` creates a new submission/session if capacity allows.
