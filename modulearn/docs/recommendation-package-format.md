# Recommendations: setup, formats and tracking

## Instructor setup and session scope

Open **Course Configure → Plugins → Static Recommendations** for the intended session. Prefer a URL-linked CSV or JSON package: upload one, inspect its map, choose failure threshold/per-type limit and presentation, then test with a student. The supplied equivalent deployment artifacts are [CS007 linked CSV](../../ML_Recs/2026-10-11/CS007.linked-recommendations.csv) and [CS007 JSON](../../ML_Recs/2026-10-11/CS007.recommendations.json): 247 activities, 114 source problems, 684 links. Choose one, not both. Neither needs a separate unit import. The machine-readable contract is [package v1 schema](../../ML_Recs/recommendation-package-v1.schema.json).

Datasets, enablement, matching, settings and assignment transitions belong to one **course session**. Course structure remains shared: a missing source imported into the outline is visible to its other sessions. New sessions start without a dataset. Migration 0026 copied formerly shared recommendation settings to independent session datasets and retained a disabled archive; review old sessions for unwanted enabled copies. Back up before migrations; rolling independent datasets back into one shared set is not safe automatically.

Package upload replaces the graph, applies its delivery settings and enables it. Retained assignments keep scores/feedback; removed targets retire with history preserved. Reuploading the same package is idempotent. Toggling off/on is not a reset. Replacing recommendations does not delete previously authored course requirements. Research locks and stale-edit revision checks still apply.

Default failure threshold is one unsuccessful scored attempt, with two recommendations **per type**. Existing datasets retain their own settings. Failures are cumulative. Student assignments stay available after activation; instructor testing provides practice without requiring a failed answer. Instructor data remains separate from students.

## Presentation

Recommendations open in a modal once per page visit when the problem has available assignments, including revisits after activation. Dismissing the modal or selecting an activity animates toward the star and settles the picker into the sidebar. Minimizing the sidebar returns to the original problem and leaves the star available to reopen it. The Return button is inside the panel and only visible during practice; there is no original-problem toolbar.

There is one unified flow, not a Sidebar/Modal choice. Old `display_mode` and `auto_open` settings are ignored and removed on the next settings save. Instructors retain the session-specific animation preference; device reduced-motion preferences take priority. Existing failure thresholds and per-type limits are unchanged.

Cards use yellow for unattempted practice, blue for in-progress practice, and green with a checkmark and crossed-out title for completed practice. Selection has a stronger green outline/fill. Hover text and accessible labels also convey status. Grades and completion come from saved practice records.

The player fits the viewport with independent activity/picker scrolling. On narrow screens the sidebar overlays part of the activity; collapse it to return to the original. Large provider content remains scrollable within its activity pane, including verified provider resize messages.

Research event logs and CSV exports include `modal_open`, `modal_close`, and `launcher_open`, alongside existing sidebar, impression, visit, return, progress, and feedback events. Presentation interactions record `source` and payload `presentation` as `sidebar` or `modal`; open/close reasons are in payload `value`. Panel events are recorded against each available recommendation, so researchers should not sum these rows as unique panel sessions. Existing event IDs make retries idempotent. Instructor testing remains excluded from student analytics, and practice never adds course credit.


## Contract for content authors

```json
{
  "format": "modulearn.recommendations.v1",
  "title": "Example course recommendations",
  "settings": {"incorrect_attempts": 1, "per_type": 2},
  "activities": [
    {"id": "problem-1", "title": "A problem", "unit": "Arrays",
     "provider": "cupcake", "url": "https://content.example/problem",
     "protocols": ["splice"], "code": "optional source code"},
    {"id": "example-1", "title": "An example", "unit": "Arrays",
     "provider": "cupcake", "url": "https://content.example/example",
     "protocols": ["splice"]}
  ],
  "recommendations": [
    {"source": "problem-1", "target": "example-1", "type": "worked_example", "rank": 1}
  ]
}
```

- UTF-8 JSON, at most 10 MiB; 1–5000 activities, 1–20000 links.
- Activity IDs are unique stable strings (letters, digits, underscore, dot, hyphen; 1–100 characters). Reference the same ID wherever the same activity occurs. One ID per distinct delivery URL. Same-title activities with different content must have different IDs **and URLs**.
- `title`, `unit`, `provider`: nonempty strings up to 255 characters. `provider` describes the actual execution platform, independently of recommendation type. `code` is optional text for inspection.
- `url`: full HTTP(S) delivery URL, at most 200 characters (the current module storage limit), without embedded credentials; preserve meaningful query parameters and fragments. Prefer the published SPLICE delivery URL. No temporary session, learner, or authorization parameters. The importer validates syntax but does not execute or fetch the URL; authors must verify delivery and tracking compatibility.
- `protocols`: nonempty list drawn from `splice`, `html`, `pitt`, `lti`. Use the protocol actually supported by that URL; listing a protocol does not add support to the provider.
- Link `type`: `animation` → Animations; `worked_example` → Worked Examples; `completion_problem` → Completion Problems.
- `rank`: integer 1–1000; lower is preferred. Unique within each source/type; no duplicate source/target pairs or self-links. Every activity must participate in a link. No similarity, clusters, embeddings or medoids are required.
- Settings are optional: `incorrect_attempts` defaults to 1 (range 1–100), `per_type` defaults to 2 (range 1–30). Upload replaces delivery settings, removes any prior similarity cutoff and enables the plugin.

