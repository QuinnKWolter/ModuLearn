from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('recruitment', '0008_alter_recruitmentsource_condition_strategy')]
    operations = [
        migrations.AddField(model_name='study', name='participant_paced', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='study', name='retry_after_remediation', field=models.BooleanField(default=True)),
    ]
