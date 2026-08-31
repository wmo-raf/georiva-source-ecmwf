from datetime import timedelta
from zoneinfo import ZoneInfo

from django import forms
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from django_extensions.db.models import TimeStampedModel
from timezone_field import TimeZoneField
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel, MultiFieldPanel

from georiva.sources.collection_definitions import (
    CollectionDefinition,
    parse_collection_defs,
)
from georiva.sources.models import DataFeed

from .collection_specs import AIFS_COLLECTIONS, IFS_COLLECTIONS
from .steps import six_hourly_steps

# Kept under its historical name: the AIFS spec predates the IFS feed.
COLLECTIONS = AIFS_COLLECTIONS

RUN_HOUR_CHOICES = [
    (0, "00Z"),
    (6, "06Z"),
    (12, "12Z"),
    (18, "18Z"),
]


def default_run_hours():
    return [0, 12]


class ECMWFAIFSDataFeedForm(WagtailAdminModelForm):
    run_hours = forms.MultipleChoiceField(
        choices=RUN_HOUR_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        initial=[0, 12],
    )

    def clean_run_hours(self):
        # Convert list of strings → list of ints for the ArrayField
        return [int(v) for v in self.cleaned_data.get("run_hours", [])]


class ECMWFAIFSDataFeed(DataFeed, TimeStampedModel):
    """
    ECMWF AIFS Loader profile:
      - Select which model runs to fetch from (00Z, 06Z, 12Z, 18Z)
      - Select forecast day range
      - Each day includes 4 timesteps: +0h, +6h, +12h, +18h
    """

    base_form_class = ECMWFAIFSDataFeedForm

    # Which runs to fetch from
    run_hours = ArrayField(
        models.IntegerField(choices=RUN_HOUR_CHOICES),
        default=default_run_hours,
        help_text="Which model runs to fetch from (e.g., 00Z and 12Z are most common)",
    )

    # Forecast range
    start_day = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(15)],
        help_text="Forecast start day (0 = analysis time)",
    )

    end_day = models.IntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(15)],
        help_text="Forecast end day (max 15)",
    )

    display_timezone = TimeZoneField(
        default="Africa/Nairobi",
    )

    panels = [
        *DataFeed.base_panels,
        MultiFieldPanel(
            [
                FieldPanel("run_hours"),
            ],
            heading="Model Runs",
        ),
        MultiFieldPanel(
            [
                FieldPanel("start_day"),
                FieldPanel("end_day"),
                FieldPanel("display_timezone"),
            ],
            heading="Forecast Range",
        ),
    ]

    class Meta:
        verbose_name = "ECMWF AIFS Data Feed"

    def clean(self):
        super().clean()
        if self.start_day > self.end_day:
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"end_day": "End day must be greater than or equal to start day."}
            )

    # ======================================================
    # Core logic
    # ======================================================

    MAX_STEP = 360
    STEP_INTERVAL = 6
    HOURS_IN_DAY = [0, 6, 12, 18]

    def get_run_hours(self):
        """Returns selected run hours, or all if none selected."""
        if self.run_hours:
            return sorted(self.run_hours)
        return [0, 6, 12, 18]  # Default to all runs

    def compute_steps(self):
        """
        Convert day range → list of forecast step hours, capped at 360h.

        Example:
            start_day=0, end_day=2 → [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66]
        """
        steps = []

        for day in range(self.start_day, self.end_day + 1):
            base_hour = day * 24
            for hour_offset in self.HOURS_IN_DAY:
                step = base_hour + hour_offset
                if step <= self.MAX_STEP:
                    steps.append(step)

        return steps

    def valid_times(self, run_utc=None):
        """
        Returns user-friendly timestamps for each step.
        """
        if run_utc is None:
            run_utc = (
                timezone.now()
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(ZoneInfo("UTC"))
            )

        tz = ZoneInfo(self.display_timezone)

        output = []
        for step in self.compute_steps():
            valid_utc = run_utc + timedelta(hours=step)
            valid_local = valid_utc.astimezone(tz)

            output.append(
                {
                    "step": step,
                    "valid_utc": valid_utc,
                    "valid_local": valid_local,
                    "label": f"{valid_local:%a %d %b %H:%M} (T+{step}h)",
                }
            )

        return output

    def __str__(self):
        runs = ", ".join(f"{h:02d}Z" for h in self.get_run_hours())
        return f"{self.name} ({runs}, Day {self.start_day}–{self.end_day})"

    @classmethod
    def get_wizard_defaults(cls) -> dict:
        return {
            "run_hours": [0, 12],
            "start_day": 0,
            "end_day": 5,
        }

    @classmethod
    def get_catalog_defaults(cls) -> dict:
        return {
            "name": "ECMWF AIFS",
            "file_format": "grib2",
            "description": "ECMWF AIFS global forecast — 0.25° resolution, 6-hourly steps.",
        }

    @classmethod
    def get_collection_definitions(cls) -> list[CollectionDefinition]:
        return parse_collection_defs(AIFS_COLLECTIONS)

    @property
    def data_source_cls(self):
        from .source import ECMWFAIFSDataSource

        return ECMWFAIFSDataSource

    def get_loader_config(self):
        """Get loader configuration dictionary."""
        return {
            "run_hours": self.get_run_hours(),
            "forecast_hours": self.compute_steps(),
        }


