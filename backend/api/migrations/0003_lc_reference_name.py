# Generated by Django 2.1.1 on 2018-09-20 20:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_auto_20180920_1643'),
    ]

    operations = [
        migrations.AddField(
            model_name='lc',
            name='reference_name',
            field=models.CharField(default='', max_length=50, verbose_name='Name for Reference Purposes'),
            preserve_default=False,
        ),
    ]