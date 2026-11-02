from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('courses', '0032_alter_moduleprogressevent_event_type')]
    operations = [migrations.AddField(model_name='module', name='completion_rule',
        field=models.CharField(max_length=20, default='provider',
            choices=[('provider', 'Provider completion'), ('submission', 'First submission')],
            help_text='First submission completes the activity regardless of correctness; scores and attempts remain separate.'))]
