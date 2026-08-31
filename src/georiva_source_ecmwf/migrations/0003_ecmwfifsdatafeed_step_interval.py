from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("georiva_source_ecmwf", "0002_ecmwfifsdatafeed"),
    ]

    operations = [
        migrations.AddField(
            model_name="ecmwfifsdatafeed",
            name="step_interval",
            field=models.IntegerField(
                choices=[(3, "3-hourly (6-hourly beyond 144h)"), (6, "6-hourly")],
                default=6,
                help_text=(
                    "Forecast step cadence. The portal serves 3-hourly steps only "
                    "up to 144h; a 3-hourly feed continues 6-hourly beyond that."
                ),
            ),
        ),
    ]
