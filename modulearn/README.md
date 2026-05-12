# ModuLearn

ModuLearn is a Django learning platform that blends native course delivery with external-tool launches, legacy analytics, and instructor workflow tooling. The current refactor keeps all public routes stable while consolidating behavior into tighter internal packages and a cleaner template/static-asset system.

## Project layout

- `accounts/`: authentication, profile management, KnowledgeTree account linking, password sync.
- `courses/`: native course structures, course instances, enrollments, progress, invite-code enrollment, module launching.
- `dashboard/`: student and instructor dashboards, native analytics, legacy MasteryGrids analytics, KnowledgeTree helper views.
- `lti/`: inbound ModuLearn-as-tool provider for LMS launches.
- `main/`: marketing/static pages.
- `modulearn/`: project settings, root URLs, outbound LTI consumer views, proxy views, and the new internal domain packages.

## Internal domain packages

- `modulearn.core`: app-shell helpers, navigation, shared context, design-system glue.
- `modulearn.learning`: selectors and services for dashboards, progress, analytics, and timelines.
- `modulearn.integrations`: course-authoring, KnowledgeTree, LTI, and URL/config helpers for external services.

## Key refactor outcomes

- Shared design system and responsive application shells now live in `static/css/design-system.css`, `templates/base.html`, and `templates/content_base.html`.
- Progress tracking has durable completion timestamps and an event ledger through `ModuleProgressEvent`.
- Student and instructor timelines are available through `modulearn.learning.selectors.timelines`.
- Dashboard and profile pages now use static JavaScript modules instead of large inline scripts for several high-traffic workflows.

## Documentation

- [Architecture](docs/architecture.md)
- [Page Inventory](docs/page-inventory.md)
- [Progress Timeline](docs/progress-timeline.md)
- [Model Glossary](docs/model-glossary.md)
- [Integrations](docs/integrations.md)
- [Testing](docs/testing.md)
- [Compatibility Checklist](docs/compatibility-checklist.md)
- [Extending ModuLearn](docs/extending-moduLearn.md)

## Testing

Test coverage is intentionally focused on smoke access, progress/timeline behavior, invite enrollment, dashboard rendering, and LTI outcome compatibility.

Run the Django test suite with your configured Python environment:

```bash
python manage.py test
```

If Python is not configured locally, use the project’s containerized runtime or your normal deployment environment.
