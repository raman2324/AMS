from django.db import migrations, models


def convert_hr_to_finance(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(role='hr').update(role='finance')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(convert_hr_to_finance, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('employee', 'Employee'),
                    ('manager', 'Manager'),
                    ('finance', 'Finance'),
                    ('it', 'IT'),
                    ('admin', 'Admin'),
                ],
                default='employee',
                max_length=20,
            ),
        ),
    ]
