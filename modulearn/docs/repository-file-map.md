# Repository file map

Snapshot: 2026-09-24, commit `3db42ee` plus existing documentation changes. Companion: [review and maintenance handoff](repository-review-2026-09-24.md).

This map covers all **260 baseline project files** (2,498,721 bytes; 55,522 text lines). It includes the three documentation files that were untracked when the review began. The review and this generated map are subsequent additions. Symbol line numbers describe this snapshot and will drift as code changes.

Python entries list top-level classes/functions, not every method. Migration entries summarize operation types. Template entries list explicit inheritance/includes and structural counts, not a claim of browser validation. Environment/key values are excluded. Empty initializers remain listed so directory coverage is explicit.

## Directories outside the source inventory

| Location | Role and review boundary |
|---|---|
| `modulearn-storage/db/db.sqlite3` | Configured active local SQLite database; inspected read-only for schema/migration state. |
| `modulearn/db.sqlite3` | Obsolete local SQLite database with older schema; not the configured application database. |
| `modulearn-storage/media/` | Persistent uploaded content; empty during review. |
| `modulearn/staticfiles/` | Generated collected assets; source behavior comes from templates, static assets and build inputs. |
| `modulearn/node_modules/` | Installed third-party frontend dependencies; not original application source. |
| `_tmp_slc_catalog_crawl_20260710/` | Ignored historical catalog crawl, helper scripts and generated outputs used for URL replacement analysis; not runtime code. |
| `.venv/`, `__pycache__/`, logs and caches | Local environments/generated runtime and review artifacts; not source deliverables. |
| `.git/` | Repository metadata; HEAD/history/status inspected, object storage not application source. |

## Coverage by group

| Group | Files | Text lines |
|---|---:|---:|
| Repository root and deployment | 5 | 137 |
| Application root and build configuration | 10 | 1,246 |
| accounts | 28 | 2,612 |
| courses | 45 | 15,950 |
| dashboard | 36 | 13,664 |
| data | 1 | 1 |
| docs | 14 | 1,388 |
| lti | 21 | 3,830 |
| main | 13 | 264 |
| Project package: settings, routing and integration controllers | 9 | 3,237 |
| Project package: core | 5 | 273 |
| Project package: integrations | 3 | 55 |
| Project package: learning | 13 | 1,710 |
| recruitment | 28 | 4,022 |
| static | 18 | 6,638 |
| static_src | 1 | 3 |
| templates | 10 | 492 |

## Repository root and deployment

| File | Lines | Contents / role |
|---|---:|---|
| [.env](../../.env) | — | Tracked environment configuration; values intentionally not reproduced. |
| [.gitignore](../../.gitignore) | 47 | Source-control exclusions; tracked files are not untracked by ignore rules. |
| [docker/docker-compose.local.yml](../../docker/docker-compose.local.yml) | 25 | Local container build and development server; no source bind mount. |
| [docker/docker-compose.yml](../../docker/docker-compose.yml) | 30 | Production deployment-root paths, environment, storage and port mapping. |
| [docker/reload-from-github.sh](../../docker/reload-from-github.sh) | 35 | Deployment checkout replacement, rebuild/restart and static copy script. |

## Application root and build configuration

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/.dockerignore](../../modulearn/.dockerignore) | 37 | Container build-context exclusions. |
| [modulearn/COURSE_CONFIGURATION_TODOS.md](../../modulearn/COURSE_CONFIGURATION_TODOS.md) | 20 | Documentation: Course Configuration TODOs; Audit; Implementation TODOs. |
| [modulearn/Dockerfile](../../modulearn/Dockerfile) | 40 | Node CSS build stage and Python/Gunicorn application image. |
| [modulearn/README.md](../../modulearn/README.md) | 48 | Documentation: ModuLearn; Project layout; Internal domain packages; Key refactor outcomes; Documentation; additional sections. |
| [modulearn/docker-entrypoint.sh](../../modulearn/docker-entrypoint.sh) | 7 | Container startup, migrations and static collection. |
| [modulearn/manage.py](../../modulearn/manage.py) | 22 | Django management command entry point. |
| [modulearn/package-lock.json](../../modulearn/package-lock.json) | 1028 | Locked Node dependency graph. |
| [modulearn/package.json](../../modulearn/package.json) | 12 | Tailwind build/watch commands and dependency declaration. |
| [modulearn/requirements.txt](../../modulearn/requirements.txt) | 15 | Python dependency requirements; only partly pinned. |
| [modulearn/tailwind.config.js](../../modulearn/tailwind.config.js) | 17 | Tailwind template/script scan paths and dark-mode configuration. |

