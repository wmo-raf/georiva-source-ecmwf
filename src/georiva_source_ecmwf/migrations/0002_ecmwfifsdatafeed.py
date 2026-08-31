import django.contrib.postgres.fields
import django.core.validators
import django.db.models.deletion
import timezone_field.fields
from django.db import migrations, models

import georiva_source_ecmwf.models


class Migration(migrations.Migration):
    dependencies = [
        ("georivasources", "0001_initial"),
        ("georiva_source_ecmwf", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ECMWFIFSDataFeed",
            fields=[
                (
                    "datafeed_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="georivasources.datafeed",
                    ),
                ),
                (
                    "run_hours",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.IntegerField(choices=[(0, "00Z"), (12, "12Z")]),
                        default=georiva_source_ecmwf.models.default_ifs_run_hours,
                        help_text="Which model runs to fetch from (the oper stream serves 00Z and 12Z out to 360h)",
                        size=None,
                    ),
                ),
                (
                    "start_day",
                    models.IntegerField(
                        default=0,
                        help_text="Forecast start day (0 = analysis time)",
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(15),
                        ],
                    ),
                ),
                (
                    "end_day",
                    models.IntegerField(
                        default=5,
                        help_text="Forecast end day (max 15)",
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(15),
                        ],
                    ),
                ),
                ("display_timezone", timezone_field.fields.TimeZoneField(default="Africa/Nairobi")),
            ],
            options={
                "verbose_name": "ECMWF IFS Data Feed",
            },
            bases=("georivasources.datafeed", models.Model),
        ),
    ]
