"""Služby docházky: veřejné API (orchestrátor balíčku)."""

from .common import (
    MISSING_EMPLOYMENT_ADHOC_MSG,
    MISSING_EMPLOYMENT_CODE,
    MISSING_EMPLOYMENT_MSG,
    AttendanceConflictError,
    can_access_employee_attendance,
    can_manage_attendance,
    employees_visible_for_attendance,
    is_published_work_shift,
    published_work_shifts_for_month,
    shift_local_day,
    workplaces_for_employee_day,
)
from .matrix import (
    DayAttendanceCell,
    EmployeeAttendanceRow,
    attendance_day_detail,
    month_attendance_matrix,
)
from .mutations import (
    clear_attendance_for_shift,
    confirm_work_interval,
    create_ad_hoc_work_interval,
    delete_ad_hoc_work_interval,
    propose_from_published_shifts,
    set_absence_for_shift,
)

__all__ = [
    "AttendanceConflictError",
    "MISSING_EMPLOYMENT_MSG",
    "MISSING_EMPLOYMENT_ADHOC_MSG",
    "MISSING_EMPLOYMENT_CODE",
    "DayAttendanceCell",
    "EmployeeAttendanceRow",
    "attendance_day_detail",
    "can_access_employee_attendance",
    "can_manage_attendance",
    "clear_attendance_for_shift",
    "confirm_work_interval",
    "create_ad_hoc_work_interval",
    "delete_ad_hoc_work_interval",
    "employees_visible_for_attendance",
    "is_published_work_shift",
    "month_attendance_matrix",
    "propose_from_published_shifts",
    "published_work_shifts_for_month",
    "set_absence_for_shift",
    "shift_local_day",
    "workplaces_for_employee_day",
]
