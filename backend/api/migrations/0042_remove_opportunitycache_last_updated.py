# Generated by Django 2.1.2 on 2018-11-16 16:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0041_auto_20181116_1345'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='opportunitycache',
            name='last_updated',
        ),
    ]
