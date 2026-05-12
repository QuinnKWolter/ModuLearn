# Integrations

## KnowledgeTree and MasteryGrids

Primary files:

- `dashboard/kt_utils.py`
- `dashboard/db_queries.py`
- `dashboard/views.py`
- `modulearn/views_proxy.py`

Responsibilities:

- discover groups and course IDs
- fetch legacy analytics data
- fetch KnowledgeTree resources
- maintain login/session checks
- proxy legacy HTTP content into the app safely

## Course Authoring

Primary files:

- `modulearn/integrations/config.py`
- `modulearn/integrations/course_authoring.py`
- `courses/utils.py`
- `dashboard/views.py`

Responsibilities:

- generate x-login tokens
- proxy x-login when browser CORS blocks direct calls
- build export/import URLs from centralized config
- redirect instructors into the authoring shell

## Inbound LTI provider

Primary files:

- `lti/views.py`
- `lti/models.py`
- `lti/cache_data_storage.py`

Responsibilities:

- accept LMS launches into ModuLearn
- serve XML config / JWKS / login endpoints
- maintain provider-side launch cache and related state

## Outbound LTI tool consumer

Primary files:

- `modulearn/views_lti.py`
- `lti/models.py`
- `lti/services.py`

Responsibilities:

- launch external tools from inside ModuLearn
- cache launch context so outcomes can resolve back to local models
- update local `ModuleProgress` from outcome callbacks
- forward outcomes to the external UM service when configured

## Proxy layer

Primary files:

- `modulearn/views_proxy.py`
- `modulearn/settings.py`

Responsibilities:

- proxy legacy HTTP content and activity APIs
- rewrite legacy HTML safely
- preserve KnowledgeTree session cookies
- enforce allowlists

## Configuration rules

- External hostnames should be derived from `modulearn.integrations.config`, not hardcoded in templates.
- Public route paths should be built with `reverse()` or `prefixed_path()` where relevant.
- Inbound and outbound LTI paths stay separate even if they share helpers.
