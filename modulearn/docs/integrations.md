# Integrations and provider tracking

## KnowledgeTree / PAWS

`accounts/backends.py` delegates to `KnowledgeTreeAuthService`. API/both authentication calls `/PortalServices/Auth`; database mode/fallback uses `dashboard.kt_db_connection.get_paws_db_connection`. `accounts/views.py` can additionally provision/link users and synchronize passwords. `dashboard/kt_utils.py` performs user/group/resource lookups, Aggregate instructor/course discovery and password synchronization. `dashboard/db_queries.py` serves legacy class/student analytics. API login success alone does not prove those separate database-dependent workflows work.

The shared connection factory now uses direct PyMySQL with timeouts and cleanup; there is no application-managed SSH. Preserve the PAWS database credentials and schema settings. KT's legacy password representation is not the local Django password representation. API results may lack a numeric KT UserID. Existing local instructor flags are preserved; KT authentication does not automatically make everyone an instructor. See [identity invariants](architecture.md) and [operations](deployment-adapt2.md).

Course Authoring integration generates x-login credentials/URLs through `modulearn.integrations` and existing view helpers. KT group/course discovery and MasteryGrids remain active legacy features; they are not interchangeable with native course sessions or analytics.

## Catalog and delivery selection

`modulearn.learning.services.slc_catalog` reads fixed public Pitt and SPLICE sources. Pitt lists omit delivery URLs, so details are fetched before import; SPLICE protocol/URL arrays must remain paired. Selected catalog imports prefer SPLICE, then HTML, PITT, LTI, preserving all original metadata in `content_data.catalog`. Only the selected protocol is assigned to its selected URL. Demo URLs are not substituted for delivery URLs. Broken entries and missing endpoints cannot be imported.

Sources cache independently for one hour, with a marked stale fallback up to 24 hours. Fetches use bounded size/time limits and verified HTTPS. Cache failures and upstream failures are distinguished. Run `python manage.py check_slc_catalog` to test both paths. Counts are not fixed expectations.

Pitt's omitted intermediates are supplied with root-anchored verification, not trusted as arbitrary roots. See [certificate provenance](../modulearn/learning/services/certificates/README.md). For ACOS, the production check on 2026-10-19 failed with Requests' default bundle but succeeded with the OS CA bundle. The Docker image now defaults `REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt`; existing deployments can set it in their root `.env` and recreate the webapp. Do not use `verify=False`.

## Tracking contracts

HTML is delivery, not a grading protocol. SPLICE and provider-specific adapters supply observations where available; an unknown event is logged without inventing a grade. Browser messages must match the embedded frame and allowed origin. Transport retries retain event IDs. Explicit session/module/practice context takes precedence over mutable group labels, and ambiguous contexts fail closed.

| Provider family | Evidence captured / limits |
| --- | --- |
| PCEX | Explanation steps/selected-goal metadata drive reading completion; challenge results drive scored attempts. Legacy preview URLs normalize to ACOS with HTTPS load URLs while retaining goal index, including zero. Missing metadata permits logs, not invented completion. |
| PCRS | Proxied run responses record source, grader results, score and attempts. Practice callbacks use the isolated context. |
| QuizJET / QuizPET | Proxied graded responses preserve answer/context through retry forms. Provider HTTP errors are not successful submissions. |
| Cupcake | Native logs are authoritative; mirrored SPLICE grades do not duplicate attempts. Answer checks normalize the verified engine's score/correctness; explanation viewing is ungraded completion. Free-coding checks are supported. Unknown messages retain raw details. Provider execution errors cannot always be distinguished from wrong answers if the provider reports them identically. |
| JSVEE | Final animation progress and delivered SPLICE step logs are retained; abandoned runs may not emit every step. |
| AnnEx | Annotated-line metadata and unique line-open events determine viewing progress, without scored attempts. |
| SQL-KnoT | CheckAnswer and interaction responses preserve SQL, result, retries and relevant SQL-Lab/schema interactions in exact session context. |
| DBQA | Signed LTI launch plus query-step adapter; browser completion and server-side LTI outcome are distinct evidence. |
| CodeCheck / jsParsons | Supported SPLICE/ACOS interactions feed the common progress path. Live provider availability still varies by record. |
| Outbound LTI 1.1 | Signed Basic Outcomes provide normalized scores, not every keystroke or intermediate answer. |

