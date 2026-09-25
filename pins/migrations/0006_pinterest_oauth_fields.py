# Generated for the Pinterest OAuth ("Connect with Pinterest") flow.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0005_automationsettings_overlay_title_on_image'),
    ]

    operations = [
        migrations.AddField(
            model_name='automationsettings',
            name='pinterest_refresh_token',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='automationsettings',
            name='pinterest_token_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='automationsettings',
            name='pinterest_username',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
