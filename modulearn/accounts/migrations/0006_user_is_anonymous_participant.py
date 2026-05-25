from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_make_user_roles_exclusive"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_anonymous_participant",
            field=models.BooleanField(default=False),
        ),
    ]