## accounts

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/accounts/KNOWLEDGETREE_AUTHENTICATION_FIELDS.md](../../modulearn/accounts/KNOWLEDGETREE_AUTHENTICATION_FIELDS.md) | 140 | Documentation: KnowledgeTree Authentication Fields; Database Tables and Fields; Primary Table: `ent_user`; Related Table: `rel_user_user`; API Authentication Fields; additional sections. |
| [modulearn/accounts/KNOWLEDGETREE_AUTH_README.md](../../modulearn/accounts/KNOWLEDGETREE_AUTH_README.md) | 189 | Documentation: KnowledgeTree Authentication Integration; Overview; Features; Configuration; Environment Variables; additional sections. |
| [modulearn/accounts/KNOWLEDGETREE_INTEGRATION_CHANGES.md](../../modulearn/accounts/KNOWLEDGETREE_INTEGRATION_CHANGES.md) | 134 | Documentation: KnowledgeTree Integration - Seamless Authentication Changes; Summary of Changes; Changes Made; 1. Removed Checkbox from Login Form; 2. Automatic Authentication Fallback; additional sections. |
| [modulearn/accounts/__init__.py](../../modulearn/accounts/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/accounts/admin.py](../../modulearn/accounts/admin.py) | 4 | Django admin registration/configuration. |
| [modulearn/accounts/apps.py](../../modulearn/accounts/apps.py) | 6 | Symbols (snapshot line): `AccountsConfig:4`. |
| [modulearn/accounts/backends.py](../../modulearn/accounts/backends.py) | 222 | Symbols (snapshot line): `EmailCaseInsensitiveBackend:16`, `KnowledgeTreeBackend:33`. |
| [modulearn/accounts/email_utils.py](../../modulearn/accounts/email_utils.py) | 43 | Symbols (snapshot line): `normalize_email_address:8`, `emails_equal:13`, `find_user_by_email:18`, `unique_username_for_email:27`, `unique_username_from_base:33`. |
| [modulearn/accounts/forms.py](../../modulearn/accounts/forms.py) | 153 | Symbols (snapshot line): `SignUpForm:7`, `LoginForm:38`, `ProfileEditForm:43`, `PasswordChangeFormCustom:69`, `SetPasswordFormCustom:88`, `KnowledgeTreePasswordResetForm:106`, `KnowledgeTreeProvisionForm:148`. |
| [modulearn/accounts/knowledgetree_auth.py](../../modulearn/accounts/knowledgetree_auth.py) | 522 | Symbols (snapshot line): `KnowledgeTreeAuthError:20`, `KnowledgeTreeAPIConnectionError:25`, `KnowledgeTreeAuthenticationFailed:30`, `KnowledgeTreeAuthService:35`. |
| [modulearn/accounts/migrations/0001_initial.py](../../modulearn/accounts/migrations/0001_initial.py) | 48 | Migration: CreateModel (1). |
| [modulearn/accounts/migrations/0002_user_course_authoring_password_user_full_name_and_more.py](../../modulearn/accounts/migrations/0002_user_course_authoring_password_user_full_name_and_more.py) | 35 | Migration: AddField (2), AlterField (2). |
| [modulearn/accounts/migrations/0003_user_kt_groups_user_kt_login_user_kt_user_id.py](../../modulearn/accounts/migrations/0003_user_kt_groups_user_kt_login_user_kt_user_id.py) | 28 | Migration: AddField (3). |
| [modulearn/accounts/migrations/0004_alter_user_kt_login_alter_user_kt_user_id.py](../../modulearn/accounts/migrations/0004_alter_user_kt_login_alter_user_kt_user_id.py) | 23 | Migration: AlterField (2). |
| [modulearn/accounts/migrations/0005_make_user_roles_exclusive.py](../../modulearn/accounts/migrations/0005_make_user_roles_exclusive.py) | 17 | Migration: RunPython (1). |
| [modulearn/accounts/migrations/0006_user_is_anonymous_participant.py](../../modulearn/accounts/migrations/0006_user_is_anonymous_participant.py) | 16 | Migration: AddField (1). |
| [modulearn/accounts/migrations/0007_normalize_user_emails.py](../../modulearn/accounts/migrations/0007_normalize_user_emails.py) | 19 | Migration: RunPython (1). |
| [modulearn/accounts/migrations/0008_remove_duplicate_user_emails.py](../../modulearn/accounts/migrations/0008_remove_duplicate_user_emails.py) | 31 | Migration: RunPython (1). |
| [modulearn/accounts/migrations/0009_alter_user_options_and_more.py](../../modulearn/accounts/migrations/0009_alter_user_options_and_more.py) | 23 | Migration: AlterModelOptions (1), AddConstraint (1). |
| [modulearn/accounts/migrations/__init__.py](../../modulearn/accounts/migrations/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/accounts/models.py](../../modulearn/accounts/models.py) | 61 | Symbols (snapshot line): `User:9`. |
| [modulearn/accounts/templates/accounts/login.html](../../modulearn/accounts/templates/accounts/login.html) | 21 | Django template; extends/includes `base.html`, `includes/tailwind_form.html`; 1 form tags; 0 inline script blocks. |
| [modulearn/accounts/templates/accounts/profile.html](../../modulearn/accounts/templates/accounts/profile.html) | 243 | Django template; extends/includes `base.html`, `includes/tailwind_form.html`, `dashboard/components/course_resources_modal.html`; 5 form tags; 0 inline script blocks. |
| [modulearn/accounts/templates/accounts/signup.html](../../modulearn/accounts/templates/accounts/signup.html) | 90 | Django template; extends/includes `base.html`; 1 form tags; 0 inline script blocks. |
| [modulearn/accounts/templates/registration/login.html](../../modulearn/accounts/templates/registration/login.html) | 1 | Django template; extends/includes `accounts/login.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/accounts/tests.py](../../modulearn/accounts/tests.py) | 216 | 15 test methods. Symbols (snapshot line): `AccountPageTests:20`, `KnowledgeTreeBackendRoleTests:135`. |
| [modulearn/accounts/urls.py](../../modulearn/accounts/urls.py) | 11 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/accounts/views.py](../../modulearn/accounts/views.py) | 316 | Symbols (snapshot line): `_default_full_name_for_user:21`, `_ensure_kt_user_exists:34`, `signup:111`, `login_view:140`, `logout_view:201`, `profile_view:206`. |

## courses

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/courses/MODULE_TESTING_ANALYSIS.md](../../modulearn/courses/MODULE_TESTING_ANALYSIS.md) | 386 | Documentation: Module Testing Analysis - Course Content Compatibility; Test Course: "Testing the Course Authoring Tool"; Critical Bugs Identified; Bug #1: HTTP Proxy Not Being Used; Current (broken):; additional sections. |
| [modulearn/courses/PROTOCOL_INFRASTRUCTURE.md](../../modulearn/courses/PROTOCOL_INFRASTRUCTURE.md) | 214 | Documentation: ModuLearn Protocol Infrastructure; Overview; Protocol Selection; 1. SPLICE Protocol; What It Is; additional sections. |
| [modulearn/courses/__init__.py](../../modulearn/courses/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/courses/admin.py](../../modulearn/courses/admin.py) | 98 | Symbols (snapshot line): `CourseAdmin:22`, `CourseInstanceAdmin:27`, `EnrollmentCodeAdmin:31`, `UnitAdmin:36`, `ModuleAdmin:43`, `ModuleFormQuestionInline:50`, `ModuleFormAdmin:55`, `ModuleAccessLogAdmin:60`, `ModuleProgressEventAdmin:66`, `ModuleBranchRuleAdmin:73`, `EnrollmentModuleUnlockAdmin:79`. |
| [modulearn/courses/apps.py](../../modulearn/courses/apps.py) | 6 | Symbols (snapshot line): `CoursesConfig:4`. |
| [modulearn/courses/demo_courses.py](../../modulearn/courses/demo_courses.py) | 458 | Symbols (snapshot line): `_intro_demo_module_specs:120`, `_repair_intro_python_demo_course:169`, `_repair_adaptive_branching_demo_course:209`, `repair_demo_courses_for_instructor:262`, `create_intro_python_demo_course:269`, `instructor_has_intro_python_demo_course:323`, `create_adaptive_branching_demo_course:330`, `instructor_has_adaptive_branching_demo_course:417`, `available_demo_course_options:442`, `create_demo_course_for_key:451`. |
| [modulearn/courses/migrations/0001_initial.py](../../modulearn/courses/migrations/0001_initial.py) | 159 | Migration: swappable_dependency (1), CreateModel (10), AddIndex (1). |
| [modulearn/courses/migrations/0002_module_provider_id_module_supported_protocols.py](../../modulearn/courses/migrations/0002_module_provider_id_module_supported_protocols.py) | 23 | Migration: AddField (2). |
| [modulearn/courses/migrations/0003_progress_timeline_events.py](../../modulearn/courses/migrations/0003_progress_timeline_events.py) | 58 | Migration: swappable_dependency (1), AddField (2), CreateModel (1), AddIndex (3). |
| [modulearn/courses/migrations/0004_rename_courses_mod_user_id_37248b_idx_courses_mod_user_id_6b95a0_idx_and_more.py](../../modulearn/courses/migrations/0004_rename_courses_mod_user_id_37248b_idx_courses_mod_user_id_6b95a0_idx_and_more.py) | 28 | Migration: RenameIndex (3). |
| [modulearn/courses/migrations/0005_moduleaccesslog_moduleform_moduleformanswer_and_more.py](../../modulearn/courses/migrations/0005_moduleaccesslog_moduleform_moduleformanswer_and_more.py) | 240 | Migration: swappable_dependency (1), CreateModel (5), AlterModelOptions (2), AddField (21), RunPython (1), AddIndex (9), AlterUniqueTogether (1). |
| [modulearn/courses/migrations/0006_alter_module_module_type_and_more.py](../../modulearn/courses/migrations/0006_alter_module_module_type_and_more.py) | 23 | Migration: AlterField (2). |
| [modulearn/courses/migrations/0006_course_is_locked_for_research.py](../../modulearn/courses/migrations/0006_course_is_locked_for_research.py) | 16 | Migration: AddField (1). |
| [modulearn/courses/migrations/0007_alter_module_module_type.py](../../modulearn/courses/migrations/0007_alter_module_module_type.py) | 18 | Migration: AlterField (1). |
| [modulearn/courses/migrations/0008_merge_20260525_1114.py](../../modulearn/courses/migrations/0008_merge_20260525_1114.py) | 14 | Symbols (snapshot line): `Migration:6`. |
| [modulearn/courses/migrations/0009_alter_moduleprogressevent_event_type.py](../../modulearn/courses/migrations/0009_alter_moduleprogressevent_event_type.py) | 18 | Migration: AlterField (1). |
| [modulearn/courses/migrations/0010_course_plugin_config.py](../../modulearn/courses/migrations/0010_course_plugin_config.py) | 18 | Migration: AddField (1). |
| [modulearn/courses/migrations/0011_adaptive_branching.py](../../modulearn/courses/migrations/0011_adaptive_branching.py) | 55 | Migration: CreateModel (2). |
| [modulearn/courses/migrations/0012_normalize_enrollment_code_emails.py](../../modulearn/courses/migrations/0012_normalize_enrollment_code_emails.py) | 33 | Migration: RunPython (1). |
| [modulearn/courses/migrations/0013_alter_enrollmentcode_unique_together_and_more.py](../../modulearn/courses/migrations/0013_alter_enrollmentcode_unique_together_and_more.py) | 22 | Migration: AlterUniqueTogether (1), AddConstraint (1). |
| [modulearn/courses/migrations/0014_alter_module_module_type.py](../../modulearn/courses/migrations/0014_alter_module_module_type.py) | 18 | Migration: AlterField (1). |
| [modulearn/courses/migrations/0015_moduleprogress_study_condition_and_more.py](../../modulearn/courses/migrations/0015_moduleprogress_study_condition_and_more.py) | 60 | Migration: AddField (4), RunPython (1). |
| [modulearn/courses/migrations/0016_modulebranchrule_required_study_condition_and_more.py](../../modulearn/courses/migrations/0016_modulebranchrule_required_study_condition_and_more.py) | 22 | Migration: AddField (1), AddIndex (1). |
| [modulearn/courses/migrations/0017_module_progress_attention_events.py](../../modulearn/courses/migrations/0017_module_progress_attention_events.py) | 18 | Migration: AlterField (1). |
| [modulearn/courses/migrations/0018_alter_module_module_type_label.py](../../modulearn/courses/migrations/0018_alter_module_module_type_label.py) | 33 | Migration: AlterField (1). |
| [modulearn/courses/migrations/0019_module_allow_resubmission.py](../../modulearn/courses/migrations/0019_module_allow_resubmission.py) | 16 | Migration: AddField (1). |
| [modulearn/courses/migrations/0020_normalize_legacy_study_form_modules.py](../../modulearn/courses/migrations/0020_normalize_legacy_study_form_modules.py) | 149 | Migration: RunPython (1), AlterField (1). |
| [modulearn/courses/migrations/__init__.py](../../modulearn/courses/migrations/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/courses/models.py](../../modulearn/courses/models.py) | 946 | Symbols (snapshot line): `Course:26`, `CourseInstance:45`, `Unit:83`, `Module:108`, `ModuleBranchRule:227`, `Enrollment:270`, `EnrollmentModuleUnlock:283`, `ModuleProgress:302`, `StudentScore:556`, `CaliperEvent:562`, `EnrollmentCode:568`, `CourseProgress:615`, `ModuleForm:751`, `ModuleFormQuestion:763`, `ModuleFormSubmission:797`, `ModuleFormAnswer:816`, `ModuleAccessLog:829`, `ModuleProgressEvent:864`, `create_module_progress_records:914`. |
| [modulearn/courses/templates/courses/components/adaptive_branching_flow_modal.html](../../modulearn/courses/templates/courses/components/adaptive_branching_flow_modal.html) | 213 | Django template; 1 form tags; 0 inline script blocks. |
| [modulearn/courses/templates/courses/components/next_module_button.html](../../modulearn/courses/templates/courses/components/next_module_button.html) | 12 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/courses/templates/courses/course_configuration.html](../../modulearn/courses/templates/courses/course_configuration.html) | 5184 | Django template; extends/includes `base.html`, `includes/page_header.html`, `courses/components/adaptive_branching_flow_modal.html`; 6 form tags; 1 inline script blocks. |
| [modulearn/courses/templates/courses/course_detail.html](../../modulearn/courses/templates/courses/course_detail.html) | 789 | Django template; extends/includes `base.html`, `includes/page_header.html`, `includes/timeline_panel.html`; 1 form tags; 1 inline script blocks. |
| [modulearn/courses/templates/courses/create_semester_course.html](../../modulearn/courses/templates/courses/create_semester_course.html) | 84 | Django template; extends/includes `base.html`; 1 form tags; 1 inline script blocks. |
| [modulearn/courses/templates/courses/enroll_with_code.html](../../modulearn/courses/templates/courses/enroll_with_code.html) | 35 | Django template; extends/includes `base.html`, `includes/page_header.html`; 1 form tags; 0 inline script blocks. |
| [modulearn/courses/templates/courses/module_detail.html](../../modulearn/courses/templates/courses/module_detail.html) | 61 | Django template; extends/includes `base.html`, `includes/page_header.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/courses/templates/courses/module_form.html](../../modulearn/courses/templates/courses/module_form.html) | 169 | Django template; extends/includes `base.html`, `includes/page_header.html`; 1 form tags; 0 inline script blocks. |
| [modulearn/courses/templates/courses/module_frame.html](../../modulearn/courses/templates/courses/module_frame.html) | 72 | Django template; extends/includes `content_base.html`, `courses/components/next_module_button.html`; 0 form tags; 1 inline script blocks. |
| [modulearn/courses/templates/courses/module_resource.html](../../modulearn/courses/templates/courses/module_resource.html) | 94 | Django template; extends/includes `base.html`, `includes/page_header.html`, `courses/components/next_module_button.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/courses/templatetags/__init__.py](../../modulearn/courses/templatetags/__init__.py) | 1 | Python package initializer. |
| [modulearn/courses/templatetags/course_tags.py](../../modulearn/courses/templatetags/course_tags.py) | 14 | Symbols (snapshot line): `get_item:6`. |
| [modulearn/courses/tests.py](../../modulearn/courses/tests.py) | 2009 | 73 test methods. Symbols (snapshot line): `DummySession:57`, `CourseProgressTests:61`. |
| [modulearn/courses/urls.py](../../modulearn/courses/urls.py) | 46 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/courses/utils.py](../../modulearn/courses/utils.py) | 1102 | Symbols (snapshot line): `normalize_module_type:54`, `_normalize_study_step:60`, `_study_step_from_content_data:64`, `_default_form_payload:71`, `_resource_metadata_by_id:149`, `_activity_platform_name:163`, `unwrap_course_export_payload:183`, `should_clone_import_payload:198`, `_safe_identifier_fragment:208`, `_generated_course_id:218`, `_unit_title:223`, `_module_entries_for_unit:227`, `_form_payload_from_activity:252`, `_sync_module_form:266`, `ensure_module_form:299`, `_content_file_export_payload:324`, `_restore_content_file:353`, `_portable_unlock_rule:371`, `_resolve_unlock_rule:389`, `_serialize_module_form:418`, `fetch_course_details:443`, `create_course_from_json:487`, `export_course_to_json:719`, `send_grade_to_canvas:842`, `reset_course_authoring_password:874`, `get_course_auth_token:889`. |
| [modulearn/courses/views.py](../../modulearn/courses/views.py) | 2916 | Symbols (snapshot line): `force_https_url:105`, `is_pcex_url:120`, `should_proxy_intercepted_activity_url:142`, `to_path_style_proxy:152`, `_is_course_instructor:172`, `_get_active_enrollment:176`, `_parse_bool:180`, `_user_can_access_module:184`, `_get_next_accessible_module:196`, `_redirect_after_module_completion:224`, `_serialize_course_instructor:237`, `_course_instructor_payload:252`, `_add_instructor_to_course_and_sessions:257`, `_remove_instructor_from_course_and_sessions:266`, `_module_rule_context:275`, `_course_research_conditions:309`, `course_list:320`, `course_detail:335`, `course_configuration:371`, `_course_configuration_context:459`, `export_course:486`, `course_instructors:515`, `add_course_instructor:531`, `remove_course_instructor:572`, `_update_course_structure_controls:597`, `_remove_deleted_module_unlock_references:677`, `_parse_protocol_list:700`, `_clean_content_data_after_url_edit:709`, `_update_module_content_configuration:717`, `_update_module_form_configuration:776`, `_update_form_question_from_post:817`, `_update_new_form_question_from_post:847`, `_parse_question_options:861`, `_normalize_unlock_settings:869`, `_branch_module_options:900`, `_branch_rule_context:908`, `_update_branching_rules:916`, `_update_course_plugins:998`, `_apply_guided_sequence_defaults:1017`, `_create_manual_unit:1042`, `_create_custom_module:1058`, `_create_form_questions:1120`, `module_detail:1148`, `unenroll:1179`, `create_course:1198`, `launch_iframe_module:1224`, `_handle_form_module:1578`, `next_accessible_module:1683`, `record_module_session_event_view:1711`, `preview_iframe_module:1767`, `log_lti_response:1970`, `LTIOutcomesView:1997`, `CaliperAnalyticsView:2031`, `enroll_with_code:2054`, `create_enrollment_code:2121`, `update_module_progress:2199`, `duplicate_course_instance:2278`, `check_group_name:2315`, `create_course_instance:2346`, `course_details:2412`, `delete_course:2458`, `get_course_enrollments:2486`, `_enrollment_response_payload:2519`, `_unique_generated_student_username:2539`, `_generated_student_password:2553`, `bulk_enroll_students:2561`, `generate_anonymous_students:2674`, `remove_enrollment:2767`, `delete_course_instance:2801`, `create_semester_course:2833`, `create_raw_course_session:2861`. |

## dashboard

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/dashboard/AUTO_GROUP_COURSE_LOADING.md](../../modulearn/dashboard/AUTO_GROUP_COURSE_LOADING.md) | 198 | Documentation: Automatic Group and Course ID Loading - Implementation Summary; Overview; Implementation Details; Backend Components; Frontend Components; additional sections. |
| [modulearn/dashboard/KNOWLEDGETREE_COURSE_ID_QUESTIONS.md](../../modulearn/dashboard/KNOWLEDGETREE_COURSE_ID_QUESTIONS.md) | 91 | Documentation: Questions for KnowledgeTree Developer - Course ID Discovery; Current Implementation Issue; Questions; 1. Direct Database Query; 2. API Endpoint for Course IDs; additional sections. |
| [modulearn/dashboard/__init__.py](../../modulearn/dashboard/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/dashboard/admin.py](../../modulearn/dashboard/admin.py) | 0 | Django admin registration/configuration. |
| [modulearn/dashboard/apps.py](../../modulearn/dashboard/apps.py) | 6 | Symbols (snapshot line): `DashboardConfig:4`. |
| [modulearn/dashboard/db_queries.py](../../modulearn/dashboard/db_queries.py) | 956 | Symbols (snapshot line): `_float_or_zero:19`, `_int_or_zero:26`, `activity_progress_has_signal:33`, `serialize_activity_progress_values:44`, `get_class_list_from_db:63`, `get_course_structure_from_db:157`, `parse_computed_model:350`, `fetch_all_students_analytics:461`, `get_student_progress_from_db:659`, `build_analytics_response:720`, `get_all_students_progress_from_db:878`. |
| [modulearn/dashboard/kt_db_connection.py](../../modulearn/dashboard/kt_db_connection.py) | 213 | Symbols (snapshot line): `DatabaseConnection:22`, `get_paws_db_connection:157`, `get_kt_db_connection:205`, `get_aggregate_db_connection:210`. |
| [modulearn/dashboard/kt_utils.py](../../modulearn/dashboard/kt_utils.py) | 1096 | Symbols (snapshot line): `get_kt_login_url:16`, `has_kt_session:38`, `_get_proxied_url:55`, `get_kt_user_id_by_login:104`, `update_kt_password:159`, `lookup_user_instructor_status_in_aggregate:233`, `is_user_instructor_in_aggregate:284`, `get_instructor_group_ids:292`, `get_user_groups_from_kt_db:338`, `get_course_ids_from_aggregate_db:400`, `get_user_groups_with_course_ids:461`, `get_masterygrids_node_ids_batch:552`, `get_user_groups_with_masterygrids_nodes:696`, `get_course_id_for_group:749`, `get_course_resources:771`. |
| [modulearn/dashboard/models.py](../../modulearn/dashboard/models.py) | 0 | Supporting source/configuration; see linked file. |
| [modulearn/dashboard/templates/dashboard/components/analytics_renderer.html](../../modulearn/dashboard/templates/dashboard/components/analytics_renderer.html) | 1180 | Django template; 0 form tags; 1 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/course_instance_card.html](../../modulearn/dashboard/templates/dashboard/components/course_instance_card.html) | 46 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/course_instances_section.html](../../modulearn/dashboard/templates/dashboard/components/course_instances_section.html) | 23 | Django template; extends/includes `dashboard/components/course_instance_card.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/course_resources_modal.html](../../modulearn/dashboard/templates/dashboard/components/course_resources_modal.html) | 34 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/courses_section.html](../../modulearn/dashboard/templates/dashboard/components/courses_section.html) | 35 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/dashboard_kpi_cards.html](../../modulearn/dashboard/templates/dashboard/components/dashboard_kpi_cards.html) | 70 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/dashboard_mastery_grid.html](../../modulearn/dashboard/templates/dashboard/components/dashboard_mastery_grid.html) | 132 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/dashboard_modals.html](../../modulearn/dashboard/templates/dashboard/components/dashboard_modals.html) | 99 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/dashboard_scripts.html](../../modulearn/dashboard/templates/dashboard/components/dashboard_scripts.html) | 2264 | Django template; 0 form tags; 1 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/dashboard_styles.html](../../modulearn/dashboard/templates/dashboard/components/dashboard_styles.html) | 1138 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/legacy_courses_section.html](../../modulearn/dashboard/templates/dashboard/components/legacy_courses_section.html) | 34 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/legacy_dashboard_header.html](../../modulearn/dashboard/templates/dashboard/components/legacy_dashboard_header.html) | 89 | Django template; 1 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/modals.html](../../modulearn/dashboard/templates/dashboard/components/modals.html) | 600 | Django template; extends/includes `dashboard/components/modals/import_json_modal.html`; 4 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/modals/import_json_modal.html](../../modulearn/dashboard/templates/dashboard/components/modals/import_json_modal.html) | 77 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/modulearn_dashboard_fetcher.html](../../modulearn/dashboard/templates/dashboard/components/modulearn_dashboard_fetcher.html) | 100 | Django template; 0 form tags; 1 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/modulearn_dashboard_header.html](../../modulearn/dashboard/templates/dashboard/components/modulearn_dashboard_header.html) | 54 | Django template; 1 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/recruitment_panel.html](../../modulearn/dashboard/templates/dashboard/components/recruitment_panel.html) | 12 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/session_accordion_item.html](../../modulearn/dashboard/templates/dashboard/components/session_accordion_item.html) | 125 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/components/session_management_section.html](../../modulearn/dashboard/templates/dashboard/components/session_management_section.html) | 29 | Django template; extends/includes `dashboard/components/session_accordion_item.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/instructor_dashboard.html](../../modulearn/dashboard/templates/dashboard/instructor_dashboard.html) | 1679 | Django template; extends/includes `base.html`, `dashboard/components/legacy_courses_section.html`, `dashboard/components/modals.html`, `dashboard/components/course_resources_modal.html`, `dashboard/components/session_accordion_item.html`; 5 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/legacy_dashboard.html](../../modulearn/dashboard/templates/dashboard/legacy_dashboard.html) | 43 | Django template; extends/includes `base.html`, `dashboard/components/legacy_dashboard_header.html`, `dashboard/components/dashboard_kpi_cards.html`, `dashboard/components/dashboard_mastery_grid.html`, `dashboard/components/dashboard_modals.html`, `dashboard/components/dashboard_styles.html`, `dashboard/components/dashboard_scripts.html`; 0 form tags; 1 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/modulearn_analytics_dashboard.html](../../modulearn/dashboard/templates/dashboard/modulearn_analytics_dashboard.html) | 45 | Django template; extends/includes `base.html`, `includes/page_header.html`, `dashboard/components/modulearn_dashboard_header.html`, `dashboard/components/dashboard_kpi_cards.html`, `dashboard/components/dashboard_mastery_grid.html`, `dashboard/components/dashboard_modals.html`, `dashboard/components/dashboard_styles.html`, `dashboard/components/analytics_renderer.html`, `dashboard/components/modulearn_dashboard_fetcher.html`; 0 form tags; 1 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/student_dashboard.html](../../modulearn/dashboard/templates/dashboard/student_dashboard.html) | 278 | Django template; extends/includes `base.html`, `includes/page_header.html`, `includes/timeline_panel.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/dashboard/templates/dashboard/study_analytics_dashboard.html](../../modulearn/dashboard/templates/dashboard/study_analytics_dashboard.html) | 865 | Django template; extends/includes `base.html`, `includes/page_header.html`; 0 form tags; 1 inline script blocks. |
| [modulearn/dashboard/tests.py](../../modulearn/dashboard/tests.py) | 401 | 12 test methods. Symbols (snapshot line): `DashboardViewTests:34`. |
| [modulearn/dashboard/urls.py](../../modulearn/dashboard/urls.py) | 28 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/dashboard/views.py](../../modulearn/dashboard/views.py) | 1624 | Symbols (snapshot line): `_analytics_json_response:36`, `student_dashboard:64`, `instructor_dashboard:78`, `create_demo_course:93`, `modulearn_analytics_dashboard:114`, `study_analytics_dashboard:145`, `export_study_analytics_csv:162`, `fetch_modulearn_instance_analytics:214`, `_compact_module_event_payload:445`, `_serialize_module_progress_event:481`, `_can_view_course_instance_analytics:497`, `_serialize_full_progress_event:512`, `_serialize_access_log:531`, `_serialize_form_submission:544`, `_resolve_history_participant:575`, `fetch_module_capture_history:623`, `fetch_modulearn_student_engagement:754`, `generate_course_auth_url:907`, `proxy_course_authoring_x_login:1002`, `reset_course_authoring_password_view:1065`, `legacy_dashboard:1093`, `get_legacy_groups_api:1110`, `discover_course_ids:1144`, `get_course_resources_api:1178`, `fetch_class_list:1238`, `fetch_analytics_data:1281`, `fetch_all_students_analytics:1441`, `fetch_cell_activity_analytics:1524`. |

