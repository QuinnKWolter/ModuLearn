from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('courses', '0029_unselected_grading_fallback')]
    operations = [migrations.AddField(model_name='course',name='schedule_timezone',field=models.CharField(max_length=64,blank=True,default=''))]
