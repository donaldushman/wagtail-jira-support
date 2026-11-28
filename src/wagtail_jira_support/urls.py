from django.urls import path

from . import views

app_name = "wagtail_jira_support"

urlpatterns = [
    path(
        "",
        views.index,
        name="index",
    ),
    path(
        "confirmation/",
        views.confirmation,
        name="confirmation",
    ),
    path(
        "<int:service_desk_id>/<int:request_type_id>/",
        views.support_request,
        name="request",
    ),
]
