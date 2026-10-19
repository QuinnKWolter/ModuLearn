# ModuLearn

Free and open-source tools for learning, teaching and research in computing education. The Django project is in this directory; deployment scripts live in `../docker`.

## Maintained guides

| Area | Guide |
| --- | --- |
| Architecture, models and ownership | [Architecture](docs/architecture.md) |
| Production deployment, static assets, networking and CA trust | [Operations](docs/deployment-adapt2.md) |
| Course configuration, plugins, analytics and studies | [Courses](docs/courses.md) |
| Recommendation setup, file contracts, presentation and logs | [Recommendations](docs/recommendation-package-format.md) |
| KnowledgeTree, catalog, provider tracking and LTI | [Integrations](docs/integrations.md) |
| Regression tests, provider coverage and HTTPS lab handoff | [Testing](docs/testing.md) |
| UI/localization, diagnostics and outstanding maintenance | [Development](docs/development.md) |

These seven guides replace dated investigation notes and duplicate app READMEs. Certificate provenance stays beside its PEM bundle. Provider coverage CSVs are dated evidence, not guarantees of current upstream availability. Functional JSON fixtures, translation catalogs and recommendation deployment packages remain in their owning directories.

From a configured development environment, run `python manage.py check` and `python manage.py test`; see the testing/development guides for boundaries and asset builds. Do not use production student data as a test fixture.