## data

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/data/slc_legacy_url_replacements.json](../../modulearn/data/slc_legacy_url_replacements.json) | 1 | Runtime legacy-to-current activity URL mapping; 140 URL replacements. |

## docs

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/docs/architecture.md](../../modulearn/docs/architecture.md) | 95 | Documentation: Architecture; Current shape; Django apps; `accounts`; `courses`; additional sections. |
| [modulearn/docs/compatibility-checklist.md](../../modulearn/docs/compatibility-checklist.md) | 37 | Documentation: Compatibility Checklist; Public routes; Role behavior; Invite and enrollment behavior; Analytics and legacy surfaces; additional sections. |
| [modulearn/docs/course-instance-session-module-analysis.md](../../modulearn/docs/course-instance-session-module-analysis.md) | 386 | Documentation: Course Sessions, Modules, and Access Control Analysis; 1. Scope and intent; 2. Terminology mapping in this codebase; 3. Primary source files; 4. Data model map (authoring, sessions, module delivery); additional sections. |
| [modulearn/docs/course-plugins.md](../../modulearn/docs/course-plugins.md) | 232 | Documentation: Course Plugin Contract; Current Storage; Registry; Reading Plugin Flags; Configuration UI; additional sections. |
| [modulearn/docs/deployment-adapt2.md](../../modulearn/docs/deployment-adapt2.md) | 49 | Documentation: Serving ModuLearn at adapt2.sis.pitt.edu/modulearn. |
| [modulearn/docs/extending-moduLearn.md](../../modulearn/docs/extending-moduLearn.md) | 31 | Documentation: Extending ModuLearn; Adding a page; Adding a workflow; Adding course plugin behavior; Adding a module/tool provider. |
| [modulearn/docs/inbound-lti.md](../../modulearn/docs/inbound-lti.md) | 62 | Documentation: Inbound LMS Launches Into ModuLearn; LTI 1.1 / Canvas Legacy; LTI 1.3 / Moodle And Canvas Advantage; Notes. |
| [modulearn/docs/integrations.md](../../modulearn/docs/integrations.md) | 89 | Documentation: Integrations; KnowledgeTree and MasteryGrids; Course Authoring; Inbound LTI provider; Outbound LTI tool consumer; additional sections. |
| [modulearn/docs/model-glossary.md](../../modulearn/docs/model-glossary.md) | 69 | Documentation: Model Glossary; Accounts; `accounts.User`; Courses domain; `courses.Course`; additional sections. |
| [modulearn/docs/page-inventory.md](../../modulearn/docs/page-inventory.md) | 76 | Documentation: Page Inventory; Marketing pages; Auth and account pages; Learning pages; Dashboard pages; additional sections. |
| [modulearn/docs/progress-timeline.md](../../modulearn/docs/progress-timeline.md) | 78 | Documentation: Progress And Timeline Model; Core progress models; `ModuleProgress`; `CourseProgress`; `ModuleProgressEvent`; additional sections. |
| [modulearn/docs/research-recruitment.md](../../modulearn/docs/research-recruitment.md) | 106 | Documentation: Research Recruitment Links; Study Setup; Prolific Entry Flow; Conditions; Completion; additional sections. |
| [modulearn/docs/testing.md](../../modulearn/docs/testing.md) | 55 | Documentation: Testing Strategy; Current focus; App-level coverage; `main/tests.py`; `accounts/tests.py`; additional sections. |
| [modulearn/docs/ui-localization.md](../../modulearn/docs/ui-localization.md) | 23 | Documentation: UI Localization; Current Languages; Where To Add Translations. |

