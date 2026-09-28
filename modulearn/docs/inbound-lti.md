# Inbound LMS Launches Into ModuLearn

ModuLearn has two separate LTI directions:

- Inbound LMS-to-ModuLearn launches live in `lti/views.py`.
- Outbound ModuLearn-to-external-tool launches live in `modulearn/views_lti.py`.

Keep these separate. The inbound path lets Canvas, Moodle, or another LMS create/login/enroll a user into a ModuLearn course session. The outbound path launches CodeCheck, CTAT, PAWS-mediated tools, and other learning tools from inside ModuLearn.

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
