from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("recruitment", "0003_participant_session_external_session_unique"),
    ]

    operations = [
        migrations.AlterField(
            model_name="recruitmentsource",
            name="condition_labels",
            field=models.CharField(
                blank=True,
                help_text="Single study condition label for this course session/source, e.g. control.",
                max_length=255,
            ),
        ),
    ]
