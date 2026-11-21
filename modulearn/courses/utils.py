import base64
import mimetypes
import requests
import logging
from copy import deepcopy
from .models import Course, Unit, Module, ModuleBranchRule, ModuleForm, ModuleFormQuestion
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
import json
import traceback
import uuid
from oauthlib.oauth1 import Client
from oauthlib.oauth1.rfc5849 import signature
from modulearn.integrations.course_authoring import (
    build_course_export_url,
    build_x_login_token_url,
)
from modulearn.learning.services.slc_replacements import (
    apply_replacement_metadata,
    apply_slc_legacy_replacement,
)
from modulearn.learning.services.course_plugins import normalize_course_plugin_config
from accounts.email_utils import find_user_by_email, normalize_email_address, unique_username_for_email

# Configure logging
logger = logging.getLogger(__name__)

User = get_user_model()
COURSE_AUTHORING_TOKEN_URL = build_x_login_token_url()
MODULEARN_COURSE_EXPORT_SCHEMA = "modulearn-course-export-v2"
MODULEARN_STUDY_EXPORT_PREFIX = "modulearn-study-export"
LEGACY_STUDY_MODULE_TYPE_TO_STEP = {
    Module.MODULE_TYPE_STUDY_CONSENT: "consent",
    Module.MODULE_TYPE_STUDY_INSTRUCTIONS: "instructions",
    Module.MODULE_TYPE_STUDY_PRETEST: "pretest",
    Module.MODULE_TYPE_STUDY_POSTTEST: "posttest",
    Module.MODULE_TYPE_STUDY_DEBRIEF: "debrief",
}
STUDY_STEP_ALIASES = {
    **LEGACY_STUDY_MODULE_TYPE_TO_STEP,
    "study_consent": "consent",
    "study_instructions": "instructions",
    "study_pretest": "pretest",
    "study_posttest": "posttest",
    "study_debrief": "debrief",
    "consent": "consent",
    "instructions": "instructions",
    "pretest": "pretest",
    "posttest": "posttest",
    "debrief": "debrief",
}


def normalize_module_type(module_type):
    """Coerce retired module type aliases into the current schema."""
    module_type = module_type or Module.MODULE_TYPE_IMPORTED
    return Module.MODULE_TYPE_FORM if module_type in Module.LEGACY_STUDY_FORM_TYPES else module_type


def _normalize_study_step(value):
    return STUDY_STEP_ALIASES.get(str(value or "").strip().lower(), "")


def _study_step_from_content_data(content_data, *, fallback=""):
    step = ""
    if isinstance(content_data, dict):
        step = _normalize_study_step(content_data.get("study_step"))
    return step or _normalize_study_step(fallback)


def _default_form_payload(title, *, content_data=None, description="", allow_resubmission=False):
    study_step = _study_step_from_content_data(content_data)
    defaults = {
        "consent": {
            "instructions": "Review the study information carefully. Submit this form only if you agree to participate.",
            "submit_button_label": "I Consent",
            "questions": [
                {
                    "prompt": "I have read the study information and agree to participate.",
                    "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                    "options": ["I agree"],
                    "required": True,
                }
            ],
        },
        "instructions": {
            "instructions": "Read the instructions for this study. Submit when you are ready to continue.",
            "submit_button_label": "Continue",
            "questions": [
                {
                    "prompt": "I understand the instructions and am ready to begin.",
                    "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                    "options": ["Ready"],
                    "required": True,
                }
            ],
        },
        "pretest": {
            "instructions": "Complete the pretest items before beginning the main study tasks.",
            "submit_button_label": "Submit Pretest",
            "questions": [
                {
                    "prompt": "Pretest placeholder response",
                    "question_type": ModuleFormQuestion.TYPE_SHORT_ANSWER,
                    "required": True,
                }
            ],
        },
        "posttest": {
            "instructions": "Complete the posttest before receiving study completion credit.",
            "submit_button_label": "Submit Posttest",
            "questions": [
                {
                    "prompt": "Posttest placeholder response",
                    "question_type": ModuleFormQuestion.TYPE_SHORT_ANSWER,
                    "required": True,
                }
            ],
        },
        "debrief": {
            "instructions": "Read the debrief. The final study link can return you to Prolific for credit.",
            "submit_button_label": "Finish Debrief",
            "questions": [
                {
                    "prompt": "I have read the debrief.",
                    "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                    "options": ["Complete"],
                    "required": True,
                }
            ],
        },
    }
    payload = deepcopy(defaults.get(study_step) or {
        "instructions": description or f"Complete {title or 'this form'} to continue.",
        "submit_button_label": "Submit",
        "questions": [
            {
                "prompt": "Confirm completion.",
                "question_type": ModuleFormQuestion.TYPE_SINGLE_CHOICE,
                "options": ["Complete"],
                "required": True,
            }
        ],
    })
    payload["allow_resubmission"] = bool(allow_resubmission)
    return payload