## lti

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/lti/LTI_CONSUMER_DOCUMENTATION.md](../../modulearn/lti/LTI_CONSUMER_DOCUMENTATION.md) | 457 | Documentation: LTI Tool Consumer Documentation; Overview; Architecture; Data Flow; Launch Flow; additional sections. |
| [modulearn/lti/__init__.py](../../modulearn/lti/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/lti/admin.py](../../modulearn/lti/admin.py) | 133 | Symbols (snapshot line): `LTIPlatformRegistrationAdmin:10`, `LTIUserIdentityAdmin:42`, `LTILaunchCacheAdmin:59`, `LTIOutcomeLogAdmin:100`. |
| [modulearn/lti/apps.py](../../modulearn/lti/apps.py) | 6 | Symbols (snapshot line): `LtiConfig:4`. |
| [modulearn/lti/cache_data_storage.py](../../modulearn/lti/cache_data_storage.py) | 27 | Symbols (snapshot line): `CacheDataStorage:8`. |
| [modulearn/lti/config.py](../../modulearn/lti/config.py) | 310 | Symbols (snapshot line): `ctat_url_modifier:24`, `ctat_score_processor:29`, `opendsa_url_modifier:38`, `dbqa_url_modifier:43`, `dbqa_score_processor:48`, `dbqa_act_modifier:53`, `get_processor:69`, `get_tool_configs:78`, `get_tool_config:257`, `is_tool_configured:271`, `list_configured_tools:302`, `list_all_tools:307`. |
| [modulearn/lti/management/__init__.py](../../modulearn/lti/management/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/lti/management/commands/__init__.py](../../modulearn/lti/management/commands/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/lti/management/commands/cleanup_lti_cache.py](../../modulearn/lti/management/commands/cleanup_lti_cache.py) | 37 | Symbols (snapshot line): `Command:14`. |
| [modulearn/lti/middleware.py](../../modulearn/lti/middleware.py) | 47 | Symbols (snapshot line): `LTIAuthMiddleware:8`. |
| [modulearn/lti/migrations/0001_lti_launch_cache.py](../../modulearn/lti/migrations/0001_lti_launch_cache.py) | 57 | Migration: CreateModel (2). |
| [modulearn/lti/migrations/0002_add_module_tracking_fields.py](../../modulearn/lti/migrations/0002_add_module_tracking_fields.py) | 43 | Migration: AddField (3), AlterField (3). |
| [modulearn/lti/migrations/0003_lti13_platform_registration_and_identity.py](../../modulearn/lti/migrations/0003_lti13_platform_registration_and_identity.py) | 109 | Migration: swappable_dependency (1), CreateModel (2), AddIndex (4), AddConstraint (2). |
| [modulearn/lti/migrations/__init__.py](../../modulearn/lti/migrations/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/lti/models.py](../../modulearn/lti/models.py) | 313 | Symbols (snapshot line): `LTIPlatformRegistration:15`, `LTIUserIdentity:78`, `LTILaunchCache:119`, `LTIOutcomeLog:277`. |
| [modulearn/lti/platforms.py](../../modulearn/lti/platforms.py) | 139 | Symbols (snapshot line): `normalize_platform_issuer:16`, `_resolve_key_path:22`, `_read_key_file:29`, `_tool_key_paths:33`, `get_lti13_config_dict:45`, `build_lti13_tool_conf:67`, `build_absolute_url:89`, `lti_setup_payload:99`. |
| [modulearn/lti/services.py](../../modulearn/lti/services.py) | 610 | Symbols (snapshot line): `create_base_lti_body:26`, `create_lti_body:89`, `get_launch_url:167`, `sign_lti_request:205`, `build_paws_launch_params:243`, `build_signed_lti_params:309`, `build_um_url:389`, `parse_outcome_xml:468`, `create_outcome_response:513`, `validate_identifier:565`, `generate_source_id:594`. |
| [modulearn/lti/tests.py](../../modulearn/lti/tests.py) | 853 | 42 test methods. Symbols (snapshot line): `PublicLTIURLTests:40`, `LTIRoleTests:68`, `InboundLTI13Tests:171`, `LTIServicesTestCase:311`, `LTILaunchCacheTestCase:466`, `LTILaunchViewTestCase:588`, `LTIOutcomeViewTestCase:638`, `LTIOutcomeProgressIntegrationTestCase:750`, `LTIConfigTestCase:820`. |
| [modulearn/lti/tool_config.py](../../modulearn/lti/tool_config.py) | 24 | Symbols (snapshot line): `DjangoToolConf:3`. |
| [modulearn/lti/urls.py](../../modulearn/lti/urls.py) | 13 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/lti/views.py](../../modulearn/lti/views.py) | 652 | Symbols (snapshot line): `get_lti_role_flags:42`, `apply_lti_roles:58`, `lti13_jwks:81`, `lti13_login:87`, `handle_lti13_launch:124`, `handle_lti11_launch:150`, `_as_list:182`, `_first_audience:192`, `_claim_dict:198`, `_get_roles:203`, `_get_deployment_id:207`, `_get_client_id:211`, `_get_registration:220`, `_get_target_link_course_id:235`, `_get_course_instance_id:246`, `_get_lms_context_ids:259`, `_identity_issuer:278`, `_safe_launch_snapshot:283`, `_upsert_lti_identity:295`, `process_launch_data:313`, `lti_launch:498`, `lti_config:514`, `lti_setup_details:557`, `lti13_platform_registration:583`. |

