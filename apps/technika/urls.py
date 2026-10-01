from django.urls import path

from . import views

urlpatterns = [
    path("technika/", views.vehicle_list, name="vehicle_list"),
    path("technika/nove/", views.vehicle_create, name="vehicle_create"),
    path("technika/<int:pk>/", views.vehicle_detail, name="vehicle_detail"),
    path("technika/<int:pk>/upravit/", views.vehicle_edit, name="vehicle_edit"),
    path(
        "technika/<int:pk>/archivovat/",
        views.vehicle_archive,
        name="vehicle_archive",
    ),
]
