from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('approvals', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalrequest',
            name='request_category',
            field=models.CharField(
                blank=True,
                choices=[('one_off', 'One-off'), ('recurring', 'Recurring')],
                default='',
                max_length=20,
            ),
        ),
    ]
