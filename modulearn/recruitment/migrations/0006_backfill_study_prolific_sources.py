from django.db import migrations


def create_default_prolific_sources(apps, schema_editor):
    Study = apps.get_model("recruitment", "Study")
    RecruitmentSource = apps.get_model("recruitment", "RecruitmentSource")

    for study in Study.objects.all().order_by("id"):
        exists = RecruitmentSource.objects.filter(
            study_id=study.id,
            platform="prolific",
        ).exists()
        if exists:
            continue
        RecruitmentSource.objects.create(
            study_id=study.id,
            platform="prolific",
            label="Prolific",
            is_active=True,
            condition_strategy="balanced",
            condition_labels="",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0005_study_studycondition_alter_recruitmentsource_options_and_more"),
    ]

    operations = [
        migrations.RunPython(create_default_prolific_sources, migrations.RunPython.noop),
    ]
