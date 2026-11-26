import hashlib
import json

from django.core.cache import cache

from .client import JiraClient
from .conf import get_settings, validate_settings
from .exceptions import (
    JiraAPIError,
    JiraConfigurationError,
    JiraRequestTypeNotFoundError,
    JiraServiceDeskNotFoundError,
)


class JiraSupportService:
    """Application-level services for Jira support requests."""

    def __init__(self):
        self.config = get_settings()
        validate_settings(self.config)

        if not self.config["ENABLED"]:
            raise JiraConfigurationError("Wagtail Jira Support is disabled.")

    def _get_client(self):
        """Create a configured Jira API client."""
        return JiraClient(
            base_url=self.config["BASE_URL"],
            email=self.config["EMAIL"],
            api_token=self.config["API_TOKEN"],
            timeout=self.config["TIMEOUT"],
        )

    def _cache_key(self, *parts):
        """Generate a cache key scoped to the Jira configuration."""
        identity = json.dumps(
            [
                self.config["BASE_URL"].rstrip("/"),
                self.config["EMAIL"],
                self.config["API_TOKEN"],
                *parts,
            ],
            separators=(",", ":"),
        )

        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()

        return f"wagtail_jira_support:{digest}"

    def _get_cached(self, key_parts, loader):
        """Retrieve cached metadata or load it from Jira."""
        key = self._cache_key(*key_parts)

        data = cache.get(key)

        if data is not None:
            return data

        data = loader()

        cache.set(
            key,
            data,
            timeout=self.config["CACHE_TIMEOUT"],
        )

        return data

    def get_service_desk_config(self, service_desk_id):
        """Retrieve configuration for an allowed service desk."""
        service_desk_id = str(service_desk_id)

        for desk in self.config["SERVICE_DESKS"]:
            if desk["id"] == service_desk_id:
                return desk

        raise JiraServiceDeskNotFoundError(
            "The requested service desk is not configured."
        )

    def _validate_request_type(
        self,
        service_desk_id,
        request_type_id,
    ):
        """Ensure a request type is explicitly allowed."""
        desk = self.get_service_desk_config(service_desk_id)

        if str(request_type_id) not in desk["request_types"]:
            raise JiraRequestTypeNotFoundError(
                "The requested request type is not configured."
            )

    def _fetch_service_desks(self):
        with self._get_client() as client:
            return client.get_service_desks()

    def _fetch_request_types(self, service_desk_id):
        with self._get_client() as client:
            return client.get_request_types(service_desk_id)

    def _fetch_request_type_fields(
        self,
        service_desk_id,
        request_type_id,
    ):
        with self._get_client() as client:
            return client.get_request_type_fields(
                service_desk_id,
                request_type_id,
            )

    def get_service_desks(self):
        """Return configured and accessible service desks."""
        data = self._get_cached(
            ("service_desks",),
            self._fetch_service_desks,
        )

        available = {str(desk["id"]): desk for desk in data}

        return [
            available[desk["id"]]
            for desk in self.config["SERVICE_DESKS"]
            if desk["id"] in available
        ]

    def get_request_types(self, service_desk_id):
        """Return explicitly allowed request types."""
        service_desk_id = str(service_desk_id)
        desk = self.get_service_desk_config(service_desk_id)

        data = self._get_cached(
            ("request_types", service_desk_id),
            lambda: self._fetch_request_types(service_desk_id),
        )

        available = {str(item["id"]): item for item in data}

        return [
            available[type_id]
            for type_id in desk["request_types"]
            if type_id in available
        ]

    def get_request_type(
        self,
        service_desk_id,
        request_type_id,
    ):
        """Return metadata for an allowed request type."""
        self._validate_request_type(
            service_desk_id,
            request_type_id,
        )

        request_type_id = str(request_type_id)

        for item in self.get_request_types(service_desk_id):
            if str(item["id"]) == request_type_id:
                return item

        raise JiraRequestTypeNotFoundError(
            "The requested request type is unavailable in Jira."
        )

    def get_request_type_fields(
        self,
        service_desk_id,
        request_type_id,
    ):
        """Return field definitions for an available request type."""
        service_desk_id = str(service_desk_id)
        request_type_id = str(request_type_id)

        self.get_request_type(
            service_desk_id,
            request_type_id,
        )

        def loader():
            data = self._fetch_request_type_fields(
                service_desk_id,
                request_type_id,
            )

            if not isinstance(data, dict) or not isinstance(
                data.get("requestTypeFields"),
                list,
            ):
                raise JiraAPIError("Jira returned invalid request type fields.")

            return data

        return self._get_cached(
            (
                "request_type_fields",
                service_desk_id,
                request_type_id,
            ),
            loader,
        )
