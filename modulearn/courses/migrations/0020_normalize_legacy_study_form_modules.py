from django.db import migrations, models


LEGACY_TO_STEP = {
    "study_consent": "consent",
    "study_instructions": "instructions",
    "study_pretest": "pretest",
    "study_posttest": "posttest",
    "study_debrief": "debrief",
}


def _default_payload(step, title, description, allow_resubmission):
    defaults = {
        "consent": {
            "instructions": "Review the study information carefully. Submit this form only if you agree to participate.",
            "submit_button_label": "I Consent",
            "questions": [
                {
                    "prompt": "I have read the study information and agree to participate.",
                    "question_type": "single_choice",
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
                    "question_type": "single_choice",
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
                    "question_type": "short_answer",
                    "options": [],
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
                    "question_type": "short_answer",
                    "options": [],
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
                    "question_type": "single_choice",
                    "options": ["Complete"],
                    "required": True,
                }
            ],
        },
    }
    payload = defaults.get(step) or {
        "instructions": description or f"Complete {title or 'this form'} to continue.",
        "submit_button_label": "Submit",
        "questions": [
            {
                "prompt": "Confirm completion.",
                "question_type": "single_choice",
                "options": ["Complete"],
                "required": True,
            }
        ],
    }
    return {**payload, "allow_resubmission": bool(allow_resubmission)}


def normalize_legacy_study_modules(apps, schema_editor):
    Module = apps.get_model("courses", "Module")
    ModuleForm = apps.get_model("courses", "ModuleForm")
    ModuleFormQuestion = apps.get_model("courses", "ModuleFormQuestion")

    for module in Module.objects.filter(module_type__in=LEGACY_TO_STEP):
        step = LEGACY_TO_STEP[module.module_type]
        content_data = module.content_data if isinstance(module.content_data, dict) else {}
        content_data = {**content_data, "study_step": step}
        payload = _default_payload(step, module.title, module.description, module.allow_resubmission)

        module_form, _created = ModuleForm.objects.get_or_create(
            module=module,
            defaults={
                "instructions": payload["instructions"],
                "submit_button_label": payload["submit_button_label"],
                "allow_resubmission": payload["allow_resubmission"],
            },
        )
        if not ModuleFormQuestion.objects.filter(form=module_form).exists():
            for index, question in enumerate(payload["questions"], start=1):
                ModuleFormQuestion.objects.create(
                    form=module_form,
                    prompt=question["prompt"],
                    question_type=question["question_type"],
                    required=question.get("required", True),
                    order=index * 10,
                    options=question.get("options", []),
                )

        module.module_type = "form"
        module.content_data = content_data
        module.save(update_fields=["module_type", "content_data"])


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0019_module_allow_resubmission"),
    ]

    operations = [
        migrations.RunPython(normalize_legacy_study_modules, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="module",
            name="module_type",
            field=models.CharField(
                choices=[
                    ("imported", "Imported Activity"),
                    ("external_link", "External Link"),
                    ("splice_smart_content", "Smart Learning Content"),
                    ("file", "Uploaded File"),
                    ("form", "Form / Survey"),
                ],
                default="imported",
                max_length=32,
            ),
        ),
    ]