def _resource_metadata_by_id(resources):
    """Map course-authoring resource IDs to human-facing resource metadata."""
    metadata = {}
    for resource in resources or []:
        resource_id = resource.get('id')
        if resource_id is None:
            continue
        metadata[str(resource_id)] = {
            'name': resource.get('name') or '',
            'providers': resource.get('providers') or [],
        }
    return metadata


def _activity_platform_name(activity, resource_id, resource_metadata):
    """Return the best display label for an imported activity's resource type."""
    explicit_label = activity.get('platform_name') or activity.get('resource_name')
    if explicit_label:
        return explicit_label

    metadata = resource_metadata.get(str(resource_id), {})
    resource_name = metadata.get('name')
    if resource_name:
        return resource_name

    provider_id = activity.get('provider_id')
    for provider in metadata.get('providers') or []:
        if not provider_id or provider.get('id') == provider_id:
            if provider.get('name'):
                return provider['name']

    return activity.get('resource_id') or ''


def unwrap_course_export_payload(payload):
    """Return the course-shaped payload from CAT, ModuLearn course, or ModuLearn study JSON."""
    if not isinstance(payload, dict):
        raise ValueError("Course import data must be a JSON object.")
    schema = (payload.get("schema") or "").strip()
    if schema.startswith(MODULEARN_STUDY_EXPORT_PREFIX):
        course_payload = payload.get("course")
        if not isinstance(course_payload, dict):
            raise ValueError("Study export is missing its course structure.")
        return course_payload
    if isinstance(payload.get("course"), dict) and "units" not in payload:
        return payload["course"]
    return payload


def should_clone_import_payload(payload):
    """ModuLearn exports are treated as templates; CAT JSON keeps its external course id."""
    if not isinstance(payload, dict):
        return False
    schema = (payload.get("schema") or "").strip()
    return schema.startswith("modulearn-course-export") or schema.startswith(MODULEARN_STUDY_EXPORT_PREFIX) or (
        isinstance(payload.get("course"), dict) and "units" not in payload
    )


def _safe_identifier_fragment(value, *, fallback="course", max_length=120):
    fragment = "".join(
        character.lower() if character.isalnum() else "-"
        for character in str(value or fallback)
    ).strip("-")
    while "--" in fragment:
        fragment = fragment.replace("--", "-")
    return (fragment or fallback)[:max_length].strip("-") or fallback


def _generated_course_id(course_data):
    seed = course_data.get("id") or course_data.get("name") or course_data.get("title") or "course"
    return f"{_safe_identifier_fragment(seed)}-copy-{uuid.uuid4().hex[:10]}"


def _unit_title(unit_data):
    return unit_data.get("name") or unit_data.get("title") or "Untitled Unit"


def _module_entries_for_unit(unit_data):
    """Support both CAT activities-by-resource and ModuLearn's flat module export."""
    if isinstance(unit_data.get("modules"), list):
        entries = []
        for activity in unit_data.get("modules") or []:
            resource_id = (
                activity.get("resource_id")
                or activity.get("platform_name")
                or activity.get("provider_id")
                or activity.get("module_type")
                or "Activities"
            )
            entries.append((resource_id, activity))
        return entries

    entries = []
    for resource_id, activities in (unit_data.get("activities") or {}).items():
        for activity in activities or []:
            if isinstance(activity, dict):
                activity = {**activity}
                activity.setdefault("resource_id", resource_id)
                entries.append((resource_id, activity))
    return entries


def _form_payload_from_activity(activity):
    form_data = activity.get("form")
    if isinstance(form_data, dict):
        return form_data
    if any(key in activity for key in ("instructions", "submit_button_label", "questions")):
        return {
            "instructions": activity.get("instructions", ""),
            "submit_button_label": activity.get("submit_button_label", "Submit"),
            "allow_resubmission": activity.get("form_allow_resubmission", activity.get("allow_resubmission", False)),
            "questions": activity.get("questions") or [],
        }
    return None


