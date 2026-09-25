# Real Pinterest OAuth tokens (especially with continuous_refresh) can run
# past 500 characters, which raised:
#   psycopg.errors.StringDataRightTruncation: value too long for type
#   character varying(500)
# in pinterest_oauth_callback on Postgres. Switching both token fields from
# CharField(max_length=500) to an unbounded TextField.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pins', '0006_pinterest_oauth_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='automationsettings',
            name='pinterest_access_token',
            field=models.TextField(blank=True, help_text='Pinterest API access token (stored server-side, never shown in the UI).'),
        ),
        migrations.AlterField(
            model_name='automationsettings',
            name='pinterest_refresh_token',
            field=models.TextField(blank=True),
        ),
    ]
