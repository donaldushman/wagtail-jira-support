from django.urls import path

from . import views

app_name = "wagtail_jira_support"

urlpatterns = [
    path("", views.index, name="index"),
]