## Import behavior and safeguards

Installation is atomic. Match existing content by normalized delivery URL (query ordering ignored, content parameters and fragments preserved). Repeated placements of the same URL are supported: every ordinary source placement can trigger recommendations, with its own attempts and practice history. Targets use one stable representative placement, retaining the previous binding when available, so duplicates do not create duplicate recommendation cards. A manual source match replaces its imported placement aliases. Titles alone never identify an exercise. Same-title/different-URL conflicts, ambiguous unit creation, invalid graphs and research-locked courses reject installation without partial writes.

Missing activities used as `source` are added as ordinary course requirements in their named units. Other missing activities are created as recommendation-only practice. Existing course modules remain ordinary course modules when also recommended; their recommendation attempts use separate practice records and do not award course credit. Existing visibility, locking, content and histories are preserved. Hidden targets remain excluded from delivery until made available; already-activated assignments must be refreshed after visibility changes using the existing transition tool.

The package completely replaces the recommendation graph. Already-activated assignments transition automatically inside the same transaction: retained targets keep their practice IDs, scores and feedback; removed targets are retired, with all history preserved. Repeat uploads do not duplicate modules, reset progress or create redundant transition events. Every upload records a durable admin audit receipt with instructor, course, checksum and result counts. Changed assignments also receive `dataset_transition` research events.

Existing platform logging and outcome adapters handle activity execution. Unknown provider messages remain logs rather than guessed grades. Package imports do not alter normal course attempt events or grade histories.

## Instructor monitoring

The recommendation research logs page now also includes **Normal course activity**: paginated course events with payload inspection and a separate course CSV download. Student/activity search and event filters apply to both contexts. Existing recommendation event and practice-summary downloads retain views, visits, attempts, scores, completion, feedback, original problem, enrollment and retirement history. Only instructors for that class can view or export these records.

Rank-only packages use `ranking_method=explicit_rank` in research exports; `similarity` is blank. Legacy cosine-based datasets keep their existing value and report `cosine_similarity`. The internal ordering score for packages is merely reciprocal rank, never a model estimate or student grade. Historical transition payloads preserve before/after configurations.


## Columns

`format,source_id,source_title,source_unit,source_provider,source_url,source_protocols,target_id,target_title,target_unit,target_provider,target_url,target_protocols,type,rank,incorrect_attempts,per_type`

- `format` is `modulearn.recommendations.csv.v1` on every row.
- Repeated IDs must have identical title, unit, provider, URL and protocols on every row.
- Protocols use `|` if multiple are supported (e.g. `splice|html`). Prefer a verified SPLICE delivery URL.
- `type` is `animation`, `worked_example`, or `completion_problem`.
- `rank` is the preference within this problem/type (1 is first); ranks must not repeat within a problem/type.
- Both setting columns must be identical across all rows.
- UTF-8 CSV, ordinary CSV quoting, 10 MiB maximum. The JSON package's URL/identity/graph constraints also apply; see the contract above.


## Legacy research CSVs and matching

The `ML_Recs/email1` and `email2` files remain original research inputs, not course exports. Wide recommendation rows contain query metadata and ranked animation/PCEX/QuizJET candidates, but generally lack delivery URLs. Optional assignments and medoids describe code patterns/clusters; their `Score` and vectors are not student grades. Keep files from one course/generation together; cluster numbers are not stable across generations.

Legacy imports use tiered matching: explicit bindings/identifiers where available, normalized title/provider/topic, then a unique course-title fallback when labels are inconsistent. A unique title can help with mislabeled providers; duplicate content variants must remain unresolved unless disambiguated. Code text is not a stable delivery identifier. Review every unresolved activity; excluded endpoints cannot yield deliverable recommendations. Prefer linked packages for production rather than relying on title guessing.

## Tracking and separation

Each assignment belongs to an enrollment and original problem, even when its target also appears as ordinary coursework. Practice UUIDs are validated against that context. Practice grades/completion do not update course progress, unlock course branches, forward course credit or trigger recursive recommendations. Original frames stay mounted while switching practice.

Events retain source attempts, activation, impressions, visits, returns, launch/focus/frame interactions, raw provider messages, scored attempts, completion and feedback (up/down/skipped). Unanswered prompts remain distinguishable from skipped feedback. Summaries include unvisited items. Exports are paginated/streamed and escape spreadsheet formula prefixes. `ranking_method` distinguishes explicit rank from legacy cosine similarity; reciprocal ordering scores are not research confidence estimates.

## Production check

Deploy code, migrations, translations and static assets together. Upload the linked file to the intended session, check the resolved map, submit an incorrect answer as a test student, visit/complete practice and inspect both course and practice logs. Check that another session is unchanged and course credit does not increase from practice. Provider availability still needs separate verification; importing a URL does not certify its grading integration.