def _sync_module_form(module, form_data):
    if not isinstance(form_data, dict):
        return

    module_form, _created = ModuleForm.objects.update_or_create(
        module=module,
        defaults={
            "instructions": form_data.get("instructions", ""),
            "submit_button_label": form_data.get("submit_button_label") or "Submit",
            "allow_resubmission": bool(form_data.get("allow_resubmission", False)),
        },
    )
    module_form.questions.all().delete()
    valid_question_types = {choice[0] for choice in ModuleFormQuestion.TYPE_CHOICES}
    for index, question_data in enumerate(form_data.get("questions") or [], start=1):
        if not isinstance(question_data, dict):
            continue
        question_type = question_data.get("question_type") or ModuleFormQuestion.TYPE_SHORT_ANSWER
        if question_type not in valid_question_types:
            question_type = ModuleFormQuestion.TYPE_SHORT_ANSWER
        ModuleFormQuestion.objects.create(
            form=module_form,
            prompt=question_data.get("prompt") or "",
            help_text=question_data.get("help_text") or "",
            question_type=question_type,
            required=bool(question_data.get("required", True)),
            order=question_data.get("order") or index * 10,
            options=question_data.get("options") or [],
            likert_min_label=question_data.get("likert_min_label") or "Strongly disagree",
            likert_max_label=question_data.get("likert_max_label") or "Strongly agree",
        )


def ensure_module_form(module, form_data=None):
    """Return a ModuleForm for a form module, creating a default if needed."""
    if module.module_type != Module.MODULE_TYPE_FORM:
        return None

    if isinstance(form_data, dict):
        _sync_module_form(module, form_data)
        return ModuleForm.objects.get(module=module)

    module_form = ModuleForm.objects.filter(module=module).first()
    if module_form:
        return module_form

    _sync_module_form(
        module,
        _default_form_payload(
            module.title,
            content_data=module.content_data,
            description=module.description,
            allow_resubmission=module.allow_resubmission,
        ),
    )
    return ModuleForm.objects.get(module=module)


def _content_file_export_payload(module, *, include_file_data=True):
    if not module.content_file:
        return None

    payload = {
        "name": module.content_file.name,
        "filename": module.content_file.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1],
        "content_type": mimetypes.guess_type(module.content_file.name)[0] or "",
    }
    try:
        payload["url"] = module.content_file.url
    except Exception:
        payload["url"] = ""
    try:
        payload["size"] = module.content_file.size
    except Exception:
        payload["size"] = None

    if include_file_data:
        try:
            with module.content_file.open("rb") as file_handle:
                payload["encoding"] = "base64"
                payload["data_base64"] = base64.b64encode(file_handle.read()).decode("ascii")
        except Exception as exc:
            logger.warning("Could not embed uploaded file for activity %s: %s", module.id, exc)
            payload["export_warning"] = "file data could not be read"
    return payload


def _restore_content_file(module, activity):
    file_payload = activity.get("content_file")
    if not isinstance(file_payload, dict) or not file_payload.get("data_base64"):
        return False
    filename = (
        file_payload.get("filename")
        or file_payload.get("name")
        or f"module-{module.id}-file"
    ).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    try:
        file_bytes = base64.b64decode(file_payload["data_base64"])
    except Exception as exc:
        logger.warning("Could not decode uploaded file for activity %s: %s", module.id, exc)
        return False
    module.content_file.save(filename, ContentFile(file_bytes), save=False)
    return True


def _portable_unlock_rule(rule, modules_by_id, units_by_id=None):
    rule = deepcopy(rule or {})
    if not rule:
        return {}
    conditions = []
    for condition in rule.get("conditions") or []:
        condition = deepcopy(condition)
        if condition.get("type") in {"module_accessed", "module_completed"}:
            target = modules_by_id.get(str(condition.get("target_id")))
            if target:
                condition["target_unit"] = target.unit.title
                condition["target_module"] = target.title
                condition["target_db_id"] = condition.pop("target_id", "")
        elif condition.get('type') in {'unit_accessed', 'unit_completed'}:
            target = (units_by_id or {}).get(str(condition.get('target_id')))
            if target:
                condition['target_unit'] = target.title
            condition['target_db_id'] = condition.pop('target_id', '')
        conditions.append(condition)
    rule["conditions"] = conditions
    return rule


