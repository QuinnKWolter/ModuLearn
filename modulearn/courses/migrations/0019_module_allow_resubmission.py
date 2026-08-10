from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0018_alter_module_module_type_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="module",
            name="allow_resubmission",
            field=models.BooleanField(default=True),
        ),
    ]
