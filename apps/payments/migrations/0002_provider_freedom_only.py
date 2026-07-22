from django.db import migrations, models


def convert_providers_to_freedom(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Payment.objects.exclude(provider='freedom').update(provider='freedom')


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(convert_providers_to_freedom, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='payment',
            name='provider',
            field=models.CharField(choices=[('freedom', 'Freedom Pay')], max_length=20),
        ),
    ]