## main

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/main/__init__.py](../../modulearn/main/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/main/admin.py](../../modulearn/main/admin.py) | 3 | Django admin registration/configuration. |
| [modulearn/main/apps.py](../../modulearn/main/apps.py) | 6 | Symbols (snapshot line): `MainConfig:4`. |
| [modulearn/main/models.py](../../modulearn/main/models.py) | 3 | Supporting source/configuration; see linked file. |
| [modulearn/main/templates/main/about.html](../../modulearn/main/templates/main/about.html) | 1 | Django template; extends/includes `main/info.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/main/templates/main/contact.html](../../modulearn/main/templates/main/contact.html) | 1 | Django template; extends/includes `main/info.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/main/templates/main/home.html](../../modulearn/main/templates/main/home.html) | 55 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/main/templates/main/info.html](../../modulearn/main/templates/main/info.html) | 80 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/main/templatetags/__init__.py](../../modulearn/main/templatetags/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/main/templatetags/tailwind_filters.py](../../modulearn/main/templatetags/tailwind_filters.py) | 38 | Symbols (snapshot line): `add_class:15`, `tw_input:25`. |
| [modulearn/main/tests.py](../../modulearn/main/tests.py) | 44 | 5 test methods. Symbols (snapshot line): `MainPageTests:5`. |
| [modulearn/main/urls.py](../../modulearn/main/urls.py) | 11 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/main/views.py](../../modulearn/main/views.py) | 22 | Symbols (snapshot line): `home:6`, `info:13`, `about:17`, `contact:21`. |

