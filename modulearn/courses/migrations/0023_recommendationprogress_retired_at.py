from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('courses', '0022_isolated_recommendation_practice')]
    operations = [migrations.AddField(
        model_name='recommendationprogress', name='retired_at',
        field=models.DateTimeField(null=True, blank=True),
    )]
