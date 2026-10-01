from django.urls import path

from . import views

urlpatterns = [
    path("dochazka/", views.attendance_month, name="attendance_month"),
    path(
        "dochazka/export/",
        views.attendance_export_xlsx,
        name="attendance_export_xlsx",
    ),
    path("dochazka/den/", views.attendance_day, name="attendance_day"),
    path(
        "dochazka/pridat-praci/",
        views.attendance_adhoc_form,
        name="attendance_adhoc_form",
    ),
    path(
        "dochazka/ad-hoc/<int:interval_id>/smazat/",
        views.attendance_adhoc_delete,
        name="attendance_adhoc_delete",
    ),
    path(
        "dochazka/smena/<int:shift_id>/potvrdit/",
        views.attendance_confirm,
        name="attendance_confirm",
    ),
    path(
        "dochazka/smena/<int:shift_id>/upravit/",
        views.attendance_confirm_form,
        name="attendance_confirm_form",
    ),
    path(
        "dochazka/smena/<int:shift_id>/absence/",
        views.attendance_absence,
        name="attendance_absence",
    ),
    path(
        "dochazka/smena/<int:shift_id>/zrusit/",
        views.attendance_clear,
        name="attendance_clear",
    ),
    path(
        "dochazka/navrhy/",
        views.attendance_propose,
        name="attendance_propose",
    ),
]
