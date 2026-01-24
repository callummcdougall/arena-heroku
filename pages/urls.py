from django.urls import path, re_path

from .views import page

urlpatterns = [
    path("", page, {"path": "index"}, name="index"),
    re_path(r"^(?P<path>.+)$", page, name="page"),
]
