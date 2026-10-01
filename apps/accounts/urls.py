from django.urls import path

from .views import MpdmbLoginView, MpdmbLogoutView

urlpatterns = [
    path("prihlaseni/", MpdmbLoginView.as_view(), name="login"),
    path("odhlaseni/", MpdmbLogoutView.as_view(), name="logout"),
]
