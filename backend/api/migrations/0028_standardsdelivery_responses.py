# Generated by Django 2.1.1 on 2018-11-05 20:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_auto_20181105_1754'),
    ]

    operations = [
        migrations.AddField(
            model_name='standardsdelivery',
            name='responses',
            field=models.IntegerField(default=0),
            preserve_default=False,
        ),
    ]