## Project package: settings, routing and integration controllers

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/modulearn/__init__.py](../../modulearn/modulearn/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/modulearn/asgi.py](../../modulearn/modulearn/asgi.py) | 16 | Django server application entry point. |
| [modulearn/modulearn/private.key](../../modulearn/modulearn/private.key) | — | Tracked private signing-key file; inspect exposure and coordinate rotation. |
| [modulearn/modulearn/public.key](../../modulearn/modulearn/public.key) | — | Public signing-key companion. |
| [modulearn/modulearn/settings.py](../../modulearn/modulearn/settings.py) | 416 | Symbols (snapshot line): `parse_boolish:30`, `get_primary_domain:334`, `LTI_URL_BUILDER:382`. |
| [modulearn/modulearn/urls.py](../../modulearn/modulearn/urls.py) | 103 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/modulearn/views_lti.py](../../modulearn/modulearn/views_lti.py) | 567 | Symbols (snapshot line): `_get_outcome_service_url:57`, `_update_module_progress:72`, `launch:175`, `outcome:354`, `health:529`. |
| [modulearn/modulearn/views_proxy.py](../../modulearn/modulearn/views_proxy.py) | 2119 | Symbols (snapshot line): `pcrs_feedback_asset:25`, `_proxy_source_from_path:36`, `_resolve_ipv4:57`, `_to_path_style:62`, `_is_login_page:84`, `_host_cookies:112`, `_host_cookie_header:124`, `_set_cookie_headers:131`, `_store_upstream_cookies:143`, `_proxied_referer_for_upstream:174`, `_rewrite_url:193`, `http_get_proxy:221`, `_handle_proxy_response:417`, `_is_paws_activity_page:674`, `_inject_activity_api_rewrite_script:694`, `_annotate_material_icon_fallbacks:980`, `_is_acos_pcex_javascript_response:1004`, `_rewrite_acos_pcex_javascript:1016`, `_first_query_value:1036`, `_referer_query_params:1043`, `_find_pcex_module:1050`, `_is_pcex_activity_data_response:1086`, `_pcex_context_key:1096`, `_session_pcex_state:1106`, `_cache_pcex_activity_metadata:1116`, `_pcex_worked_example_metadata:1163`, `_pcex_explanation_steps_for_goal:1190`, `_pcex_final_explanation_line:1205`, `_pcex_explanation_step_key:1223`, `_pcex_result_state:1235`, `_infer_pcex_goal_count_from_remote:1278`, `_infer_pcex_worked_examples_from_remote:1303`, `_pcex_local_progress_context:1329`, `_capture_pcex_activity_if_possible:1362`, `_pcex_worked_example_state:1402`, `_capture_pcex_explanation_if_possible:1474`, `_pcex_payload_is_correct:1538`, `_pcex_tracking_payload:1545`, `_request_form_payload:1551`, `_json_form_object:1578`, `_acos_pcex_params:1594`, `_acos_pcex_event_path:1615`, `_acos_pcex_score_snapshot:1619`, `_acos_pcex_attempt_count:1634`, `_acos_pcex_log_event_type:1651`, `_capture_acos_pcex_event_if_possible:1658`, `_capture_pcex_result_if_possible:1769`, `forward_to_adapt2:1872`, `forward_cbum:1937`, `forward_acos_pcex:1997`, `http_get_proxy_path:2032`. |
| [modulearn/modulearn/wsgi.py](../../modulearn/modulearn/wsgi.py) | 16 | Django server application entry point. |

## Project package: core

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/modulearn/core/__init__.py](../../modulearn/modulearn/core/__init__.py) | 1 | Python package initializer. |
| [modulearn/modulearn/core/context_processors.py](../../modulearn/modulearn/core/context_processors.py) | 17 | Symbols (snapshot line): `app_shell:8`. |
| [modulearn/modulearn/core/middleware.py](../../modulearn/modulearn/core/middleware.py) | 51 | Symbols (snapshot line): `QueryStringLanguageMiddleware:6`. |
| [modulearn/modulearn/core/navigation.py](../../modulearn/modulearn/core/navigation.py) | 62 | Symbols (snapshot line): `_nav_item:7`, `build_navigation:20`. |
| [modulearn/modulearn/core/roles.py](../../modulearn/modulearn/core/roles.py) | 142 | Symbols (snapshot line): `_looks_like_group_login:11`, `_build_legacy_group_fallback:18`, `get_legacy_course_groups:61`, `get_legacy_masterygrids_groups:80`, `get_user_role_snapshot:106`. |

## Project package: integrations

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/modulearn/integrations/__init__.py](../../modulearn/modulearn/integrations/__init__.py) | 1 | Python package initializer. |
| [modulearn/modulearn/integrations/config.py](../../modulearn/modulearn/integrations/config.py) | 35 | Symbols (snapshot line): `get_script_name:9`, `prefixed_path:14`, `get_course_authoring_base_url:22`, `build_course_authoring_url:29`, `get_knowledge_tree_base_url:34`. |
| [modulearn/modulearn/integrations/course_authoring.py](../../modulearn/modulearn/integrations/course_authoring.py) | 19 | Symbols (snapshot line): `build_course_export_url:6`, `build_x_login_token_url:10`, `build_x_login_url:14`, `build_course_authoring_app_url:18`. |

