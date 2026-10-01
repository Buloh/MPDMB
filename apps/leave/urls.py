from django.urls import path

from . import views

urlpatterns = [
    path("dovolena/", views.leave_year, name="leave_year"),
    path(
        "dovolena/zamestnanec/<int:employee_id>/",
        views.leave_employee,
        name="leave_employee",
    ),
    path(
        "dovolena/pracoviste/<int:workplace_id>/",
        views.leave_workplace,
        name="leave_workplace",
    ),
    path(
        "dovolena/plan/formular/",
        views.leave_plan_form_partial,
        name="leave_plan_form_partial",
    ),
    path(
        "dovolena/plan/vytvorit/",
        views.leave_plan_create,
        name="leave_plan_create",
    ),
    path(
        "dovolena/plan/<int:plan_id>/schvalit/",
        views.leave_plan_approve,
        name="leave_plan_approve",
    ),
    path(
        "dovolena/plan/<int:plan_id>/zrusit/",
        views.leave_plan_cancel,
        name="leave_plan_cancel",
    ),
]
