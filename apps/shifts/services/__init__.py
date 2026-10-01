"""Služby pro plán směn: překryvy, verze, publikace, matice.

Veřejné API zůstává na `apps.shifts.services` (re-export z podmodulů).
"""

from apps.shifts.fund import (
    balancing_summaries_for_month,
    calendar_month_fund,
    employee_month_fund,
    format_hours,
    fund_summary_for_employee,
    planned_net_minutes_for_employee_month,
    planned_net_minutes_in_range,
    resolve_daily_fund_minutes,
)
from apps.shifts.services.access import (
    can_manage_shift_plan,
    employees_visible_for_shift_plan,
)
from apps.shifts.services.generation import (
    generate_month_from_templates,
    generate_shifts_from_templates,
    monday_of_week,
    resolve_assignment_for_day,
    resolve_template_type,
)
from apps.shifts.services.matrix import build_month_matrix
from apps.shifts.services.mutations import (
    MAX_SHIFTS_PER_DAY,
    ShiftConflictError,
    apply_shift_type,
    assign_shift_cell,
    cancel_shift,
    create_shift,
    find_overlapping_shifts,
    publish_shift,
    update_shift,
)
from apps.shifts.services.workplaces import (
    employment_covers_month,
    filter_employees_with_employment_in_range,
    format_workplace_assignments_label,
    format_workplace_segments_label,
    nearest_future_workplace_hint,
    primary_workplace_for_month,
    types_available_for_employee_day,
    workplace_for_employee_day,
    workplace_overlapping_month,
    workplace_segments_in_month,
)

__all__ = [
    "MAX_SHIFTS_PER_DAY",
    "ShiftConflictError",
    "apply_shift_type",
    "assign_shift_cell",
    "balancing_summaries_for_month",
    "build_month_matrix",
    "calendar_month_fund",
    "can_manage_shift_plan",
    "cancel_shift",
    "create_shift",
    "employee_month_fund",
    "employees_visible_for_shift_plan",
    "employment_covers_month",
    "filter_employees_with_employment_in_range",
    "find_overlapping_shifts",
    "format_hours",
    "format_workplace_assignments_label",
    "format_workplace_segments_label",
    "fund_summary_for_employee",
    "generate_month_from_templates",
    "generate_shifts_from_templates",
    "monday_of_week",
    "nearest_future_workplace_hint",
    "planned_net_minutes_for_employee_month",
    "planned_net_minutes_in_range",
    "primary_workplace_for_month",
    "publish_shift",
    "resolve_assignment_for_day",
    "resolve_daily_fund_minutes",
    "resolve_template_type",
    "types_available_for_employee_day",
    "update_shift",
    "workplace_for_employee_day",
    "workplace_overlapping_month",
    "workplace_segments_in_month",
]