## Project package: learning

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/modulearn/learning/__init__.py](../../modulearn/modulearn/learning/__init__.py) | 1 | Python package initializer. |
| [modulearn/modulearn/learning/selectors/__init__.py](../../modulearn/modulearn/learning/selectors/__init__.py) | 1 | Python package initializer. |
| [modulearn/modulearn/learning/selectors/courses.py](../../modulearn/modulearn/learning/selectors/courses.py) | 262 | Symbols (snapshot line): `_module_provider_identity:12`, `_build_provider_grid:21`, `build_course_detail_context:113`. |
| [modulearn/modulearn/learning/selectors/dashboard.py](../../modulearn/modulearn/learning/selectors/dashboard.py) | 121 | Symbols (snapshot line): `build_student_dashboard_context:16`, `build_instructor_dashboard_context:39`. |
| [modulearn/modulearn/learning/selectors/timelines.py](../../modulearn/modulearn/learning/selectors/timelines.py) | 81 | Symbols (snapshot line): `_serialize_event:9`, `_base_queryset:43`, `_visible_timeline_events:54`, `get_student_timeline:60`, `get_course_timeline_for_student:68`, `get_course_instance_recent_activity:76`. |
| [modulearn/modulearn/learning/services/__init__.py](../../modulearn/modulearn/learning/services/__init__.py) | 1 | Python package initializer. |
| [modulearn/modulearn/learning/services/access_rules.py](../../modulearn/modulearn/learning/services/access_rules.py) | 349 | Symbols (snapshot line): `AccessState:10`, `empty_rule:20`, `build_unlock_rule:24`, `next_order_for_unit:37`, `next_order_for_module:44`, `sync_module_progress_for_course:51`, `log_module_access:80`, `evaluate_unit_access:94`, `evaluate_module_access:104`, `_has_active_branch_target:128`, `_rule_passes:139`, `_has_dynamic_module_unlock:154`, `_condition_passes:163`, `_participant_condition:189`, `_module_accessed:202`, `_module_completed:219`, `_unit_modules:227`, `_unit_accessed:233`, `_unit_completed:240`, `_previous_unit:247`, `_rule_reason:259`, `_module_title:298`, `_unit_title:309`, `_branch_reason:320`. |
| [modulearn/modulearn/learning/services/adaptive_branching.py](../../modulearn/modulearn/learning/services/adaptive_branching.py) | 117 | Symbols (snapshot line): `has_dynamic_module_unlock:11`, `handle_progress_event:27`, `_rule_matches:69`, `_threshold:91`, `_participant_condition:95`, `_unlock_reason:114`. |
| [modulearn/modulearn/learning/services/course_plugins.py](../../modulearn/modulearn/learning/services/course_plugins.py) | 56 | Symbols (snapshot line): `available_course_plugins:28`, `normalize_course_plugin_config:32`, `is_course_plugin_enabled:46`, `enabled_course_plugins:51`. |
| [modulearn/modulearn/learning/services/limits.py](../../modulearn/modulearn/learning/services/limits.py) | 94 | Symbols (snapshot line): `CapacityLimitError:9`, `max_students_per_session:13`, `max_sessions_per_course:17`, `max_active_sessions_per_instructor:21`, `active_session_enrollment_count:31`, `remaining_session_student_slots:35`, `ensure_session_student_capacity:39`, `active_course_session_count:50`, `remaining_course_session_slots:56`, `ensure_course_session_capacity:60`, `active_instructor_session_count:73`, `remaining_instructor_session_slots:82`, `ensure_instructor_session_capacity:86`. |
| [modulearn/modulearn/learning/services/pcrs_tracking.py](../../modulearn/modulearn/learning/services/pcrs_tracking.py) | 235 | Symbols (snapshot line): `is_pcrs_url:14`, `is_pcrs_run_path:24`, `capture_pcrs_result_if_possible:29`, `_first_query_value:138`, `_query_values:145`, `_query_dict_payload:153`, `_raw_body_text:169`, `_submission_snapshot:182`, `_referer_query_params:202`, `_find_pcrs_module:209`. |
| [modulearn/modulearn/learning/services/progress.py](../../modulearn/modulearn/learning/services/progress.py) | 229 | Symbols (snapshot line): `clamp:14`, `_coerce_score:20`, `_coerce_progress:26`, `log_module_progress_event:32`, `module_accepts_scored_attempt:65`, `recompute_course_progress:78`, `apply_progress_snapshot:131`, `record_module_launch:210`, `record_module_session_event:214`. |
| [modulearn/modulearn/learning/services/slc_replacements.py](../../modulearn/modulearn/learning/services/slc_replacements.py) | 163 | Symbols (snapshot line): `SLCReplacement:15`, `apply_slc_legacy_replacement:24`, `apply_replacement_metadata:73`, `_find_mapping:81`, `_best_replacement_url:90`, `_supported_protocols:103`, `_lookup_candidates:114`, `_canonical_url:133`, `_load_url_mappings:149`. |

## recruitment

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/recruitment/__init__.py](../../modulearn/recruitment/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/recruitment/admin.py](../../modulearn/recruitment/admin.py) | 56 | Symbols (snapshot line): `StudyConditionInline:13`, `StudyAdmin:19`, `RecruitmentSourceAdmin:29`, `ParticipantSessionAdmin:37`, `RecruitmentAssignmentSlotAdmin:45`, `RecruitmentEntryLogAdmin:52`. |
| [modulearn/recruitment/apps.py](../../modulearn/recruitment/apps.py) | 6 | Symbols (snapshot line): `RecruitmentConfig:4`. |
| [modulearn/recruitment/fields.py](../../modulearn/recruitment/fields.py) | 56 | Symbols (snapshot line): `_fernet:16`, `EncryptedCharField:24`. |
| [modulearn/recruitment/migrations/0001_initial.py](../../modulearn/recruitment/migrations/0001_initial.py) | 128 | Migration: swappable_dependency (1), CreateModel (4), AddConstraint (3), AddIndex (2). |
| [modulearn/recruitment/migrations/0002_rename_recruitment_status_entered_idx_recruitment_status_887633_idx_and_more.py](../../modulearn/recruitment/migrations/0002_rename_recruitment_status_entered_idx_recruitment_status_887633_idx_and_more.py) | 23 | Migration: RenameIndex (2). |
| [modulearn/recruitment/migrations/0003_participant_session_external_session_unique.py](../../modulearn/recruitment/migrations/0003_participant_session_external_session_unique.py) | 29 | Migration: RemoveConstraint (1), AddIndex (1), AddConstraint (1). |
| [modulearn/recruitment/migrations/0004_alter_recruitmentsource_condition_labels.py](../../modulearn/recruitment/migrations/0004_alter_recruitmentsource_condition_labels.py) | 20 | Migration: AlterField (1). |
| [modulearn/recruitment/migrations/0005_study_studycondition_alter_recruitmentsource_options_and_more.py](../../modulearn/recruitment/migrations/0005_study_studycondition_alter_recruitmentsource_options_and_more.py) | 155 | Migration: swappable_dependency (1), CreateModel (2), AlterModelOptions (1), RemoveConstraint (1), AlterField (1), AddField (4), AddConstraint (3), RunPython (1), AddIndex (1). |
| [modulearn/recruitment/migrations/0006_backfill_study_prolific_sources.py](../../modulearn/recruitment/migrations/0006_backfill_study_prolific_sources.py) | 33 | Migration: RunPython (1). |
| [modulearn/recruitment/migrations/__init__.py](../../modulearn/recruitment/migrations/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/recruitment/models.py](../../modulearn/recruitment/models.py) | 356 | Symbols (snapshot line): `Study:15`, `StudyCondition:73`, `RecruitmentSource:91`, `RecruitmentAssignmentSlot:205`, `ParticipantSession:232`, `RecruitmentEntryLog:326`. |
| [modulearn/recruitment/services/__init__.py](../../modulearn/recruitment/services/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/recruitment/services/conditions.py](../../modulearn/recruitment/services/conditions.py) | 60 | Symbols (snapshot line): `assign_condition:12`, `_assign_hash:28`, `_assign_balanced:34`, `_assign_from_schedule:46`. |
| [modulearn/recruitment/services/participants.py](../../modulearn/recruitment/services/participants.py) | 156 | Symbols (snapshot line): `get_current_participant_session:8`, `get_participant_sessions:33`, `participant_course_redirect:58`, `user_can_access_participant_course:67`, `get_participant_resume_module:79`. |
| [modulearn/recruitment/services/prolific.py](../../modulearn/recruitment/services/prolific.py) | 128 | Symbols (snapshot line): `ProlificVerificationError:14`, `ProlificIds:19`, `completion_url:30`, `validate_prolific_ids:34`, `valid_prolific_pid:56`, `is_synthetic_prolific_pid:63`, `verify_secured_url:67`, `verify_submission_api:98`, `_assert_claim_match:125`. |
| [modulearn/recruitment/services/sona.py](../../modulearn/recruitment/services/sona.py) | 54 | Symbols (snapshot line): `SonaCreditError:9`, `client_credit_url:13`, `grant_credit_server_side:23`. |
| [modulearn/recruitment/services/studies.py](../../modulearn/recruitment/services/studies.py) | 471 | Symbols (snapshot line): `parse_condition_labels:154`, `_template_study_payload:163`, `_template_condition_labels:169`, `_create_default_study_modules:178`, `_source_payload:229`, `_create_recruitment_sources_from_template:248`, `create_study_for_instructor:284`, `export_study_to_json:359`, `clear_study_participation:398`, `delete_study_completely:464`. |
| [modulearn/recruitment/services/study_analytics.py](../../modulearn/recruitment/services/study_analytics.py) | 249 | Symbols (snapshot line): `build_study_analytics_context:14`, `study_analytics_csv_rows:146`, `_empty_condition_summary:185`, `_progress_event_summary:198`, `_event_count:235`, `_iso_event_summary_value:239`, `_participant_label:244`. |
| [modulearn/recruitment/templates/recruitment/already_completed.html](../../modulearn/recruitment/templates/recruitment/already_completed.html) | 15 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/recruitment/templates/recruitment/consent.html](../../modulearn/recruitment/templates/recruitment/consent.html) | 29 | Django template; extends/includes `base.html`; 1 form tags; 0 inline script blocks. |
| [modulearn/recruitment/templates/recruitment/ineligible.html](../../modulearn/recruitment/templates/recruitment/ineligible.html) | 15 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/recruitment/templates/recruitment/sessions.html](../../modulearn/recruitment/templates/recruitment/sessions.html) | 69 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/recruitment/templates/recruitment/thank_you.html](../../modulearn/recruitment/templates/recruitment/thank_you.html) | 18 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/recruitment/tests/__init__.py](../../modulearn/recruitment/tests/__init__.py) | 0 | Python package initializer (empty). |
| [modulearn/recruitment/tests/test_recruitment_flow.py](../../modulearn/recruitment/tests/test_recruitment_flow.py) | 1046 | 35 test methods. Symbols (snapshot line): `RecruitmentEntryFlowTests:33`. |
| [modulearn/recruitment/urls.py](../../modulearn/recruitment/urls.py) | 26 | Django URL declarations and namespaced endpoint wiring. |
| [modulearn/recruitment/views.py](../../modulearn/recruitment/views.py) | 824 | Symbols (snapshot line): `_client_ip:46`, `_entry_log_kwargs:53`, `_rate_limit_entry:65`, `_detect_platform:74`, `_participant_username:84`, `_provision_participant_user:89`, `_verify_entry:120`, `enter:142`, `study_launch:157`, `_enter_source:183`, `sessions:332`, `resume_session:359`, `consent:402`, `already_completed:418`, `thank_you:432`, `complete_current:438`, `complete_current_study:460`, `complete:474`, `_determine_outcome:528`, `_prolific_code_for_outcome:542`, `_redirect_after_source_save:550`, `_user_can_manage_study:565`, `_sync_study_conditions:569`, `_uploaded_study_template:599`, `create_study:614`, `export_study:636`, `create_study_source:655`, `reset_study_participation:706`, `delete_study:730`, `create_source:753`, `_optional_int:758`, `_single_condition_label:767`, `export_sessions:773`. |

