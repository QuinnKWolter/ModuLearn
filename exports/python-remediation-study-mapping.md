# Python remediation study: material mapping

Reviewed 2026-10-29. **Ordering and practice pairings approved by Quinn on 2026-10-29.** All 28 supplied catalog records and Cupcake YAML definitions were retrieved. No matching Gillian/Abigail worked-example entries were identified in the 4,130-entry public catalog.

## Participant order

| Order | Original | Additional practice | Pairing rationale / caveat |
|---|---|---|---|
| 1 | [Q09](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q09.yaml?protocol=splice) | [M01](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_m01.yaml?protocol=splice) | Addition within a comparison; M01 changes the branch outcome (strict > at equality). |
| 2 | [Q10](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q10.yaml?protocol=splice) | [M02](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_m02.yaml?protocol=splice) | Subtraction within a comparison; M02 uses < rather than <= and a variable discount. |
| 3 | [Q11](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q11.yaml?protocol=splice) | [M03](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_m03.yaml?protocol=splice) | Multiplication within a comparison; M03 uses == rather than >=. Review this operator change. |
| 4 | [Q12](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q12.yaml?protocol=splice) | [M04](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_m04.yaml?protocol=splice) | Division yielding a float; M04 uses >= at equality rather than >. |
| 5 | [Q13](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q13.yaml?protocol=splice) | [H01](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_h01.yaml?protocol=splice) | Self-update inside an if/else; H01 exercises the if branch while Q13 exercises else. |
| 6 | [Q14](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q14.yaml?protocol=splice) | [H02](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_h02.yaml?protocol=splice) | Two-variable updates; H02 exercises a richer else branch. Review the added update. |
| 7 | [Q15](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q15.yaml?protocol=splice) | [H03](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_h03.yaml?protocol=splice) | Conditional reassignment before use; H03 closely mirrors Q15 with different values. |
| 8 | [Q16](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_q16.yaml?protocol=splice) | [H04](https://adapt2.sis.pitt.edu/cupcake/#/activities/gillian-python/free_coding_h04.yaml?protocol=splice) | Sequential if statements; H04 takes both updates while Q16 skips the second. Second test is < rather than >. |

For each row: incorrect original → assigned condition target → retry original; correct original → next row. Practice targets are populated. Similar examples should demonstrate the paired practice problem; matched examples should explain the original. Those **16 example URLs are still missing**, and their connected placeholders are retained. Do not enable recruitment until they are supplied and pilot-tested.

## All supplied material

| Item | Catalog title | Assigned use |
|---|---|---|
| free_coding_h01 | Updating a variable using its own value (x = x + n) inside a branch | practice |
| free_coding_h02 | Two dependent state updates in a branch | practice |
| free_coding_h03 | Arithmetic condition decides whether a second variable is reassigned before it is used | practice |
| free_coding_h04 | Two sequential if statements where the first update changes the second decision | practice |
| free_coding_h05 | Division in the condition | Reserve / not assigned |
| free_coding_h06 | State updates inside an if/elif/else chain | Reserve / not assigned |
| free_coding_h07 | Swapping two values with a temporary variable inside a branch | Reserve / not assigned |
| free_coding_h08 | Equality check with arithmetic, then a second if/else that depends on the updated value | Reserve / not assigned |
| free_coding_h09 | Multiple sequential updates to one variable plus a string assignment within a branch | Reserve / not assigned |
| free_coding_h10 | Integration: conditional update followed by an if/elif/else on the updated values | Reserve / not assigned |
| free_coding_m01 | Addition inside a comparison | practice |
| free_coding_m02 | Subtraction inside a comparison | practice |
| free_coding_m03 | Multiplication inside an equality comparison (==) vs. assignment (=) | practice |
| free_coding_m04 | Division producing a decimal inside a comparison | practice |
| free_coding_m05 | Multiplication in an if/elif/else chain | Reserve / not assigned |
| free_coding_m06 | Different arithmetic in each condition of an if/elif/else chain | Reserve / not assigned |
| free_coding_m07 | Arithmetic on both sides of a comparison | Reserve / not assigned |
| free_coding_m08 | Division vs. multiplication on opposite sides of a comparison | Reserve / not assigned |
| free_coding_m09 | Order of operations (parentheses vs. * before +) inside a comparison | Reserve / not assigned |
| free_coding_m10 | Division repeated in an if/elif/else chain | Reserve / not assigned |
| free_coding_q09 | Arithmetic expression (addition) evaluated inside if condition | original |
| free_coding_q10 | Arithmetic expression (subtraction) evaluated inside if condition | original |
| free_coding_q11 | Arithmetic expression (multiplication) evaluated inside if condition | original |
| free_coding_q12 | Arithmetic expression (division) evaluated inside if condition | original |
| free_coding_q13 | Single variable updated inside if/else branch | original |
| free_coding_q14 | Two variables both updated inside the if-branch | original |
| free_coding_q15 | Arithmetic in condition must be evaluated first to select branch | original |
| free_coding_q16 | Two sequential independent if/else blocks | original |

## Evidence and limits

- Catalog source: https://adapt2.sis.pitt.edu/next.course-authoring/api/catalog-v2 . Each populated activity stores the catalog record ID and stable provider activity ID in content metadata; URLs use SPLICE. Neutral participant titles retain the slot numbering.
- All 28 reference programs parsed and produced the declared expected stdout under a restricted arithmetic/branch-only local execution check. This is not a live Cupcake submission test.
- All selected original/practice activities currently declare one visible fixed-output test. M09, not selected, also declares one hidden test. Fixed output alone does not establish whether a correct algorithm rather than hard-coded output was submitted.
- Original Q16 says two if/else blocks in its title; its actual second statement has no else. H04 is also a separate second if without else.
- No assignment of reserves to baseline or final test was inferred. Approved questionnaires, consent/debrief, pretest, transfer tasks, rubric, section deadlines and repeat-failure policy still require review.
- Import/export round trip and all 24 canonical-event routing paths are covered by recruitment.tests.test_experiment_template. Actual provider callback pilots remain required.

## Import

Use Manage Studies → Create Study → Optional Template JSON with python-remediation-study-template.json. Edit existing activities in place to keep branch identities. Recruitment is disabled.
