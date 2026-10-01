"""URL konfigurace projektu MPDMB."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.employees.urls")),
    path("", include("apps.workplaces.urls")),
    path("", include("apps.shifts.urls")),
    path("", include("apps.attendance.urls")),
    path("", include("apps.activities.urls")),
    path("", include("apps.leave.urls")),
    path("", include("apps.technika.urls")),
    path("", include("apps.documents.urls")),
    path("", include("apps.core.urls")),
]
