from django.db import migrations, models


def delete_hr_users(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    CustomUser.objects.filter(role='hr').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(delete_hr_users, migrations.RunPython.noop),
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
