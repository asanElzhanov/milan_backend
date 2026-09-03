from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms', '0001_initial'),
    ]

    operations = [
        migrations.RenameField('staticpage', old_name='title', new_name='title_ru'),
        migrations.RenameField('staticpage', old_name='content', new_name='content_ru'),
        migrations.AddField(
            model_name='staticpage',
            name='title_kz',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='название (каз.)'),
        ),
        migrations.AddField(
            model_name='staticpage',
            name='title_en',
            field=models.CharField(blank=True, default='', max_length=200, verbose_name='название (англ.)'),
        ),
        migrations.AddField(
            model_name='staticpage',
            name='content_kz',
            field=models.TextField(blank=True, default='', verbose_name='контент (каз.)'),
        ),
        migrations.AddField(
            model_name='staticpage',
            name='content_en',
            field=models.TextField(blank=True, default='', verbose_name='контент (англ.)'),
        ),
        migrations.AlterModelOptions(
            name='staticpage',
            options={'ordering': ['title_ru'], 'verbose_name': 'статическая страница', 'verbose_name_plural': 'статические страницы'},
        ),
    ]
