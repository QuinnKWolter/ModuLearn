from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('courses', '0023_recommendationprogress_retired_at')]
    operations = [migrations.AlterField(
        model_name='moduleprogressevent', name='event_type',
        field=models.CharField(max_length=32, choices=[
            ('provider_event', 'Provider Interaction'), ('attempt', 'Scored Attempt'),
            ('launch', 'Launch'), ('iframe_load', 'Iframe Load'), ('tab_blur', 'Tab Blur'), ('tab_focus', 'Tab Focus'),
            ('progress', 'Progress'), ('completion', 'Completion'), ('outcome', 'Outcome'), ('reopened', 'Reopened'),
        ]),
    )]
