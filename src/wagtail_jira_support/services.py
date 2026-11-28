import hashlib
import json
from copy import deepcopy

from django.core.cache import cache

from .client import JiraClient
from .conf import get_settings, validate_settings
from .context import build_description, sanitize_source_url
from .exceptions import (
    JiraAPIError,
    JiraConfigurationError,
    JiraConnectionError,
    JiraPermissionError,
    JiraRequestTypeNotFoundError,
    JiraRequestValidationError,
    JiraServiceDeskNotFoundError,
    JiraSubmissionUncertainError,
    JiraUserAmbiguousError,
    JiraUserNotFoundError,
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

    def prepare_request(
        self,
        service_desk_id,
        request_type_id,
        summary,
        description,
        billing_code="",
        source_url="",
    ):
        """Validate and prepare a support request without submitting it."""
        service_desk_id = str(service_desk_id)
        request_type_id = str(request_type_id)

        desk = self.get_service_desk_config(service_desk_id)

        if not isinstance(summary, str) or not summary.strip():
            raise JiraRequestValidationError("A summary is required.")

        if not isinstance(description, str) or not description.strip():
            raise JiraRequestValidationError("A description is required.")

        summary = summary.strip()

        if len(summary) > 255:
            raise JiraRequestValidationError(
                "The summary cannot exceed 255 characters."
            )

        metadata = self.get_request_type_fields(
            service_desk_id,
            request_type_id,
        )

        available_fields = {
            field["fieldId"]: field for field in metadata["requestTypeFields"]
        }

        fields = {}

        # Populate configured default fields.
        for field_id, value in desk.get("default_fields", {}).items():
            if field_id not in available_fields:
                raise JiraConfigurationError(
                    f"Configured default field {field_id} "
                    "is unavailable for this request type."
                )

            fields[field_id] = deepcopy(value)

        # Core request fields always take precedence.
        fields["summary"] = summary

        source_url = sanitize_source_url(source_url)

        fields["description"] = build_description(
            description=description,
            application_name=self.config["APPLICATION_NAME"],
            environment=self.config["ENVIRONMENT"],
            source_url=source_url,
        )

        # Populate the optional URL field when available.
        url_field = desk.get("url_field")

        if source_url and url_field in available_fields:
            fields[url_field] = source_url

        # Populate the optional billing code field when available.
        billing_code_field = desk.get("billing_code_field")

        if (
            isinstance(billing_code, str)
            and billing_code.strip()
            and billing_code_field in available_fields
        ):
            fields[billing_code_field] = billing_code.strip()

        # Ensure all submitted fields are supported by Jira.
        unsupported_fields = set(fields) - set(available_fields)

        if unsupported_fields:
            raise JiraRequestValidationError(
                "The selected request type does not support "
                "all required support request fields."
            )

        # Ensure all required Jira fields have been populated.
        missing_fields = []

        for field_id, definition in available_fields.items():
            if not definition.get("required"):
                continue

            value = fields.get(field_id)

            if value is None or value == "" or value == [] or value == {}:
                missing_fields.append(definition.get("name", field_id))

        if missing_fields:
            raise JiraRequestValidationError(
                "Missing required Jira fields: " + ", ".join(missing_fields)
            )

        return {
            "serviceDeskId": service_desk_id,
            "requestTypeId": request_type_id,
            "requestFieldValues": fields,
        }

    def resolve_requester(self, email):
        """Resolve an email address to an active Jira account ID."""
        if not isinstance(email, str) or not email.strip():
            raise JiraUserNotFoundError(
                "An email address is required to identify the requester in Jira."
            )

        email = email.strip()
        normalized_email = email.casefold()

        with self._get_client() as client:
            users = client.search_users(email)

        if not isinstance(users, list):
            raise JiraAPIError("Jira returned an invalid user search response.")

        matches = []

        for user in users:
            if not isinstance(user, dict):
                raise JiraAPIError("Jira returned an invalid user record.")

            user_email = user.get("emailAddress")

            if not isinstance(user_email, str):
                continue

            if user_email.strip().casefold() == normalized_email:
                matches.append(user)

        if not matches:
            raise JiraUserNotFoundError("Unable to identify a matching Jira account.")

        if len(matches) > 1:
            raise JiraUserAmbiguousError("Multiple Jira accounts match the requester.")

        user = matches[0]

        if user.get("active") is not True:
            raise JiraUserNotFoundError("The matching Jira account is inactive.")

        account_id = user.get("accountId")

        if not isinstance(account_id, str) or not account_id.strip():
            raise JiraUserNotFoundError(
                "The matching Jira account has no valid account ID."
            )

        return account_id.strip()

    def submit_request(
        self,
        service_desk_id,
        request_type_id,
        requester_email,
        summary,
        description,
        billing_code="",
        source_url="",
    ):
        """Submit a validated support request on behalf of a requester."""
        payload = self.prepare_request(
            service_desk_id=service_desk_id,
            request_type_id=request_type_id,
            summary=summary,
            description=description,
            billing_code=billing_code,
            source_url=source_url,
        )

        metadata = self.get_request_type_fields(
            service_desk_id,
            request_type_id,
        )

        if metadata.get("canRaiseOnBehalfOf") is not True:
            raise JiraPermissionError(
                "The Jira integration account cannot raise "
                "requests on behalf of other users."
            )

        account_id = self.resolve_requester(requester_email)

        with self._get_client() as client:
            try:
                result = client.create_request(
                    service_desk_id=payload["serviceDeskId"],
                    request_type_id=payload["requestTypeId"],
                    fields=payload["requestFieldValues"],
                    raise_on_behalf_of=account_id,
                )
            except JiraConnectionError:
                raise JiraSubmissionUncertainError(
                    "Unable to confirm whether Jira created the support request."
                ) from None

        if not isinstance(result, dict):
            raise JiraSubmissionUncertainError(
                "Jira returned an unexpected submission response."
            )

        issue_key = result.get("issueKey")

        if not isinstance(issue_key, str) or not issue_key.strip():
            raise JiraSubmissionUncertainError("Jira did not return a valid issue key.")

        links = result.get("_links")

        if not isinstance(links, dict):
            links = {}

        return {
            "issue_key": issue_key,
            "issue_id": result.get("issueId"),
            "portal_url": links.get("web", ""),
        }
