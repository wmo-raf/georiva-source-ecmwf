"""
Forecast step computation for the ECMWF Open Data feeds.

Pure functions (no Django) so feed step logic is testable without a
configured settings module. Terminology follows the core glossary:
*run hour* is the initialisation hour, *step* the forecast lead hour.
"""

MAX_STEP = 360
HOURS_IN_DAY = (0, 6, 12, 18)

# The open-data portal publishes IFS oper 3-hourly only up to this lead
# hour; beyond it only 6-hourly steps exist (to MAX_STEP).
THREE_HOURLY_MAX_STEP = 144


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


def ifs_steps(start_day, end_day, step_interval=6, max_step=MAX_STEP):
    """
    Step hours for an inclusive forecast day range at the feed's chosen
    cadence, honouring the portal's piecewise rule: 3-hourly steps exist
    only up to 144h, so a 3-hourly feed silently continues 6-hourly
    beyond, capped at ``max_step``.

    Example:
        ifs_steps(6, 6, 3) -> [144, 150, 156, 162]
    """
    if step_interval == 6:
        return six_hourly_steps(start_day, end_day, max_step)

    steps = []
    for day in range(start_day, end_day + 1):
        for hour_offset in range(0, 24, step_interval):
            step = day * 24 + hour_offset
            if step > max_step:
                continue
            if step > THREE_HOURLY_MAX_STEP and step % 6:
                continue
            steps.append(step)
    return steps
