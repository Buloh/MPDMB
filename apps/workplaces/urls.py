from django.urls import path

from . import views

urlpatterns = [
    path("pracoviste/", views.workplace_list, name="workplace_list"),
    path("pracoviste/nove/", views.workplace_create, name="workplace_create"),
    path("pracoviste/<int:pk>/", views.workplace_detail, name="workplace_detail"),
    path(
        "pracoviste/<int:pk>/upravit/",
        views.workplace_edit,
        name="workplace_edit",
    ),
    path(
        "pracoviste/<int:pk>/archivovat/",
        views.workplace_archive,
        name="workplace_archive",
    ),
    path(
        "pracoviste/<int:pk>/priradit/",
        views.assignment_create,
        name="workplace_assign",
    ),
]
