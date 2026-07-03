# Research Recruitment Links

ModuLearn supports reduced-access research participants through `recruitment` sources attached to a `CourseInstance`.

## Prolific Entry Flow

Instructors create or update the Prolific source from the course configuration recruitment modal. The generated external study URL has this shape:

```text
https://<host>/r/prolific/<source_id>/?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

Prolific fills those placeholders when a participant launches the study.

Expected parameters:

- `PROLIFIC_PID`: Prolific participant id, stored as a string.
- `STUDY_ID`: Prolific study id, stored as a string and checked against the configured source when present.
- `SESSION_ID`: Prolific submission id, stored as a string and used as the idempotency key for resuming the same participant session.

All three values are validated as 24-character hexadecimal identifiers before ModuLearn provisions anything. URL parameters are treated as identifiers, not secrets.

On accepted entry, ModuLearn:

- creates or resumes an anonymous participant `User`,
- creates or resumes the learner `Enrollment`,
- creates or resumes a `ParticipantSession`,
- assigns the participant to a configured research condition,
- logs the entry attempt,
- signs the participant in,
- redirects directly to the assigned course session.

Anonymous participants are intentionally restricted. They are redirected away from profiles and dashboards, cannot enroll in other sessions, and can only view their assigned course session.

## Completion

Course pages can link to:

```text
/r/complete-current/<course_instance_id>/
```

That endpoint resolves the logged-in participant's active `ParticipantSession`, calculates the completion outcome, and redirects to Prolific using the configured completion code:

```text
https://app.prolific.com/submissions/complete?cc=<completion_code>
```

## Local Testing

Use the generated Prolific URL and replace the placeholders with stable 24-character hex values, for example:

```text
?PROLIFIC_PID=aaaaaaaaaaaaaaaaaaaaaaaa&STUDY_ID=bbbbbbbbbbbbbbbbbbbbbbbb&SESSION_ID=cccccccccccccccccccccccc
```

Reusing the same `SESSION_ID` should resume the same `ParticipantSession`. Changing `SESSION_ID` creates a new submission/session if capacity allows.