IFS_RUN_HOUR_CHOICES = [
    (0, "00Z"),
    (12, "12Z"),
]


def default_ifs_run_hours():
    return [0, 12]


class ECMWFIFSDataFeedForm(WagtailAdminModelForm):
    run_hours = forms.MultipleChoiceField(
        choices=IFS_RUN_HOUR_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        initial=[0, 12],
    )

    def clean_run_hours(self):
        # Convert list of strings -> list of ints for the ArrayField
        return [int(v) for v in self.cleaned_data.get("run_hours", [])]


class ECMWFIFSDataFeed(DataFeed, TimeStampedModel):
    """
    ECMWF IFS (deterministic `oper` stream) feed:
      - Select which model runs to fetch from — only 00Z and 12Z, the
        cycles the `oper` stream serves out to 360h
      - Select forecast day range (0-15)
      - Steps are 6-hourly in this slice: +0h, +6h, +12h, +18h per day
    """

    base_form_class = ECMWFIFSDataFeedForm

    # Which runs to fetch from
    run_hours = ArrayField(
        models.IntegerField(choices=IFS_RUN_HOUR_CHOICES),
        default=default_ifs_run_hours,
        help_text="Which model runs to fetch from (the oper stream serves 00Z and 12Z out to 360h)",
    )

    # Forecast range
    start_day = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(15)],
        help_text="Forecast start day (0 = analysis time)",
    )

    end_day = models.IntegerField(
        default=5,
        validators=[MinValueValidator(0), MaxValueValidator(15)],
        help_text="Forecast end day (max 15)",
    )

    display_timezone = TimeZoneField(
        default="Africa/Nairobi",
    )

    panels = [
        *DataFeed.base_panels,
        MultiFieldPanel(
            [
                FieldPanel("run_hours"),
            ],
            heading="Model Runs",
        ),
        MultiFieldPanel(
            [
                FieldPanel("start_day"),
                FieldPanel("end_day"),
                FieldPanel("display_timezone"),
            ],
            heading="Forecast Range",
        ),
    ]

    class Meta:
        verbose_name = "ECMWF IFS Data Feed"

    def clean(self):
        super().clean()
        if self.start_day > self.end_day:
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"end_day": "End day must be greater than or equal to start day."}
            )

    def get_run_hours(self):
        """Returns selected run hours, or both oper cycles if none selected."""
        if self.run_hours:
            return sorted(self.run_hours)
        return [0, 12]

    def compute_steps(self):
        """Convert day range -> list of forecast step hours, capped at 360h."""
        return six_hourly_steps(self.start_day, self.end_day)

    def valid_times(self, run_utc=None):
        """Returns user-friendly timestamps for each step."""
        if run_utc is None:
            run_utc = (
                timezone.now()
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(ZoneInfo("UTC"))
            )

        tz = ZoneInfo(self.display_timezone)

        output = []
        for step in self.compute_steps():
            valid_utc = run_utc + timedelta(hours=step)
            valid_local = valid_utc.astimezone(tz)

            output.append(
                {
                    "step": step,
                    "valid_utc": valid_utc,
                    "valid_local": valid_local,
                    "label": f"{valid_local:%a %d %b %H:%M} (T+{step}h)",
                }
            )

        return output

    def __str__(self):
        runs = ", ".join(f"{h:02d}Z" for h in self.get_run_hours())
        return f"{self.name} ({runs}, Day {self.start_day}–{self.end_day})"

    @classmethod
    def get_wizard_defaults(cls) -> dict:
        return {
            "run_hours": [0, 12],
            "start_day": 0,
            "end_day": 5,
        }

    @classmethod
    def get_catalog_defaults(cls) -> dict:
        return {
            "name": "ECMWF IFS",
            "file_format": "grib2",
            "description": "ECMWF IFS global deterministic forecast — 0.25° resolution, 6-hourly steps.",
        }

    @classmethod
    def get_collection_definitions(cls) -> list[CollectionDefinition]:
        return parse_collection_defs(IFS_COLLECTIONS)

    @property
    def data_source_cls(self):
        from .source import ECMWFIFSDataSource

        return ECMWFIFSDataSource

    def get_loader_config(self):
        """Get loader configuration dictionary."""
        return {
            "run_hours": self.get_run_hours(),
            "forecast_hours": self.compute_steps(),
        }
