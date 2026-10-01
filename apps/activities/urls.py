from django.urls import path

from . import views

urlpatterns = [
    path("cinnost/", views.activity_day, name="activity_day"),
    path(
        "cinnost/preference/<int:employee_id>/",
        views.activity_preferences,
        name="activity_preferences",
    ),
    path(
        "cinnost/generovat/",
        views.activity_generate,
        name="activity_generate",
    ),
    path(
        "cinnost/vymazat-den/",
        views.activity_clear_day,
        name="activity_clear_day",
    ),
    path(
        "cinnost/slot/formular/",
        views.activity_slot_form,
        name="activity_slot_form",
    ),
    path(
        "cinnost/slot/ulozit/",
        views.activity_slot_save,
        name="activity_slot_save",
    ),
    path(
        "cinnost/denni-ukol/formular/",
        views.activity_day_task_form,
        name="activity_day_task_form",
    ),
    path(
        "cinnost/denni-ukol/ulozit/",
        views.activity_day_task_save,
        name="activity_day_task_save",
    ),
    path(
        "cinnost/polozka/pridat/",
        views.activity_item_create,
        name="activity_item_create",
    ),
    path(
        "cinnost/polozka/<int:item_id>/upravit/",
        views.activity_item_edit,
        name="activity_item_edit",
    ),
    path(
        "cinnost/polozka/<int:item_id>/smazat/",
        views.activity_item_delete,
        name="activity_item_delete",
    ),
    path("cinnost/export/", views.activity_export, name="activity_export"),
    path(
        "cinnost/export.xlsx",
        views.activity_export_xlsx,
        name="activity_export_xlsx",
    ),
    path(
        "cinnost/lokality/",
        views.location_list,
        name="activity_location_list",
    ),
    path(
        "cinnost/lokality/nova/",
        views.location_create,
        name="activity_location_create",
    ),
    path(
        "cinnost/lokality/<int:location_id>/upravit/",
        views.location_edit,
        name="activity_location_edit",
    ),
]
