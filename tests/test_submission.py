from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from wagtail_jira_support.exceptions import (
    JiraAPIError,
    JiraConnectionError,
    JiraPermissionError,
    JiraRequestTypeNotFoundError,
    JiraRequestValidationError,
    JiraServiceDeskNotFoundError,
    JiraSubmissionUncertainError,
    JiraUserAmbiguousError,
    JiraUserNotFoundError,
)
from wagtail_jira_support.services import JiraSupportService

VALID_CONFIG = {
    "ENABLED": True,
    "BASE_URL": "https://example.atlassian.net",
    "EMAIL": "integration@example.com",
    "API_TOKEN": "test-token",
    "APPLICATION_NAME": "Example Website",
    "ENVIRONMENT": "development",
    "SERVICE_DESKS": [
        {
            "id": "12",
            "request_types": ["100"],
            "default_fields": {
                "customfield_10078": {"id": "10172"},
            },
            "url_field": "customfield_10080",
            "billing_code_field": "customfield_10093",
        },
    ],
}


VALID_USER = {
    "accountId": "example-account-id",
    "emailAddress": "editor@example.com",
    "active": True,
}


VALID_RESPONSE = {
    "issueId": "12345",
    "issueKey": "WD-123",
    "_links": {
        "web": ("https://example.atlassian.net/servicedesk/customer/portal/12/WD-123"),
    },
}


