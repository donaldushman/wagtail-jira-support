from urllib.parse import urlsplit

import requests

from .exceptions import (
    JiraAPIError,
    JiraAuthenticationError,
    JiraConnectionError,
    JiraPermissionError,
    JiraSubmissionUncertainError,
)


class JiraClient:
    """Client for the Jira Cloud Service Management REST API."""

    def __init__(
        self,
        base_url,
        email,
        api_token,
        timeout=10,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def close(self):
        """Close the underlying HTTP session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _request(self, method, path, **kwargs):
        """Perform a request and return the decoded JSON response."""
        parsed_path = urlsplit(path)

        if parsed_path.scheme or parsed_path.netloc or not path.startswith("/"):
            raise JiraAPIError("Invalid Jira API path.")

        url = f"{self.base_url}{path}"

        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout,
                allow_redirects=False,
                **kwargs,
            )
        except requests.Timeout:
            raise JiraConnectionError("The Jira API request timed out.") from None
        except requests.RequestException:
            raise JiraConnectionError("Unable to communicate with Jira.") from None

        if response.status_code == 401:
            raise JiraAuthenticationError("Jira authentication failed.")

        if response.status_code == 403:
            raise JiraPermissionError("Permission denied by Jira.")

        if method.upper() == "POST" and response.status_code >= 500:
            raise JiraSubmissionUncertainError(
                "Jira encountered a server error during submission. "
                "The outcome could not be confirmed."
            )

        if not 200 <= response.status_code < 300:
            raise JiraAPIError(f"Jira returned HTTP {response.status_code}.")

        if response.status_code == 204:
            return None

        try:
            return response.json()
        except ValueError:
            if method.upper() == "POST":
                raise JiraSubmissionUncertainError(
                    "Jira accepted the request but returned an invalid JSON response."
                ) from None

            raise JiraAPIError("Jira returned an invalid JSON response.") from None

    def _get_paginated(self, path, params=None):
        """Retrieve all pages from a Jira Service Management endpoint."""
        results = []
        params = dict(params or {})
        params.setdefault("limit", 50)
        params.setdefault("start", 0)

        while True:
            data = self._request(
                "GET",
                path,
                params=params,
            )

            if (
                not isinstance(data, dict)
                or not isinstance(data.get("values"), list)
                or not isinstance(data.get("isLastPage"), bool)
            ):
                raise JiraAPIError("Jira returned an invalid paginated response.")

            values = data["values"]
            results.extend(values)

            if data["isLastPage"]:
                break

            if not values:
                raise JiraAPIError("Jira returned an unexpected empty page.")

            params["start"] += len(values)

        return results

    def get_current_user(self):
        """Retrieve the authenticated Jira account."""
        return self._request(
            "GET",
            "/rest/api/3/myself",
        )

    def get_service_desks(self):
        """Retrieve accessible service desks."""
        return self._get_paginated(
            "/rest/servicedeskapi/servicedesk",
        )

    def get_request_types(self, service_desk_id):
        """Retrieve request types for a service desk."""
        return self._get_paginated(
            f"/rest/servicedeskapi/servicedesk/{service_desk_id}/requesttype",
        )

    def get_request_type_fields(
        self,
        service_desk_id,
        request_type_id,
    ):
        """Retrieve field definitions for a request type."""
        return self._request(
            "GET",
            f"/rest/servicedeskapi/servicedesk/"
            f"{service_desk_id}/requesttype/"
            f"{request_type_id}/field",
        )

    def search_users(self, query):
        """Search Jira users."""
        return self._request(
            "GET",
            "/rest/api/3/user/search",
            params={
                "query": query,
                "maxResults": 50,
            },
        )

    def create_request(
        self,
        service_desk_id,
        request_type_id,
        fields,
        raise_on_behalf_of=None,
    ):
        """Create a Jira Service Management customer request."""
        payload = {
            "serviceDeskId": str(service_desk_id),
            "requestTypeId": str(request_type_id),
            "requestFieldValues": fields,
        }

        if raise_on_behalf_of:
            payload["raiseOnBehalfOf"] = raise_on_behalf_of

        return self._request(
            "POST",
            "/rest/servicedeskapi/request",
            json=payload,
        )
