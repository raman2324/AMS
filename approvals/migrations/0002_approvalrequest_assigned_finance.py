import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('approvals', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalrequest',
            name='assigned_finance',
            field=models.ForeignKey(
                blank=True,
                null=True,
                limit_choices_to={'role': 'finance'},
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_requests',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
