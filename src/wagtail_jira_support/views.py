import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .conf import get_settings
from .exceptions import JiraSupportError
from .services import JiraSupportService

logger = logging.getLogger(__name__)


@require_GET
def index(request):
    """Display the configured Jira support options."""
    config = get_settings()

    if not config["ENABLED"]:
        raise Http404

    if not (
        request.user.is_authenticated
        and request.user.is_active
        and request.user.has_perm("wagtailadmin.access_admin")
    ):
        raise PermissionDenied

    service_desks = []
    error = None

    try:
        service = JiraSupportService()

        for desk in service.get_service_desks():
            service_desks.append(
                {
                    "id": desk["id"],
                    "name": desk["projectName"],
                    "request_types": service.get_request_types(desk["id"]),
                }
            )

    except JiraSupportError as exc:
        logger.warning(
            "Unable to retrieve Jira support metadata: %s",
            type(exc).__name__,
        )

        service_desks = []
        error = "Support options are temporarily unavailable. Please try again later."

    return render(
        request,
        "wagtail_jira_support/index.html",
        {
            "page_title": config["MENU_LABEL"],
            "application_name": config["APPLICATION_NAME"],
            "environment": config["ENVIRONMENT"],
            "service_desks": service_desks,
            "error": error,
        },
    )