def _resolve_unlock_rule(portable_rule, raw_rule, module_lookup, unit_lookup=None):
    rule = deepcopy(portable_rule or raw_rule or {})
    if not rule:
        return {}
    used_portable = bool(portable_rule)
    resolved_conditions = []
    for condition in rule.get("conditions") or []:
        condition = deepcopy(condition)
        condition_type = condition.get("type")
        if condition_type in {"module_accessed", "module_completed"}:
            target = None
            target_unit = condition.pop("target_unit", None)
            target_module = condition.pop("target_module", None)
            condition.pop("target_db_id", None)
            if target_unit and target_module:
                target = module_lookup.get((target_unit, target_module))
            if target:
                condition["target_id"] = target.id
            elif used_portable:
                continue
        elif condition_type in {'unit_accessed', 'unit_completed'}:
            lookup = unit_lookup or {}
            old_id = condition.pop('target_db_id', condition.pop('target_id', ''))
            title = condition.pop('target_unit', None)
            target = lookup.get(('id', str(old_id))) or lookup.get(('title', title))
            if target:
                condition['target_id'] = target.id
            else:
                condition = {'type': 'unresolved_import'}
        resolved_conditions.append(condition)
    if not resolved_conditions:
        return {}
    return {
        "mode": rule.get("mode") or rule.get("operator") or "all",
        "conditions": resolved_conditions,
    }


def _serialize_module_form(module):
    try:
        module_form = module.form
    except ModuleForm.DoesNotExist:
        return None
    return {
        "instructions": module_form.instructions,
        "allow_resubmission": module_form.allow_resubmission,
        "submit_button_label": module_form.submit_button_label,
        "questions": [
            {
                "prompt": question.prompt,
                "help_text": question.help_text,
                "question_type": question.question_type,
                "question_type_label": question.get_question_type_display(),
                "required": question.required,
                "order": question.order,
                "options": question.options or [],
                "likert_min_label": question.likert_min_label,
                "likert_max_label": question.likert_max_label,
            }
            for question in module_form.questions.all()
        ],
    }

