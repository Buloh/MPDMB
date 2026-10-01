from django.urls import path

from . import views

urlpatterns = [
    path("zamestnanci/", views.employee_list, name="employee_list"),
    path("zamestnanci/novy/", views.employee_create, name="employee_create"),
    path("zamestnanci/<int:pk>/", views.employee_detail, name="employee_detail"),
    path("zamestnanci/<int:pk>/upravit/", views.employee_edit, name="employee_edit"),
    path(
        "zamestnanci/<int:pk>/archivovat/",
        views.employee_archive,
        name="employee_archive",
    ),
]
