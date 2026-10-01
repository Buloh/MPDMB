from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("provoz/", views.ops_hub, name="ops_hub"),
    path("administrace/", views.admin_hub, name="admin_hub"),
    path("health/", views.health, name="health"),
    path("napoveda/", views.help_index, name="help"),
    path("napoveda/<path:path>", views.help_file, name="help_file"),
]
