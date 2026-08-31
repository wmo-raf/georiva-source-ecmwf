"""
Forecast step computation for the ECMWF Open Data feeds.

Pure functions (no Django) so feed step logic is testable without a
configured settings module. Terminology follows the core glossary:
*run hour* is the initialisation hour, *step* the forecast lead hour.
"""

MAX_STEP = 360
HOURS_IN_DAY = (0, 6, 12, 18)


def six_hourly_steps(start_day, end_day, max_step=MAX_STEP):
    """
    Step hours for an inclusive forecast day range at 6-hourly cadence,
    capped at ``max_step``.

    Example:
        six_hourly_steps(0, 2) -> [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66]
    """
    steps = []
    for day in range(start_day, end_day + 1):
        for hour_offset in HOURS_IN_DAY:
            step = day * 24 + hour_offset
            if step <= max_step:
                steps.append(step)
    return steps