Cupcake resize handling accepts bounded heights from the verified source/origin inside a scrollable activity viewport. Growth is coalesced to avoid resize feedback loops; shrinking within a launch may leave space rather than bounce the page. Recommendation frames suppress inner app footers. Saved editor/random-parameter restoration remains provider-dependent even when local scores and logs persist.

The capture fixture `courses/fixtures/cupcake_observed_events.json` is synthetic/test evidence consumed by regressions, not a student log export. All adapters must preserve ordinary-course versus recommendation isolation; see [recommendations](recommendation-package-format.md). Representative provider results and unresolved setup requirements are in [testing](testing.md).

## Outbound LTI

`modulearn/views_lti.py` handles authenticated tool launches and outcomes; inbound LMS identity is separate. Outbound launch contexts bind user, module, exact course session and permitted practice context. Callbacks validate OAuth signatures/body hashes and finite normalized scores, reject mismatched contexts and deduplicate identical signed retries. Stored course scores use 0–100; callback values use 0–1. `LTI_FORWARD_TO_UM` controls optional legacy forwarding separately from local saving.

Direct provider credentials belong in environment configuration. The old Node consumer is a reference, not the implementation. Saltire is no longer implicitly registered; active database platform registrations remain supported. See [HTTPS testing and credential variable names](testing.md).

## Inbound LMS setup

The following describes existing inbound routes, not a security certification. The inbound LTI 1.1 handler still needs the authorization review listed under [open maintenance work](development.md#open-maintenance-work); outbound signature validation does not fix that separate path.

## LTI 1.1 / Canvas Legacy

Endpoints:

- Launch: `/lti/launch/?course_id=<CourseInstance.id>`
- Cartridge XML: `/lti/config/?course_id=<CourseInstance.id>`

The instructor dashboard LTI Setup modal exposes both. The copied URL preserves the selected course session via `course_id`.

Flow:

1. Canvas posts a Basic LTI launch to `/lti/launch/`.
2. `handle_lti11_launch` normalizes the POST fields.
3. `process_launch_data` provisions or reuses a local user by Canvas/LTI identity or case-insensitive email.
4. Learners are enrolled in the `CourseInstance`; instructors are attached as instructors.
5. If Canvas sends `lis_result_sourcedid`, it is stored on `CourseProgress` for legacy grade passback.

## LTI 1.3 / Moodle And Canvas Advantage

Copy these values from the LTI Setup modal into Moodle or Canvas:

- Tool URL / Target Link URI: `/lti/launch/?course_id=<CourseInstance.id>`
- Initiate login URL: `/lti/login/`
- Redirect URI: `/lti/launch/`
- Public keyset / JWKS URL: `/lti/jwks/`

After the LMS tool is created, copy its platform details back into the same modal:

- Platform ID / issuer
- Client ID
- Deployment ID
- Authentication request URL
- Access token URL
- Public keyset URL

These values create or update `LTIPlatformRegistration`, which is used by `pylti1p3` to validate signed `id_token` launches.

Flow:

1. Moodle/Canvas sends OIDC login initiation to `/lti/login/`.
2. ModuLearn builds the auth redirect through `pylti1p3` using DB-backed platform registrations.
3. The platform posts an `id_token` to `/lti/launch/`.
4. `DjangoMessageLaunch.validate()` verifies the JWT and deployment.
5. `process_launch_data` reads standard LTI 1.3 claims, including roles, deployment, custom fields, and `target_link_uri`.
6. The course session is resolved from `course_id` in the target link URI or custom claims.
7. The local user is mapped through `LTIUserIdentity`, then enrolled or attached as instructor.

## Notes

- LTI 1.3 registration is tenant-specific. A copied Tool URL alone is not enough; the platform registration details must exist in ModuLearn before signed launches can validate.
- External LMS roles do not demote an existing ModuLearn instructor to student.
- Moodle and Canvas should share the launcher's name and email if you want automatic account reuse by email on first launch.
- LTI 1.3 grade passback via Assignment and Grade Services is not implemented here yet; legacy LTI 1.1 outcome passback remains the existing Canvas-oriented path.
