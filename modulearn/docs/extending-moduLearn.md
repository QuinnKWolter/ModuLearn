# Extending ModuLearn

## Adding a page

1. Add the Django view in the owning app as a thin delegator when possible.
2. Prefer shaping context in `modulearn.learning.selectors` or `modulearn.integrations` helpers rather than growing large views.
3. Build the template on top of:
   - `templates/base.html` for full pages
   - `templates/content_base.html` for embedded/iframe pages
4. Reuse `templates/includes/page_header.html`, `timeline_panel.html`, and other shared includes before creating new one-off patterns.

## Adding a workflow

1. Put read/query shaping into a selector.
2. Put state-changing behavior into a service.
3. Keep the public route stable if you are refactoring an existing flow.
4. Add at least one smoke or service-level test for the behavior.

## Adding a module/tool provider

1. Decide whether the tool is:
   - inbound LMS provider functionality
   - outbound LTI tool-consumer functionality
   - native module launch behavior
2. Put host/config rules into `modulearn.integrations`.
3. Use the existing progress service contract so launches/outcomes can update timelines consistently.
4. Document the new provider in `docs/integrations.md`.