## static

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/static/css/design-system.css](../../modulearn/static/css/design-system.css) | 722 | Shared visual tokens, components, layouts and interaction styles. |
| [modulearn/static/css/styles.css](../../modulearn/static/css/styles.css) | 1497 | Stylesheet. |
| [modulearn/static/css/tailwind.generated.css](../../modulearn/static/css/tailwind.generated.css) | 1 | Generated Tailwind stylesheet, tracked as a deployable asset. |
| [modulearn/static/img/logo_128.png](../../modulearn/static/img/logo_128.png) | — | PNG image asset. |
| [modulearn/static/img/logo_32.png](../../modulearn/static/img/logo_32.png) | — | PNG image asset. |
| [modulearn/static/img/logo_64.png](../../modulearn/static/img/logo_64.png) | — | PNG image asset. |
| [modulearn/static/img/pcrs/red-sad-face.png](../../modulearn/static/img/pcrs/red-sad-face.png) | — | PNG image asset. |
| [modulearn/static/img/pcrs/yellow-happy-face.png](../../modulearn/static/img/pcrs/yellow-happy-face.png) | — | PNG image asset. |
| [modulearn/static/js/accounts/profile.js](../../modulearn/static/js/accounts/profile.js) | 54 | JavaScript functions: `filterGroups`. |
| [modulearn/static/js/accounts/signup.js](../../modulearn/static/js/accounts/signup.js) | 80 | JavaScript functions: `normalize`, `profileTokens`, `setRule`, `setFieldState`, `updatePasswordChecks`. |
| [modulearn/static/js/app-shell.js](../../modulearn/static/js/app-shell.js) | 138 | JavaScript functions: `t`, `getStoredTheme`, `applyTheme`, `toggleTheme`, `toggleMobileNav`, `handleHeaderScroll`, `syncShellOffsets`, `dismissFlashMessage`, `initializeFlashMessages`. |
| [modulearn/static/js/bootstrap-compat.js](../../modulearn/static/js/bootstrap-compat.js) | 220 | JavaScript functions: `syncBodyModalState`. |
| [modulearn/static/js/courses/create-semester-course.js](../../modulearn/static/js/courses/create-semester-course.js) | 185 | JavaScript functions: `t`, `isUsableCsrfToken`, `getCookieCsrfToken`, `getFormCsrfToken`, `getCsrfToken`, `showError`, `hideManualError`, `showManualError`, `createCourseFromExport`, `createRawSession`. |
| [modulearn/static/js/courses/module-frame.js](../../modulearn/static/js/courses/module-frame.js) | 255 | JavaScript functions: `uuid`, `showBlockedNotice`, `getStateData`, `iframeUrlSummary`, `sessionPayload`, `recordSessionEvent`, `notifyProgressMaybeUpdated`, `setAttentionState`, `probeSplice`. |
| [modulearn/static/js/courses/next-module-button.js](../../modulearn/static/js/courses/next-module-button.js) | 166 | JavaScript functions: `t`, `setButtonState`, `resolveNext`, `scheduleRefresh`, `refreshAll`, `warm`. |
| [modulearn/static/js/dashboard/instructor-dashboard.js](../../modulearn/static/js/dashboard/instructor-dashboard.js) | 1603 | JavaScript functions: `t`, `debounce`, `debounced`, `replacePattern`, `replaceNumericPathSegment`, `parseJsonResponse`, `escapeHtml`, `activityEventLabel`, `activityEventClass`, `formatActivityDate`, `activitySuccessLabel`, `activitySortValue`, `compareActivityValues`, `renderSessionActivityTable`, `populateSessionActivityTypeFilter`, `openSessionActivity`, `csvEscape`, `downloadSessionActivityCsv`, `initializeSessionActionRows`, `handleDashboardCopy`, `csrfHeaders`, `buildLegacyDashboardUrl`, `createNewSession`, `setInputValue`, `setLtiValue`, `setText`, `copyInputValue`, `normalizeIssuerBase`, `fillLtiEndpointDefaults`, `fillMoodleEndpointDefaults`, `syncLtiPlatformHelp`, `resetLtiEndpointAutofillState`, `openLtiSetup`, `saveLtiPlatformRegistration`, `showDeleteCourseConfirmation`, `deleteCourse`, `showDeleteSessionConfirmation`, `deleteCourseSession`, `updateAnonymousCapacityHint`, `loadEnrollments`, `attachRemoveListeners`, `formatGeneratedRoster`, `filterLegacyGroups`, `renderLegacyGroups`, `loadLegacyGroups`, `resetImportJsonState`, `isSupportedCourseImportPayload`. |
| [modulearn/static/js/i18n.js](../../modulearn/static/js/i18n.js) | 1546 | JavaScript functions: `trimParts`, `translateCore`, `translateString`, `translateTextNode`, `translateAttributes`, `translateTree`. |
| [modulearn/static/js/shared/course-resources-modal.js](../../modulearn/static/js/shared/course-resources-modal.js) | 171 | JavaScript functions: `escapeHtml`, `createClient`, `patternUrl`, `showLoading`, `showError`, `openResource`, `renderResources`, `loadResources`, `openCourseResourcesModal`, `bindTriggers`. |

## static_src

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/static_src/tailwind.css](../../modulearn/static_src/tailwind.css) | 3 | Tailwind input directives and source styles. |

## templates

| File | Lines | Contents / role |
|---|---:|---|
| [modulearn/templates/404.html](../../modulearn/templates/404.html) | 17 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/templates/500.html](../../modulearn/templates/500.html) | 17 | Django template; extends/includes `base.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/templates/base.html](../../modulearn/templates/base.html) | 69 | Django template; extends/includes `includes/app_nav.html`, `includes/app_footer.html`; 0 form tags; 2 inline script blocks. |
| [modulearn/templates/content_base.html](../../modulearn/templates/content_base.html) | 43 | Django template; extends/includes `includes/app_footer.html`; 0 form tags; 2 inline script blocks. |
| [modulearn/templates/includes/app_footer.html](../../modulearn/templates/includes/app_footer.html) | 5 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/templates/includes/app_nav.html](../../modulearn/templates/includes/app_nav.html) | 134 | Django template; 6 form tags; 0 inline script blocks. |
| [modulearn/templates/includes/page_header.html](../../modulearn/templates/includes/page_header.html) | 18 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/templates/includes/tailwind_form.html](../../modulearn/templates/includes/tailwind_form.html) | 36 | Django template; extends/includes `includes/tailwind_form.html`; 0 form tags; 0 inline script blocks. |
| [modulearn/templates/includes/timeline_panel.html](../../modulearn/templates/includes/timeline_panel.html) | 43 | Django template; 0 form tags; 0 inline script blocks. |
| [modulearn/templates/lti/auto_submit.html](../../modulearn/templates/lti/auto_submit.html) | 110 | Django template; extends/includes `content_base.html`; 1 form tags; 1 inline script blocks. |

## Keeping the map useful

Update this index when adding, moving or retiring an application subsystem. Prefer the focused architecture or feature document for detailed behavior; use the companion review for cross-cutting invariants and outstanding findings. Dependency caches, generated static assets, credentials, and database contents should not be copied into the map.
