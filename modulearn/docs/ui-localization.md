# UI Localization

ModuLearn uses Django language selection for the active language and a small browser-side UI catalog for current templates and JavaScript-rendered labels.

## Current Languages

- `en`: English
- `es`: Spanish

The navbar language toggle posts to Django's `set_language` endpoint and stores the choice in the `modulearn_language` cookie.

Any page can also be opened with `?lang=en` or `?lang=es`. That query parameter activates the language for the current request and updates the same language cookie for later pages.

## Where To Add Translations

- Add new language codes in `modulearn/settings.py` under `LANGUAGES`.
- Add UI strings in `static/js/i18n.js`.
- Prefer exact English source strings as keys.
- Use prefix rules only for stable labels followed by dynamic values, such as `Assigned condition: C1`.

External learning modules loaded in iframes are intentionally not translated by ModuLearn.

For future server-side translations, templates can be incrementally moved to Django `{% trans %}` / `{% blocktrans %}` tags and compiled into `locale/<lang>/LC_MESSAGES/django.mo`.
