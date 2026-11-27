import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from .conf import get_settings
from .exceptions import (
    JiraRequestTypeNotFoundError,
    JiraRequestValidationError,
    JiraServiceDeskNotFoundError,
    JiraSupportError,
)
from .forms import SupportRequestForm
from .services import JiraSupportService

logger = logging.getLogger(__name__)


def check_support_access(request):
    """Ensure the user is permitted to access Jira support."""
    config = get_settings()

    if not config["ENABLED"]:
        raise Http404

    if not (
        request.user.is_authenticated
        and request.user.is_active
        and request.user.has_perm("wagtailadmin.access_admin")
    ):
        raise PermissionDenied

    return config


@require_GET
def index(request):
    """Display the configured Jira support options."""
    config = check_support_access(request)

    service_desks = []
    error = None

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


@require_http_methods(["GET", "POST"])
def support_request(request, service_desk_id, request_type_id):
    """Display and validate a support request form."""
    config = check_support_access(request)

    service_desk_id = str(service_desk_id)
    request_type_id = str(request_type_id)

    context = {
        "page_title": config["MENU_LABEL"],
        "application_name": config["APPLICATION_NAME"],
        "environment": config["ENVIRONMENT"],
        "form": None,
        "error": None,
        "prepared": False,
    }

    try:
        service = JiraSupportService()

        desk_config = service.get_service_desk_config(service_desk_id)

        request_type = service.get_request_type(
            service_desk_id,
            request_type_id,
        )

        service_desk = next(
            (
                desk
                for desk in service.get_service_desks()
                if str(desk["id"]) == service_desk_id
            ),
            None,
        )

        if service_desk is None:
            raise JiraServiceDeskNotFoundError(
                "The requested service desk is unavailable."
            )

        metadata = service.get_request_type_fields(
            service_desk_id,
            request_type_id,
        )

        available_fields = {field["fieldId"] for field in metadata["requestTypeFields"]}

        show_billing_code = desk_config.get("billing_code_field") in available_fields

        form = SupportRequestForm(
            request.POST if request.method == "POST" else None,
            show_billing_code=show_billing_code,
        )

        context.update(
            {
                "service_desk": service_desk,
                "request_type": request_type,
                "form": form,
            }
        )

        if request.method == "POST" and form.is_valid():
            try:
                service.prepare_request(
                    service_desk_id=service_desk_id,
                    request_type_id=request_type_id,
                    summary=form.cleaned_data["summary"],
                    description=form.cleaned_data["description"],
                    billing_code=form.cleaned_data.get("billing_code", ""),
                )

            except JiraRequestValidationError as exc:
                form.add_error(None, str(exc))

            else:
                # Temporary validation-only behavior.
                # No Jira ticket is created.
                context["prepared"] = True

    except (
        JiraServiceDeskNotFoundError,
        JiraRequestTypeNotFoundError,
    ):
        raise Http404 from None

    except JiraSupportError as exc:
        logger.warning(
            "Unable to prepare Jira support request: %s",
            type(exc).__name__,
        )

        context["error"] = (
            "Support options are temporarily unavailable. Please try again later."
        )

    return render(
        request,
        "wagtail_jira_support/request.html",
        context,
    )
