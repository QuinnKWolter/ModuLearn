# Course Plugin Contract

Course plugins are opt-in behavior hooks attached to a reusable `Course`.
They are intentionally lightweight today so research features can evolve without repeated schema churn.

## Current Storage

Plugin state lives on `courses.Course.plugin_config`.

```json
{
  "plugins": {
    "static_recommendations": {
      "enabled": true,
      "settings": {}
    },
    "dynamic_recommendations": {
      "enabled": false,
      "settings": {}
    },
    "guided_sequence": {
      "enabled": false,
      "settings": {}
    },
    "adaptive_branching": {
      "enabled": false,
      "settings": {}
    }
  }
}
```

Use `modulearn.learning.services.course_plugins.normalize_course_plugin_config()` before reading or writing this field. It guarantees all registered plugin keys exist and have the same shape.

## Registry

The user-facing plugin registry is `modulearn.learning.services.course_plugins.AVAILABLE_COURSE_PLUGINS`.

Each registry item must include:

- `key`: stable machine key. Use lowercase snake case.
- `name`: instructor-facing display name.
- `summary`: one-sentence description for the course configuration page.

Do not rename a key after it has shipped. Add a new key and migrate data if semantics change substantially.

## Reading Plugin Flags

Server-side code should use:

- `is_course_plugin_enabled(course, plugin_key)` for one plugin.
- `enabled_course_plugins(course)` for a `{key: bool}` map.

Student-facing course pages receive `course_plugins` from `build_course_detail_context()` and expose the same flags in the DOM as:

```html
<script id="coursePluginFlags" type="application/json">...</script>
```

Client-side overlays can read that script tag before enabling behavior.

## Configuration UI

Instructor toggles live in `courses/templates/courses/course_configuration.html`.
The POST action is `update_plugins`, handled by `courses.views._update_course_plugins()`.

The current UI only exposes binary enable/disable toggles. Plugin-specific settings should still be stored under `settings`, but they need their own UI and validation before use.

## Guided Sequence

`guided_sequence` is a setup accelerator for linear courses.

When an instructor enables it from Course Configuration, ModuLearn applies a default progression:

- all units and modules are made visible
- the first unit remains unlocked
- later units unlock after the previous unit is completed
- the first module remains unlocked
- every later module unlocks after the immediately previous module is completed

This default is applied only when the plugin changes from disabled to enabled. After that, instructors can keep using the normal visibility and lock controls to customize the sequence without later plugin saves overwriting their changes.

Student launch pages use the same access-rule evaluator to show a Next Module button. The button links to the next visible/unlocked module in course order, or renders disabled when no accessible successor exists.

## Adaptive Branching

Conditional flow is implemented as the `adaptive_branching` plugin rather than overloading the existing `unlock_rule` JSON field.

The existing `unlock_rule` field is good for deterministic requirements such as "complete module A before B." Branching is per-student and event-driven: a student outcome on A can unlock B for one learner and C for another. That uses durable per-enrollment unlock state.

Models:

```text
ModuleBranchRule
  course
  source_module
  condition_type          # success, failure, score_gte, score_lt, completed, selected_choice later
  threshold               # nullable number for score rules
  target_module
  priority
  active
  created_at
  updated_at

EnrollmentModuleUnlock
  enrollment
  module
  source_module
  source_rule
  reason
  created_at
```

Event flow:

1. Keep all score/progress writes flowing through `apply_progress_snapshot()`.
2. After a progress/outcome/completion event is logged, `modulearn.learning.services.adaptive_branching.handle_progress_event()` evaluates the event.
3. The plugin evaluates active `ModuleBranchRule` rows for the source module.
4. Matching rules create `EnrollmentModuleUnlock` rows for the target module.
5. `evaluate_module_access()` treats a matching dynamic unlock as sufficient access when the branching plugin is enabled.

Configuration UI:

- Branching setup lives in Course Configuration inside the course plugins modal.
- Author rules as "From module A, if correct unlock B; if incorrect unlock C."
- Saving a new branch target makes that target visible and locked, with no ordinary unlock rule, so the branch unlock controls access.
- Correct/incorrect rules use the normalized event `success` flag. Failure rules require assessment evidence such as a score, so ordinary no-score viewing/progress events do not trigger incorrect-path unlocks.
- Score rules use a 0-100 threshold.

This keeps Guided Sequence as the simple linear default and Adaptive Branching as an optional layer that can open alternate paths for individual students.

## Recommended Plugin Shape

Keep plugin implementation in a service module, not in templates or large views.

Preferred layout:

```text
modulearn/learning/plugins/
  static_recommendations.py
  dynamic_recommendations.py
```

Preferred service API:

```python
def is_enabled(course) -> bool:
    ...

def build_context(*, course, course_instance, user, enrollment=None) -> dict:
    ...

def handle_event(*, event, module_progress=None, payload=None) -> None:
    ...
```

Only add methods that the plugin actually needs. The three hooks above cover the expected recommendation work:

- context building for overlays and queues
- event-driven reactions to wrong answers, low progress, failed modules, or completions
- enablement checks from course config

## Event Sources

Recommendation plugins should treat `ModuleProgressEvent` as the main event ledger.

Useful event types today:

- `launch`
- `progress`
- `completion`
- `outcome`
- `reopened`

Progress writes should continue to flow through `modulearn.learning.services.progress.apply_progress_snapshot()` so plugins can rely on normalized progress, score, success, completion, and timeline data.

## Static Recommendation Sketch

Static recommendation data can live initially in `Module.content_data`, for example:

```json
{
  "recommendations": {
    "on_incorrect": [42, 43],
    "on_low_score": [44]
  }
}
```

When a progress/outcome event reports failure or low success, the plugin can enqueue unfinished target modules for that learner.

If queues need durability, add a dedicated model later, for example:

```text
RecommendationQueueItem
  user
  enrollment
  source_module
  target_module
  reason
  status
  created_at
  dismissed_at
  completed_at
```

## Dynamic Recommendation Sketch

Dynamic recommendations should compute candidates from the current course graph and learner state. Keep the algorithm behind a service function so experiments can swap strategies:

```python
def recommend_after_failure(*, module_progress, event) -> list[Module]:
    ...
```

The first pass can use simple rules such as same unit, earlier order, incomplete modules, or modules sharing tags/provider metadata. Later passes can use model state, activity metadata, or analytics signals.

## Export And Import

Course exports include `plugin_config` and `branch_rules`. Imports preserve plugin settings after normalization and recreate branch rules after units/modules are synced.

This means exported courses can be shared with plugin toggles intact, but plugin-specific settings must remain JSON-serializable and portable across environments.

## Guardrails

- Plugins must default to off.
- Missing plugin config must behave like disabled config.
- Plugin behavior should never hide required core course content unless a course-level instructor setting explicitly says so.
- Plugin code should not mutate progress directly unless it uses the canonical progress service.
- Plugin-specific UI should degrade cleanly if JavaScript does not load.
