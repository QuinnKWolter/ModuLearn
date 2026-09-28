# Sign-in roles and display names

Investigated 2026-09-28. The code changes below do not change account roles, merge accounts, or rewrite stored names. No production database was accessed or modified.

## Navbar name

The navbar previously used Django's `get_full_name()` (first name plus last name), ignoring ModuLearn's separate `full_name` field edited on Profile. A name saved on Profile therefore could not correct stale imported first/last names in either navbar menu.

`User.get_display_name()` now prefers a nonblank profile name, then first/last names, then username. A candidate with no alphabetic characters is treated as an identifier rather than a display name. Unicode letters are supported. Both desktop/mobile menus and the profile heading use it, retain HTML escaping, and exclude the name from automatic UI translation. Original stored fields and external identities are preserved. The source of a particular production identifier cannot be established without inspecting that account's name fields; no provider-specific provenance is assumed.

## Roles

The application role comes from `accounts.User.is_instructor` and `is_student`, not a similarly named Django auth group. For an authenticated instructor, `get_user_role_snapshot()` makes instructor take precedence over student flags and enrollment. Navbar construction and dashboard redirects use the same snapshot. KnowledgeTree group membership is not consulted to decide which dashboard link appears.

Historical versions before `a91146c` could demote an instructor when Aggregate failed to confirm the role. Current KT and LTI logic preserves existing local role flags. That does not repair previously incorrect flags, nor should a login automatically grant instructor permissions to an existing student. Aggregate is consulted when provisioning a new KT user; unavailable lookup leaves both flags false.

A separate stale-write race was reproduced: KT linking or metadata synchronization previously saved the entire user instance. If an administrator changed its role while the lookup was running, that save could overwrite the correction. These paths now save only KT/identity metadata. The model's partial-save logic also avoids adding student-role writes to unrelated updates. Explicit role changes and full saves still enforce instructor/student exclusivity. The KT backend refreshes role flags before returning the authenticated user.

The same field-scoped saving applies to profile edits, local/KT password forms, and Course Authoring credential generation/reset, so those operations do not overwrite a concurrent role correction either. Administrator role edits remain supported; the flag is not made permanently immutable.

Additional regressions reproduced two ways a checked instructor flag could be bypassed without changing the database flag: a student snapshot cached earlier on the same user object, and a retained research-participant flag/session that redirected the instructor before the dashboard role check. Snapshot reuse now requires unchanged role flags; instructor status overrides participant navigation suppression and participant confinement/redirects. Participant provisioning refuses to repurpose an instructor account, and even an explicitly requested LTI role resync cannot demote an instructor. Normal student/participant behavior remains covered by the existing suite.

These are confirmed defects, but the exact trigger of the reported production discrepancy remains unconfirmed. Do not automatically promote, merge, or relink accounts to conceal it. A checked `is_instructor` flag is authoritative for the authenticated account; these changes do not infer instructor status from a name, group membership, or remote lookup.

## Production checks when Admin and the browser disagree

First check the affected browser's Profile page: **Username**, **Role**, and **KnowledgeTree Login**. Compare the username with the exact Admin record. Email/display name alone may hide different identities. A standard authenticated request is not replaced by the LTI recovery middleware; that middleware only attempts recovery for an unauthenticated request with retained LTI state.

Next run the following inside the **same running application container/process environment** serving the page. Start `python manage.py shell`, then paste this read-only snippet. It prints only identity/display/role fields, expected navigation keys, and the database/source locations. It does not print passwords, keys, tokens, raw launch data, or session contents and does not call KT:

```python
import inspect
from types import SimpleNamespace
from django.conf import settings
from django.db.models import Q
from accounts.models import User
from modulearn.core.navigation import build_navigation
from modulearn.core.roles import get_user_role_snapshot

identifier = "bakram@ncsu.edu"  # Repeat with QuinnKWolter for the name issue.
print("Database:", settings.DATABASES["default"]["NAME"])
print("Role implementation:", inspect.getfile(get_user_role_snapshot))
matches = User.objects.filter(
    Q(username__iexact=identifier)
    | Q(email__iexact=identifier)
    | Q(kt_login__iexact=identifier)
).distinct().order_by("pk")
for user in matches:
    print({field: getattr(user, field) for field in (
        "pk", "username", "full_name", "first_name", "last_name",
        "is_instructor", "is_student", "is_active",
        "is_anonymous_participant", "kt_login",
    )})
    print("Effective role:", get_user_role_snapshot(user)["primary_role"])
    print("Navigation:", [item["key"] for item in build_navigation(
        SimpleNamespace(user=user, path="/")
    )])
```

Interpretation:

- Different Profile username: inspect account matching and login method before changing roles or linking identities.
- Exact account has `is_instructor=False`: identify why the Admin/browser environments or records differ. Make any intentional role correction on the verified record; KT sign-in is not a role-repair mechanism.
- `is_instructor=True`, normal account, expected navigation contains `instructor`, but the browser shows student: check the actual deployed image/revision, all worker instances, database mounts, reverse-proxy routing, and cached HTML. Current tests cannot reproduce that mismatch from those flags alone.
- `is_anonymous_participant=True`: older code could hide navigation or redirect to research even for an instructor. The patched code gives the instructor flag precedence while preserving the stored participant flag and history. Normal participants still use the research shell.

An existing signed-in session picks up an Admin role change on its next request in the current implementation; it does not require manual session deletion. Inspect the deployment before assuming a permanent session cache.

## Verification

Regression coverage in `accounts/tests.py` exercises both navbar menus, profile-name precedence, numeric-name fallback, Unicode names, normal password login, KT fallback matching by ID/login/email/username, concurrent role changes during KT synchronization, role changes during an existing session, and instructor precedence over student enrollment, cached role snapshots, and participant state. Additional LTI and recruitment tests prove automated role sync/provisioning cannot demote or repurpose an instructor. Existing LTI role-preservation tests remain part of the full suite.

Profile/password changes and Course Authoring credential writes also have concurrent-role regression coverage. Test databases are disposable and external services are mocked or blocked.

Final validation: all **200 tests passed** on Django 6.0.5 / Python 3.14.0 (18 tests added). Django system checks passed, no model migration changes were detected, and the diff passed whitespace checks.

No schema migration or CSS rebuild is required. Application code/templates still need the normal deployment and worker restart. Production behavior must be checked after deployment; local tests are not proof of the production account's state.
