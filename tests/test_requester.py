from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from wagtail_jira_support.exceptions import (
    JiraAPIError,
    JiraConnectionError,
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
    "SERVICE_DESKS": [
        {
            "id": "12",
            "request_types": ["100"],
        },
    ],
}


VALID_USER = {
    "accountId": "example-account-id",
    "displayName": "Example User",
    "emailAddress": "editor@example.com",
    "active": True,
    "accountType": "atlassian",
}


@override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
class RequesterResolutionTests(SimpleTestCase):
    def setUp(self):
        self.service = JiraSupportService()

        patcher = patch("wagtail_jira_support.services.JiraClient")

        self.client_class = patcher.start()
        self.addCleanup(patcher.stop)

        self.client = self.client_class.return_value.__enter__.return_value

        self.client.search_users.return_value = [VALID_USER.copy()]

    def test_exact_email_match(self):
        result = self.service.resolve_requester("editor@example.com")

        self.assertEqual(result, "example-account-id")

        self.client.search_users.assert_called_once_with("editor@example.com")

    def test_case_insensitive_email_match(self):
        result = self.service.resolve_requester("EDITOR@EXAMPLE.COM")

        self.assertEqual(result, "example-account-id")

    def test_email_is_trimmed(self):
        result = self.service.resolve_requester("  editor@example.com  ")

        self.assertEqual(result, "example-account-id")

        self.client.search_users.assert_called_once_with("editor@example.com")

    def test_missing_email(self):
        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("")

        self.client_class.assert_not_called()

    def test_whitespace_only_email(self):
        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("   ")

        self.client_class.assert_not_called()

    def test_none_email(self):
        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester(None)

        self.client_class.assert_not_called()

    def test_no_matching_accounts(self):
        self.client.search_users.return_value = []

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_partial_email_match_is_rejected(self):
        self.client.search_users.return_value = [
            {
                **VALID_USER,
                "emailAddress": "other-editor@example.com",
            }
        ]

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_exact_match_among_multiple_results(self):
        self.client.search_users.return_value = [
            {
                **VALID_USER,
                "accountId": "different-account-id",
                "emailAddress": "other-editor@example.com",
            },
            VALID_USER.copy(),
        ]

        result = self.service.resolve_requester("editor@example.com")

        self.assertEqual(result, "example-account-id")

    def test_multiple_exact_matches_are_rejected(self):
        self.client.search_users.return_value = [
            VALID_USER.copy(),
            {
                **VALID_USER,
                "accountId": "another-account-id",
            },
        ]

        with self.assertRaises(JiraUserAmbiguousError):
            self.service.resolve_requester("editor@example.com")

    def test_inactive_account_is_rejected(self):
        self.client.search_users.return_value = [
            {
                **VALID_USER,
                "active": False,
            }
        ]

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_missing_active_status_is_rejected(self):
        user = VALID_USER.copy()
        user.pop("active")

        self.client.search_users.return_value = [user]

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_hidden_email_is_rejected(self):
        user = VALID_USER.copy()
        user.pop("emailAddress")

        self.client.search_users.return_value = [user]

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_missing_account_id_is_rejected(self):
        user = VALID_USER.copy()
        user.pop("accountId")

        self.client.search_users.return_value = [user]

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_empty_account_id_is_rejected(self):
        self.client.search_users.return_value = [
            {
                **VALID_USER,
                "accountId": "",
            }
        ]

        with self.assertRaises(JiraUserNotFoundError):
            self.service.resolve_requester("editor@example.com")

    def test_customer_account_type_is_supported(self):
        self.client.search_users.return_value = [
            {
                **VALID_USER,
                "accountType": "customer",
            }
        ]

        result = self.service.resolve_requester("editor@example.com")

        self.assertEqual(result, "example-account-id")

    def test_invalid_search_response(self):
        self.client.search_users.return_value = {}

        with self.assertRaises(JiraAPIError):
            self.service.resolve_requester("editor@example.com")

    def test_invalid_user_record(self):
        self.client.search_users.return_value = [None]

        with self.assertRaises(JiraAPIError):
            self.service.resolve_requester("editor@example.com")

    def test_connection_error_is_propagated(self):
        self.client.search_users.side_effect = JiraConnectionError("Connection failed.")

        with self.assertRaises(JiraConnectionError):
            self.service.resolve_requester("editor@example.com")

    def test_requester_lookup_is_not_cached(self):
        self.service.resolve_requester("editor@example.com")
        self.service.resolve_requester("editor@example.com")

        self.assertEqual(
            self.client.search_users.call_count,
            2,
        )

    def test_requester_resolution_does_not_create_ticket(self):
        self.service.resolve_requester("editor@example.com")

        self.client.create_request.assert_not_called()
