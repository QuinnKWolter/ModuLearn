from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0005_moduleaccesslog_moduleform_moduleformanswer_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="is_locked_for_research",
            field=models.BooleanField(default=False),
        ),
    ]
