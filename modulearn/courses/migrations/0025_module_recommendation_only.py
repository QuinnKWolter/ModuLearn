from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('courses', '0024_moduleprogressevent_provider_events')]
    operations = [migrations.AddField(
        model_name='module', name='is_recommendation_only',
        field=models.BooleanField(default=False, help_text='Available only as isolated recommendation practice; excluded from course requirements.'),
    )]
