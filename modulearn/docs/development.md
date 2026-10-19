# Development, maintenance and diagnostics

## Extending the platform

Keep route names and Django app labels stable. Put read shaping in selectors and state changes in services. Use `base.html` for full pages, `content_base.html` for embedded activity pages, shared includes and design-system tokens. New providers need a verified delivery/grade contract, source/origin validation, exact session/practice resolution and tests for failed/correct/retried submissions. Unknown messages must not become guessed grades. Update the provider matrix only with actual evidence.

Course configuration changes must retain atomic saves, multipart uploads, CSRF, instructor ownership and research locks. Check ordinary and instructor-testing enrollments separately. Recommendation events/grades must stay out of normal class rollups.

## UI build and localization

```bash
npm ci
npm run build:css
python manage.py collectstatic --noinput
```

Run in `modulearn/`; production Docker builds the CSS in a separate Node stage. The runtime entrypoint collects static assets and the deployment script publishes them. Never hand-edit the generated stylesheet. Home uses `home.css`; Info/Profile use `editorial-pages.css`. Home variants follow authenticated roles without audience tabs. Preserve the compact copyleft footer and responsive layouts.

## Adding translated interface text

The existing EN/ES switch and Django language middleware remain authoritative.
The navbar posts to Django's `set_language` endpoint and stores the choice in the
`modulearn_language` cookie. Opening a page with `?lang=en` or `?lang=es` also
changes the language and updates that cookie. Additional supported languages must
be registered in `modulearn/settings.py` under `LANGUAGES`.
Feature messages live in `main/locales/es/`, grouped into `public.json`,
`configuration.json`, `catalog.json`, and `recommendations.json`. English source
strings are the keys and are also the fallback when no translation is available.
Adding another configured language uses a corresponding locale directory.

For templates:

```django
{% load ui_i18n %}
{% ui "Go to your courses" %}
{% ui "Adding to: {unit}" unit=unit.title %}
```

For JavaScript, use complete messages with named placeholders:

```javascript
ModuLearnI18n.t('Page {page} of {pages}', {page, pages});
```

The template tag and JavaScript consume the same feature catalog. `base.html`
embeds it with Django's safe `json_script` helper; no additional translation
request or compile step is needed. Templates escape interpolated values, and
interactive components insert translated messages using `textContent`. The server
caches catalog files for the process lifetime, so restart the app when deploying
translation edits. Run the normal static collection for changed JS/CSS.

Do not concatenate translated sentence fragments or pass course content through
the translator. Translate first, then interpolate. Use `data-no-ui-translate`
around content that must stay literal. The SLC browser translates its own labels,
counts, table headings, pagination, empty states, availability notices, selection
messages, and accessibility labels explicitly. Titles, descriptions, authors,
provider metadata, delivery URLs, and source code retain the source language.
Filter option values and saved preferences remain language-independent. Numeric
catalog counts and recommendation similarities use the active locale.

The existing automatic translator still covers older templates, including shared
form labels and configuration controls. Feature catalogs extend that dictionary
as well, so those pages can migrate incrementally. New public pages are translated
on the server; their wording does not depend on a post-load DOM rewrite. New
configuration labels and plugin text are covered by the feature catalogs, while
older translations remain in `static/js/i18n.js`.


## Progress incident diagnosis and repair

Record exact session, module, user and time. Compare the per-attempt ledger, raw provider payloads, state, current rollup and network failures. Launch-only audit flags are **review candidates**, not proof of a lost successful attempt. Normal and practice records must be inspected separately. Unknown historical scores cannot be invented.

The read-only [audit script](../../docker/audit-student-progress.py) can be piped into the production Django shell:

```bash
sudo docker exec -i modulearn__webapp bash -c 'cd /modulearn && python manage.py shell -v 0 -c "import sys; exec(sys.stdin.read())"' < ModuLearn/docker/audit-student-progress.py
```

It defaults to sessions 42/43; set `AUDIT_SESSION_IDS` in the container process environment to audit other sessions. Keep generated student reports private and outside the source checkout/public media.

`python manage.py repair_cupcake_progress --help` describes the narrowly scoped repair. Supply `--sessions` and `--modules`; preview is the default. It reconciles saved free-coding answerChecked events with explicit correctness/transport IDs, skips ambiguous counters/ownership/single-attempt cases, and does not replay external submissions. Review preview output and take a database-consistent backup before adding `--apply`. This is not a general provider recovery tool and cannot restore data never received.

`import_course_unit` and `transition_recommendations` also expose dry-run/checksum workflows via `--help`; transitions require course and session scope. Prefer the atomic linked-package upload for normal recommendation installation.

## Open maintenance work

Documentation cleanup is not a security repair. Preserve these actionable findings from the earlier review; deployed exposure still needs separate assessment:

- Inbound LTI 1.1 `handle_lti11_launch` passes extracted fields to identity processing without the outbound path's signature checks. Review registration, signature/replay validation and account linking before treating this route as trusted.
- `create_enrollment_code` checks instructor role but not session ownership, and `enroll_with_code` can authenticate an existing user without enforcing one-time validity. Separate invitation acceptance from authentication and add scoped authorization.
- Legacy `create_course_from_json` can retrieve/update an existing course ID; enforce ownership/clone isolation at the mutation boundary. The legacy `fetch_class_list` endpoint needs group authorization, not just login. Review global LTI setup/registration scope too.
- `.env` and a private key are tracked. Plan separate credential/configuration remediation and rotation with recruitment encryption compatibility. Review credential logging, upstream session identifiers, proxy cookie forwarding and same-origin executable content boundaries; this cleanup does not certify them.
- Recruitment `_determine_outcome` can default incomplete work to completed. Review completion policy, synthetic-ID bypasses, secured claims and `PROLIFIC_API_TOKEN` configuration before tightening a study contract.
- Access-rule disable semantics, exclusive branch denominators, visibility rollups and file/link completion gates need explicit policy/tests. Earlier findings here should be revalidated against the intended course behavior before changing grades.
- Historical account migration 0008 deduplicates emails destructively. Do not rerun or rewrite it as a progress repair; inspect backup impact first.
- Load-test concurrent enrollment/condition assignment and SQLite writes. IMMEDIATE transactions reduce lock-upgrade failures but do not prove capacity/assignment safety under load.
- Candidate dead compatibility code: `establish_http_session`, `KNOWLEDGETREE.SECURITY_CHECK_PATH`, `lti/tool_config.py::DjangoToolConf`, and DB factory aliases. Verify callers before removing. SSH and the default Saltire registration have already been removed; direct MySQL remains required for active paths.

## Documentation and artifact policy

Keep one maintained guide per area, linked from [README](../README.md). Update existing sections rather than adding dated fix reports, speculative designs or generated file maps. Keep public deployment packages, schemas, test fixtures and certificate provenance; put disposable captures/logs in ignored scratch space. Do not use blanket JSON/TXT deletion: translations, package locks and replay fixtures are functional inputs.