@override_settings(
    WAGTAIL_JIRA_SUPPORT=VALID_CONFIG,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    },
)
class SubmissionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        self.service = JiraSupportService()

        patcher = patch("wagtail_jira_support.services.JiraClient")

        self.client_class = patcher.start()
        self.addCleanup(patcher.stop)

        self.client = self.client_class.return_value.__enter__.return_value

        self.client.get_request_types.return_value = [
            {
                "id": "100",
                "name": "Report a website problem",
            },
        ]

        self.client.get_request_type_fields.return_value = {
            "canRaiseOnBehalfOf": True,
            "requestTypeFields": [
                {
                    "fieldId": "summary",
                    "required": True,
                },
                {
                    "fieldId": "description",
                    "required": False,
                },
                {
                    "fieldId": "customfield_10078",
                    "required": True,
                },
                {
                    "fieldId": "customfield_10080",
                    "required": False,
                },
                {
                    "fieldId": "customfield_10093",
                    "required": False,
                },
            ],
        }

        self.client.search_users.return_value = [
            VALID_USER.copy(),
        ]

        self.client.create_request.return_value = VALID_RESPONSE.copy()

    def submit(self, **overrides):
        """Submit a request using valid defaults."""
        kwargs = {
            "service_desk_id": "12",
            "request_type_id": "100",
            "requester_email": "editor@example.com",
            "summary": "Example problem",
            "description": "Something is not working.",
            "billing_code": "ABC-123",
            "source_url": "https://example.com/page/",
        }

        kwargs.update(overrides)

        return self.service.submit_request(**kwargs)

    def test_successful_submission(self):
        result = self.submit()

        self.assertEqual(
            result,
            {
                "issue_key": "WD-123",
                "issue_id": "12345",
                "portal_url": VALID_RESPONSE["_links"]["web"],
            },
        )

    def test_submission_uses_correct_requester(self):
        self.submit()

        self.client.search_users.assert_called_once_with("editor@example.com")

        kwargs = self.client.create_request.call_args.kwargs

        self.assertEqual(
            kwargs["raise_on_behalf_of"],
            "example-account-id",
        )

    def test_submission_uses_correct_service_desk(self):
        self.submit()

        kwargs = self.client.create_request.call_args.kwargs

        self.assertEqual(kwargs["service_desk_id"], "12")
        self.assertEqual(kwargs["request_type_id"], "100")

    def test_submission_includes_prepared_fields(self):
        self.submit()

        fields = self.client.create_request.call_args.kwargs["fields"]

        self.assertEqual(
            fields["summary"],
            "Example problem",
        )

        self.assertIn(
            "Something is not working.",
            fields["description"],
        )

        self.assertIn(
            "Application: Example Website",
            fields["description"],
        )

        self.assertIn(
            "Environment: development",
            fields["description"],
        )

        self.assertEqual(
            fields["customfield_10078"],
            {"id": "10172"},
        )

        self.assertEqual(
            fields["customfield_10093"],
            "ABC-123",
        )

        self.assertEqual(
            fields["customfield_10080"],
            "https://example.com/page/",
        )

    def test_submission_sanitizes_source_url(self):
        self.submit(source_url=("https://example.com/page/?token=secret#section"))

        fields = self.client.create_request.call_args.kwargs["fields"]

        self.assertEqual(
            fields["customfield_10080"],
            "https://example.com/page/",
        )

        self.assertNotIn("secret", fields["description"])
        self.assertNotIn("#section", fields["description"])

    def test_submission_without_optional_fields(self):
        self.submit(
            billing_code="",
            source_url="",
        )

        fields = self.client.create_request.call_args.kwargs["fields"]

        self.assertNotIn("customfield_10093", fields)
        self.assertNotIn("customfield_10080", fields)

    def test_successful_submission_creates_exactly_one_request(self):
        self.submit()

        self.client.create_request.assert_called_once()

    def test_request_type_metadata_is_cached(self):
        self.submit()

        self.client.get_request_type_fields.assert_called_once()

    def test_invalid_summary_prevents_submission(self):
        with self.assertRaises(JiraRequestValidationError):
            self.submit(summary="")

        self.client.search_users.assert_not_called()
        self.client.create_request.assert_not_called()

    def test_invalid_description_prevents_submission(self):
        with self.assertRaises(JiraRequestValidationError):
            self.submit(description="")

        self.client.search_users.assert_not_called()
        self.client.create_request.assert_not_called()

    def test_unconfigured_service_desk_prevents_submission(self):
        with self.assertRaises(JiraServiceDeskNotFoundError):
            self.submit(service_desk_id="999")

        self.client.search_users.assert_not_called()
        self.client.create_request.assert_not_called()

    def test_unconfigured_request_type_prevents_submission(self):
        with self.assertRaises(JiraRequestTypeNotFoundError):
            self.submit(request_type_id="999")

        self.client.search_users.assert_not_called()
        self.client.create_request.assert_not_called()

    def test_missing_requester_email_prevents_submission(self):
        with self.assertRaises(JiraUserNotFoundError):
            self.submit(requester_email="")

        self.client.create_request.assert_not_called()

    def test_missing_requester_account_prevents_submission(self):
        self.client.search_users.return_value = []

        with self.assertRaises(JiraUserNotFoundError):
            self.submit()

        self.client.create_request.assert_not_called()

    def test_ambiguous_requester_prevents_submission(self):
        self.client.search_users.return_value = [
            VALID_USER.copy(),
            {
                **VALID_USER,
                "accountId": "another-account-id",
            },
        ]

        with self.assertRaises(JiraUserAmbiguousError):
            self.submit()

        self.client.create_request.assert_not_called()

    def test_inactive_requester_prevents_submission(self):
        self.client.search_users.return_value = [
            {
                **VALID_USER,
                "active": False,
            },
        ]

        with self.assertRaises(JiraUserNotFoundError):
            self.submit()

        self.client.create_request.assert_not_called()

    def test_missing_raise_on_behalf_permission(self):
        self.client.get_request_type_fields.return_value["canRaiseOnBehalfOf"] = False

        with self.assertRaises(JiraPermissionError):
            self.submit()

        self.client.search_users.assert_not_called()
        self.client.create_request.assert_not_called()

    def test_missing_raise_on_behalf_metadata(self):
        self.client.get_request_type_fields.return_value.pop("canRaiseOnBehalfOf")

        with self.assertRaises(JiraPermissionError):
            self.submit()

        self.client.create_request.assert_not_called()

    def test_requester_lookup_connection_error(self):
        self.client.search_users.side_effect = JiraConnectionError("Connection failed.")

        with self.assertRaises(JiraConnectionError):
            self.submit()

        self.client.create_request.assert_not_called()

    def test_jira_rejection_is_propagated(self):
        self.client.create_request.side_effect = JiraAPIError("Jira returned HTTP 400.")

        with self.assertRaises(JiraAPIError):
            self.submit()

        self.client.create_request.assert_called_once()

    def test_jira_permission_error_is_propagated(self):
        self.client.create_request.side_effect = JiraPermissionError(
            "Permission denied."
        )

        with self.assertRaises(JiraPermissionError):
            self.submit()

        self.client.create_request.assert_called_once()

    def test_submission_connection_failure_is_uncertain(self):
        self.client.create_request.side_effect = JiraConnectionError(
            "Connection failed."
        )

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

        self.client.create_request.assert_called_once()

    def test_uncertain_submission_error_is_propagated(self):
        self.client.create_request.side_effect = JiraSubmissionUncertainError(
            "Unable to confirm submission."
        )

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

        self.client.create_request.assert_called_once()

    def test_invalid_submission_response(self):
        self.client.create_request.return_value = []

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

        self.client.create_request.assert_called_once()

    def test_empty_submission_response(self):
        self.client.create_request.return_value = None

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

    def test_missing_issue_key(self):
        self.client.create_request.return_value = {
            "issueId": "12345",
        }

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

    def test_invalid_issue_key(self):
        self.client.create_request.return_value = {
            "issueKey": 12345,
        }

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

    def test_empty_issue_key(self):
        self.client.create_request.return_value = {
            "issueKey": "   ",
        }

        with self.assertRaises(JiraSubmissionUncertainError):
            self.submit()

    def test_missing_portal_url(self):
        self.client.create_request.return_value = {
            "issueId": "12345",
            "issueKey": "WD-123",
        }

        result = self.submit()

        self.assertEqual(result["issue_key"], "WD-123")
        self.assertEqual(result["portal_url"], "")

    def test_invalid_links_response(self):
        self.client.create_request.return_value = {
            "issueId": "12345",
            "issueKey": "WD-123",
            "_links": [],
        }

        result = self.submit()

        self.assertEqual(result["issue_key"], "WD-123")
        self.assertEqual(result["portal_url"], "")

    def test_missing_web_link(self):
        self.client.create_request.return_value = {
            "issueId": "12345",
            "issueKey": "WD-123",
            "_links": {
                "agent": ("https://example.atlassian.net/browse/WD-123"),
            },
        }

        result = self.submit()

        self.assertEqual(result["issue_key"], "WD-123")
        self.assertEqual(result["portal_url"], "")

    def test_invalid_portal_url_does_not_invalidate_submission(self):
        self.client.create_request.return_value = {
            "issueId": "12345",
            "issueKey": "WD-123",
            "_links": {
                "web": "https://other.example.com/request/",
            },
        }

        result = self.submit()

        self.assertEqual(result["issue_key"], "WD-123")
        self.assertEqual(result["portal_url"], "")
