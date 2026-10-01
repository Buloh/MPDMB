from django.urls import path

from . import views

urlpatterns = [
    path("smeny/", views.shift_month, name="shift_month"),
    path("smeny/", views.shift_month, name="shift_week"),
    path("smeny/typy/", views.shift_type_list, name="shift_type_list"),
    path("smeny/typy/novy/", views.shift_type_create, name="shift_type_create"),
    path(
        "smeny/typy/<int:pk>/upravit/",
        views.shift_type_edit,
        name="shift_type_edit",
    ),
    path("smeny/sablony/", views.schedule_template_list, name="schedule_template_list"),
    path(
        "smeny/sablony/nova/",
        views.schedule_template_create,
        name="schedule_template_create",
    ),
    path(
        "smeny/sablony/<int:pk>/upravit/",
        views.schedule_template_edit,
        name="schedule_template_edit",
    ),
    path(
        "smeny/sablony/prirazeni/",
        views.schedule_assignment_list,
        name="schedule_assignment_list",
    ),
    path(
        "smeny/sablony/prirazeni/nove/",
        views.schedule_assignment_create,
        name="schedule_assignment_create",
    ),
    path(
        "smeny/sablony/prirazeni/<int:pk>/upravit/",
        views.schedule_assignment_edit,
        name="schedule_assignment_edit",
    ),
    path("smeny/fond/", views.work_time_profile_list, name="work_time_profile_list"),
    path(
        "smeny/fond/profil/novy/",
        views.work_time_profile_create,
        name="work_time_profile_create",
    ),
    path(
        "smeny/fond/profil/hromadne/",
        views.work_time_profile_bulk_create,
        name="work_time_profile_bulk_create",
    ),
    path(
        "smeny/fond/predvolby/",
        views.work_time_preset_list,
        name="work_time_preset_list",
    ),
    path(
        "smeny/fond/predvolby/nova/",
        views.work_time_preset_create,
        name="work_time_preset_create",
    ),
    path(
        "smeny/fond/predvolby/<int:pk>/upravit/",
        views.work_time_preset_edit,
        name="work_time_preset_edit",
    ),
    path(
        "smeny/fond/obdobi/nove/",
        views.balancing_period_create,
        name="balancing_period_create",
    ),
    path(
        "smeny/fond/obdobi/hromadne/",
        views.balancing_period_bulk_create,
        name="balancing_period_bulk_create",
    ),
    path("smeny/bunka/", views.shift_cell_assign, name="shift_cell_assign"),
    path("smeny/bunka/modal/", views.shift_cell_modal, name="shift_cell_modal"),
    path(
        "smeny/generovat/",
        views.shift_generate_month,
        name="shift_generate_month",
    ),
    path("smeny/nova/", views.shift_create, name="shift_create"),
    path("smeny/<int:pk>/", views.shift_detail, name="shift_detail"),
    path("smeny/<int:pk>/upravit/", views.shift_edit, name="shift_edit"),
    path("smeny/<int:pk>/publikovat/", views.shift_publish, name="shift_publish"),
    path("smeny/<int:pk>/zrusit/", views.shift_cancel, name="shift_cancel"),
]