def fetch_course_details(course_id, user):
    logger.info(f"Starting fetch_course_details for course_id: {course_id}")
    
    # Get the authentication token
    token = get_course_auth_token(user)
    
    url = build_course_export_url(course_id)
    logger.info(f"Fetching course data from URL: {url}")
    
    headers = {
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.get(url, headers=headers)
        logger.info(f"Received response with status code: {response.status_code}")
        logger.debug(f"Response content: {response.text[:500]}...")  # Log first 500 chars
        
        if response.status_code != 200:
            error_message = f"Failed to fetch course details: Status {response.status_code}, Response: {response.text}"
            logger.error(error_message)
            raise Exception(error_message)
        
        course_data = response.json()
        if not course_data:
            logger.error("Empty response from API")
            raise Exception("Empty response from API")
            
        logger.info("Successfully fetched course data")
        logger.debug(f"Course data structure: {list(course_data.keys())}")
        return course_data
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        raise Exception(f"Failed to connect to course API: {str(e)}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        logger.error(f"Raw response: {response.text[:500]}...")
        raise Exception(f"Invalid JSON response from API: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in fetch_course_details: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def create_course_from_json(
    course_data,
    current_user,
    *,
    clone=False,
    title_override=None,
    description_override=None,
    course_id_override=None,
    lock_for_research=None,
):
    logger.debug("Creating course from JSON data")
    course_data = unwrap_course_export_payload(course_data)

    source_course_id = course_data.get("id") or course_data.get("course_id") or ""
    course_id = course_id_override or (_generated_course_id(course_data) if clone or not source_course_id else str(source_course_id))
    course_title = (title_override or course_data.get("name") or course_data.get("title") or "Untitled Course").strip()
    course_description = description_override if description_override is not None else course_data.get("description", "")
    plugin_config = normalize_course_plugin_config(course_data.get("plugin_config") or course_data.get("plugins") or {})
    is_locked_for_research = (
        bool(lock_for_research)
        if lock_for_research is not None
        else bool(course_data.get("is_locked_for_research", False))
    )

    schedule_timezone = course_data.get('schedule_timezone') or ''
    if schedule_timezone:
        from zoneinfo import ZoneInfo
        ZoneInfo(schedule_timezone)
    course, created = Course.objects.get_or_create(
        id=course_id,
        defaults={
            "title": course_title,
            "description": course_description or "",
            "plugin_config": plugin_config,
            "schedule_timezone": schedule_timezone,
            "is_locked_for_research": is_locked_for_research,
        },
    )
    logger.debug("Course %s: %s", "created" if created else "retrieved", course)

    if not created:
        updated = False
        for field_name, value in (
            ("title", course_title),
            ("description", course_description or ""),
            ("plugin_config", plugin_config),
            ("is_locked_for_research", is_locked_for_research),
        ):
            if getattr(course, field_name) != value:
                setattr(course, field_name, value)
                updated = True
        if updated:
            course.save()

    if getattr(current_user, "is_instructor", False):
        course.instructors.add(current_user)

    instructor_data = course_data.get("instructor", {})
    if instructor_data:
        instructor_email = normalize_email_address(instructor_data.get("email"))
        if instructor_email:
            instructor_user = find_user_by_email(instructor_email)
            if instructor_user is None:
                instructor_user = User.objects.create_user(
                    username=unique_username_for_email(instructor_email, local_part_only=True),
                    email=instructor_email,
                    is_instructor=True,
                    is_student=False,
                )
            course.instructors.add(instructor_user)

    resource_metadata = _resource_metadata_by_id(course_data.get("resources"))
    provider_protocols_map = course_data.get("provider_protocols", {}) or {}
    module_lookup = {}
    unit_lookup = {}
    pending_unlock_rules = []

    for unit_index, unit_data in enumerate(course_data.get("units", []), start=1):
        if not isinstance(unit_data, dict):
            continue
        unit_title = _unit_title(unit_data)
        unit, unit_created = Unit.objects.get_or_create(
            course=course,
            title=unit_title,
            defaults={
                "description": unit_data.get("description", ""),
                "order": unit_data.get("order") or unit_index * 10,
                "is_visible": unit_data.get("is_visible", True),
                "is_locked": unit_data.get("is_locked", False),
                "unlock_rule": unit_data.get("unlock_rule") or {},
            },
        )
        if not unit_created:
            unit_order = unit_data.get("order") or (unit_index * 10 if unit.order == 0 else unit.order)
            updated = False
            for field_name, value in (
                ("description", unit_data.get("description", "")),
                ("order", unit_order),
                ("is_visible", unit_data.get("is_visible", unit.is_visible)),
                ("is_locked", unit_data.get("is_locked", unit.is_locked)),
                ("unlock_rule", unit_data.get("unlock_rule") or unit.unlock_rule or {}),
            ):
                if getattr(unit, field_name) != value:
                    setattr(unit, field_name, value)
                    updated = True
            if updated:
                unit.save()
        from modulearn.learning.services.unit_packages import parse_schedule
        unit.opens_at, unit.closes_at = parse_schedule(unit_data.get("opens_at", unit.opens_at), unit_data.get("closes_at", unit.closes_at))
        seconds = int(unit_data.get('time_limit_seconds', 0) or 0)
        if not 0 <= seconds <= 86400:
            raise ValueError('Section timers must be between 0 and 86400 seconds.')
        unit.time_limit_seconds = seconds
        unit.save(update_fields=["opens_at", "closes_at", "time_limit_seconds"])
        unit_lookup[('title', unit.title)] = unit
        if unit_data.get('id') is not None:
            unit_lookup[('id', str(unit_data['id']))] = unit
        pending_unlock_rules.append((unit, unit_data.get("unlock_rule") or {}, unit_data.get("unlock_rule_portable") or {}))
        logger.debug("Unit %s: %s", "created" if unit_created else "retrieved", unit)

        for module_index, (resource_id, activity) in enumerate(_module_entries_for_unit(unit_data), start=1):
            if not isinstance(activity, dict):
                continue
            title = activity.get("name") or activity.get("title") or f"Untitled Module {module_index}"
            provider_id = activity.get("provider_id", "") or ""
            author_id = activity.get("author_id", activity.get("author", "")) or ""
            platform_name = _activity_platform_name(activity, resource_id, resource_metadata)
            supported_protocols = activity.get("supported_protocols") or provider_protocols_map.get(provider_id, [])
            activity_url_was_supplied = activity.get("url") is not None or activity.get("content_url") is not None
            content_url = activity.get("url", activity.get("content_url", ""))
            raw_module_type = activity.get("module_type") or Module.MODULE_TYPE_IMPORTED
            desired_module_type = normalize_module_type(raw_module_type)
            content_data = deepcopy(activity.get("content_data")) if activity.get("content_data") is not None else None
            legacy_study_step = _normalize_study_step(raw_module_type)
            if legacy_study_step:
                if not isinstance(content_data, dict):
                    content_data = {}
                content_data["study_step"] = legacy_study_step
            replacement = apply_slc_legacy_replacement(
                content_url,
                current_module_type=desired_module_type,
                current_supported_protocols=supported_protocols,
            )
            if replacement:
                logger.info(
                    "Replacing legacy SLC URL during import: %s -> %s",
                    replacement.original_url,
                    replacement.replacement_url,
                )
                content_url = replacement.replacement_url
                desired_module_type = replacement.module_type
                supported_protocols = replacement.supported_protocols
                content_data = apply_replacement_metadata(content_data, replacement)

            module, module_created = Module.objects.get_or_create(
                unit=unit,
                title=title,
                defaults={
                    "module_type": desired_module_type,
                    "order": activity.get("order") or module_index * 10,
                    "description": activity.get("description") or "",
                    "content_url": content_url or None,
                    "provider_id": provider_id,
                    "platform_name": platform_name,
                    "author": author_id,
                    "supported_protocols": supported_protocols,
                    "is_visible": activity.get("is_visible", True),
                    "is_locked": activity.get("is_locked", False),
                    "allow_resubmission": activity.get("allow_resubmission", True),
                    "unlock_rule": activity.get("unlock_rule") or {},
                    "content_data": content_data,
                    "keywords": activity.get("keywords", "") or "",
                    "resource_link_id": activity.get("resource_link_id") or None,
                },
            )

            updated = False
            desired_values = {
                "completion_rule": activity.get("completion_rule", module.completion_rule),
                "order": activity.get("order") or module.order,
                "provider_id": provider_id,
                "module_type": desired_module_type,
                "platform_name": platform_name or module.platform_name,
                "author": author_id,
                "supported_protocols": supported_protocols,
                "is_visible": activity.get("is_visible", module.is_visible),
                "is_graded": activity.get("is_graded", module.is_graded) is True,
                "is_recommendation_only": activity.get("is_recommendation_only", module.is_recommendation_only) is True,
                "is_locked": activity.get("is_locked", module.is_locked),
                "allow_resubmission": activity.get("allow_resubmission", module.allow_resubmission),
                "unlock_rule": activity.get("unlock_rule") or module.unlock_rule or {},
                "keywords": activity.get("keywords", module.keywords) or "",
                "resource_link_id": activity.get("resource_link_id", module.resource_link_id) or None,
            }
            legacy_metadata_description = f"Provider: {provider_id or 'unknown'}, Author: {author_id or 'unknown'}"
            if activity.get("description") is not None:
                desired_values["description"] = activity.get("description") or ""
            elif module.description == legacy_metadata_description:
                desired_values["description"] = ""
            if activity_url_was_supplied:
                desired_values["content_url"] = content_url or None
            if content_data is not None:
                desired_values["content_data"] = content_data

            for field_name, value in desired_values.items():
                if field_name == 'completion_rule' and value not in dict(Module.COMPLETION_RULE_CHOICES):
                    raise ValueError('Invalid activity completion rule.')
                if getattr(module, field_name) != value:
                    setattr(module, field_name, value)
                    updated = True
            if _restore_content_file(module, activity):
                updated = True
            if updated:
                module.save()

            form_data = _form_payload_from_activity(activity)
            if desired_module_type in Module.FORM_LIKE_TYPES:
                ensure_module_form(module, form_data)

            module_lookup[(unit.title, module.title)] = module
            pending_unlock_rules.append((module, activity.get("unlock_rule") or {}, activity.get("unlock_rule_portable") or {}))
            logger.debug("Activity %s: %s", "created" if module_created else "retrieved", module)

    for model_object, raw_rule, portable_rule in pending_unlock_rules:
        resolved_rule = _resolve_unlock_rule(portable_rule, raw_rule, module_lookup, unit_lookup)
        if model_object.unlock_rule != resolved_rule:
            model_object.unlock_rule = resolved_rule
            model_object.save(update_fields=["unlock_rule"])

    if "branch_rules" in course_data:
        ModuleBranchRule.objects.filter(course=course).delete()
        valid_conditions = {value for value, _label in ModuleBranchRule.CONDITION_CHOICES}
        for rule_data in course_data.get("branch_rules") or []:
            source_module = module_lookup.get((rule_data.get("source_unit"), rule_data.get("source_module")))
            target_module = module_lookup.get((rule_data.get("target_unit"), rule_data.get("target_module")))
            condition_type = rule_data.get("condition_type")
            if not source_module or not target_module or condition_type not in valid_conditions:
                continue
            ModuleBranchRule.objects.create(
                course=course,
                source_module=source_module,
                target_module=target_module,
                condition_type=condition_type,
                threshold=rule_data.get("threshold"),
                required_study_condition=(rule_data.get("required_study_condition") or "").strip(),
                priority=rule_data.get("priority") or 0,
                active=rule_data.get("active", True),
            )

    logger.info("Successfully created/updated course: %s", course)
    return course


def export_course_to_json(course, *, course_instance=None, include_file_data=True, unit_ids=None):
    provider_protocols = {}
    units = []
    course_modules_by_id = {}
    prefetched_units = list(course.units.prefetch_related("modules__form__questions").all())
    course_units_by_id = {str(unit.id): unit for unit in prefetched_units}
    for unit in prefetched_units:
        for module in unit.modules.all():
            course_modules_by_id[str(module.id)] = module

    for unit in prefetched_units:
        if unit_ids is not None and unit.id not in unit_ids:
            continue
        activities = {}
        modules = []
        for module in unit.modules.all():
            exported_module_type = normalize_module_type(module.module_type)
            module_type_label = dict(Module.MODULE_TYPE_CHOICES).get(exported_module_type, exported_module_type)
            resource_id = module.platform_name or module.provider_id or module_type_label
            provider_id = module.provider_id or resource_id
            if provider_id and module.supported_protocols:
                provider_protocols[provider_id] = module.supported_protocols

            module_payload = {
                "id": module.id,
                "name": module.title,
                "title": module.title,
                "description": module.description,
                "url": module.content_url or "",
                "content_url": module.content_url or "",
                "module_type": exported_module_type,
                "module_type_label": module_type_label,
                "display_type_label": module.display_type_label,
                "resource_id": resource_id,
                "provider_id": provider_id,
                "platform_name": module.platform_name,
                "author_id": module.author,
                "author": module.author,
                "order": module.order,
                "is_visible": module.is_visible,
                "is_recommendation_only": module.is_recommendation_only,
                "is_graded": module.is_graded,
                "completion_rule": module.completion_rule,
                "is_locked": module.is_locked,
                "allow_resubmission": module.allow_resubmission,
                "unlock_rule": module.unlock_rule or {},
                "unlock_rule_portable": _portable_unlock_rule(module.unlock_rule, course_modules_by_id, course_units_by_id),
                "content_data": module.content_data or {},
                "content_file": _content_file_export_payload(module, include_file_data=include_file_data),
                "keywords": module.keywords,
                "resource_link_id": module.resource_link_id,
                "supported_protocols": module.supported_protocols or [],
                "form": _serialize_module_form(module),
            }
            activities.setdefault(resource_id, []).append(module_payload)
            modules.append(module_payload)

        units.append({
            "id": unit.id,
            "opens_at": unit.opens_at.isoformat() if unit.opens_at else None,
            "time_limit_seconds": unit.time_limit_seconds,
            "closes_at": unit.closes_at.isoformat() if unit.closes_at else None,
            "name": unit.title,
            "title": unit.title,
            "description": unit.description,
            "order": unit.order,
            "is_visible": unit.is_visible,
            "is_locked": unit.is_locked,
            "unlock_rule": unit.unlock_rule or {},
            "unlock_rule_portable": _portable_unlock_rule(unit.unlock_rule, course_modules_by_id, course_units_by_id),
            "activities": activities,
            "modules": modules,
        })

    payload = {
        "schema": MODULEARN_COURSE_EXPORT_SCHEMA,
        "id": course.id,
        "name": course.title,
        "title": course.title,
        "description": course.description,
        "is_locked_for_research": course.is_locked_for_research,
        "plugin_config": normalize_course_plugin_config(course.plugin_config),
        "schedule_timezone": course.schedule_timezone,
        "provider_protocols": provider_protocols,
        "instructors": [
            {
                "username": instructor.username,
                "email": instructor.email,
                "name": instructor.get_full_name(),
            }
            for instructor in course.instructors.all().order_by("username")
        ],
        "branch_rules": [
            {
                "source_unit": rule.source_module.unit.title,
                "source_module": rule.source_module.title,
                "target_unit": rule.target_module.unit.title,
                "target_module": rule.target_module.title,
                "condition_type": rule.condition_type,
                "condition_type_label": rule.get_condition_type_display(),
                "threshold": rule.threshold,
                "required_study_condition": rule.required_study_condition,
                "priority": rule.priority,
                "active": rule.active,
            }
            for rule in course.branch_rules.select_related(
                "source_module",
                "source_module__unit",
                "target_module",
                "target_module__unit",
            ).order_by("source_module__unit__order", "source_module__order", "priority", "id")
        ],
        "units": units,
    }
    if course_instance:
        payload["course_instance"] = {
            "id": course_instance.id,
            "group_name": course_instance.group_name,
            "active": course_instance.active,
            "canvas_course_id": course_instance.canvas_course_id,
            "canvas_assignment_id": course_instance.canvas_assignment_id,
            "lis_outcome_service_url": course_instance.lis_outcome_service_url,
            "instructors": [
                {
                    "username": instructor.username,
                    "email": instructor.email,
                    "name": instructor.get_full_name(),
                }
                for instructor in course_instance.instructors.all().order_by("username")
            ],
        }
    return payload

def send_grade_to_canvas(xml_payload, outcome_service_url, consumer_key, consumer_secret):
    """Helper function to send grades to Canvas via LTI 1.1"""
    
    client = Client(
        client_key=consumer_key,
        client_secret=consumer_secret,
    )
    
    # Generate OAuth1 signature
    oauth_params = client.get_oauth_params()
    oauth_params.append(('oauth_body_hash', signature.sign_plaintext(xml_payload, consumer_secret)))
    
    # Get authorization header
    auth_header = client.get_oauth_signature(
        outcome_service_url,
        http_method='POST',
        oauth_params=oauth_params
    )
    
    headers = {
        'Content-Type': 'application/xml',
        'Authorization': auth_header,
    }
    
    # Send the request
    return requests.post(
        outcome_service_url,
        data=xml_payload,
        headers=headers,
        verify=True
    )

def reset_course_authoring_password(user):
    """Explicit local reset; the remote administrator must synchronize it."""
    new_password = str(uuid.uuid4())
    user.course_authoring_password = new_password
    user.save(update_fields=['course_authoring_password'])
    logger.info("Course-authoring credential reset requested by user_id=%s", user.pk)
    return new_password


def get_course_auth_token(user, retry_on_mismatch=False):
    """Obtain a token without logging credentials or rotating them on failure.

    retry_on_mismatch is retained for caller compatibility; retries cannot repair
    a remote password mismatch and must never silently change local credentials.
    """
    if not user.is_authenticated:
        raise ValueError("User not authenticated")
    if not user.course_authoring_password:
        # Concurrent initial requests must use the same credential. Update only
        # this field, preserving concurrent role/profile changes.
        from django.db.models import Q
        type(user).objects.filter(pk=user.pk).filter(
            Q(course_authoring_password='') | Q(course_authoring_password__isnull=True)
        ).update(course_authoring_password=str(uuid.uuid4()))
        user.refresh_from_db(fields=['course_authoring_password'])
    response = requests.post(
        COURSE_AUTHORING_TOKEN_URL,
        json={"fullname": user.full_name or user.get_full_name() or user.username,
              "email": user.email, "password": user.course_authoring_password},
        timeout=(5, 10),
        allow_redirects=False,
    )
    response.raise_for_status()
    token = response.text.strip()
    if response.is_redirect or not token or token.startswith('<'):
        raise requests.exceptions.RequestException("Invalid authoring token response")
    logger.info("Course-authoring token obtained for user_id=%s", user.pk)
    return token
