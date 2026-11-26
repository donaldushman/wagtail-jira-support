from copy import deepcopy
from urllib.parse import urlsplit

from django.conf import settings

from .exceptions import JiraConfigurationError

DEFAULTS = {
    "ENABLED": False,
    "BASE_URL": "",
    "EMAIL": "",
    "API_TOKEN": "",
    "APPLICATION_NAME": "",
    "ENVIRONMENT": "",
    "TIMEOUT": 10,
    "CACHE_TIMEOUT": 3600,
    "MENU_LABEL": "Request support",
    "MENU_ORDER": 10000,
    "SERVICE_DESKS": [],
}


def get_settings():
    """Return the merged package configuration."""
    config = deepcopy(DEFAULTS)

    overrides = getattr(settings, "WAGTAIL_JIRA_SUPPORT", {})

    if not isinstance(overrides, dict):
        raise JiraConfigurationError("WAGTAIL_JIRA_SUPPORT must be a dictionary.")

    config.update(deepcopy(overrides))

    return config


def is_enabled():
    """Return whether Jira support is enabled."""
    return get_settings()["ENABLED"]


def validate_settings(config=None):
    """Validate the package configuration."""
    if config is None:
        config = get_settings()

    if not config["ENABLED"]:
        return

    required_settings = (
        "BASE_URL",
        "EMAIL",
        "API_TOKEN",
        "APPLICATION_NAME",
        "SERVICE_DESKS",
    )

    for key in required_settings:
        if not config.get(key):
            raise JiraConfigurationError(f"WAGTAIL_JIRA_SUPPORT requires {key}.")

    parsed_url = urlsplit(config["BASE_URL"])

    if (
        parsed_url.scheme != "https"
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise JiraConfigurationError("BASE_URL must be a valid HTTPS URL.")

    for key in ("TIMEOUT", "CACHE_TIMEOUT"):
        value = config[key]

        if type(value) is not int or value <= 0:
            raise JiraConfigurationError(f"{key} must be a positive integer.")

    service_desks = config["SERVICE_DESKS"]

    if not isinstance(service_desks, list):
        raise JiraConfigurationError("SERVICE_DESKS must be a list.")

    seen_ids = set()

    for desk in service_desks:
        if not isinstance(desk, dict):
            raise JiraConfigurationError("Each service desk must be a dictionary.")

        desk_id = desk.get("id")

        if not isinstance(desk_id, str) or not desk_id.isdigit():
            raise JiraConfigurationError(
                "Each service desk requires a numeric string ID."
            )

        if desk_id in seen_ids:
            raise JiraConfigurationError("Duplicate service desk ID.")

        seen_ids.add(desk_id)

        request_types = desk.get("request_types")

        if (
            not isinstance(request_types, list)
            or not request_types
            or not all(
                isinstance(value, str) and value.isdigit() for value in request_types
            )
        ):
            raise JiraConfigurationError(
                f"Service desk {desk_id} requires valid request type IDs."
            )

        if not isinstance(desk.get("default_fields", {}), dict):
            raise JiraConfigurationError(
                f"Service desk {desk_id} default_fields must be a dictionary."
            )
