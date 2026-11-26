from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from wagtail_jira_support.exceptions import (
    JiraAPIError,
    JiraConfigurationError,
    JiraConnectionError,
    JiraRequestTypeNotFoundError,
    JiraServiceDeskNotFoundError,
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
            "request_types": ["100", "101"],
        },
        {
            "id": "52",
            "request_types": ["200"],
        },
    ],
}


SERVICE_DESKS = [
    {"id": "52", "projectName": "Second Desk"},
    {"id": "99", "projectName": "Unconfigured Desk"},
    {"id": "12", "projectName": "First Desk"},
]


REQUEST_TYPES = [
    {"id": "101", "name": "Request a change"},
    {"id": "999", "name": "Unconfigured request type"},
    {
        "id": "100",
        "name": "Report a problem",
        "description": "Report an application problem.",
        "helpText": "Describe the problem.",
    },
]


REQUEST_TYPE_FIELDS = {
    "canRaiseOnBehalfOf": True,
    "canAddRequestParticipants": True,
    "requestTypeFields": [
        {
            "fieldId": "summary",
            "name": "Summary",
            "required": True,
        },
        {
            "fieldId": "description",
            "name": "Description",
            "required": False,
        },
    ],
}


@override_settings(
    WAGTAIL_JIRA_SUPPORT=VALID_CONFIG,
    CACHES={
        "default": {
            "BACKEND": ("django.core.cache.backends.locmem.LocMemCache"),
            "LOCATION": "wagtail-jira-support-tests",
        },
    },
)
class JiraSupportServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

        self.service = JiraSupportService()

        patcher = patch("wagtail_jira_support.services.JiraClient")

        self.client_class = patcher.start()
        self.addCleanup(patcher.stop)

        self.client = self.client_class.return_value.__enter__.return_value

        self.client.get_service_desks.return_value = SERVICE_DESKS

        self.client.get_request_types.return_value = REQUEST_TYPES

        self.client.get_request_type_fields.return_value = REQUEST_TYPE_FIELDS

    @override_settings(WAGTAIL_JIRA_SUPPORT={})
    def test_disabled_service(self):
        with self.assertRaises(JiraConfigurationError):
            JiraSupportService()

    def test_client_configuration(self):
        self.service.get_service_desks()

        self.client_class.assert_called_once_with(
            base_url="https://example.atlassian.net",
            email="integration@example.com",
            api_token="test-token",
            timeout=10,
        )

    def test_get_service_desk_config(self):
        desk = self.service.get_service_desk_config("12")

        self.assertEqual(desk["id"], "12")
        self.assertEqual(
            desk["request_types"],
            ["100", "101"],
        )

    def test_unconfigured_service_desk(self):
        with self.assertRaises(JiraServiceDeskNotFoundError):
            self.service.get_service_desk_config("99")

    def test_service_desks_are_filtered_and_ordered(self):
        desks = self.service.get_service_desks()

        self.assertEqual(
            [desk["id"] for desk in desks],
            ["12", "52"],
        )

    def test_unavailable_service_desk_is_excluded(self):
        self.client.get_service_desks.return_value = [
            SERVICE_DESKS[0],
        ]

        desks = self.service.get_service_desks()

        self.assertEqual(
            [desk["id"] for desk in desks],
            ["52"],
        )

    def test_service_desks_are_cached(self):
        self.service.get_service_desks()
        self.service.get_service_desks()

        self.client.get_service_desks.assert_called_once()

    def test_empty_service_desk_results_are_cached(self):
        self.client.get_service_desks.return_value = []

        self.assertEqual(
            self.service.get_service_desks(),
            [],
        )

        self.assertEqual(
            self.service.get_service_desks(),
            [],
        )

        self.client.get_service_desks.assert_called_once()

    def test_request_types_are_filtered_and_ordered(self):
        types = self.service.get_request_types("12")

        self.assertEqual(
            [item["id"] for item in types],
            ["100", "101"],
        )

    def test_request_types_are_cached(self):
        self.service.get_request_types("12")
        self.service.get_request_types("12")

        self.client.get_request_types.assert_called_once_with("12")

    def test_request_type_caches_are_separate(self):
        self.service.get_request_types("12")
        self.service.get_request_types("52")

        self.assertEqual(
            self.client.get_request_types.call_count,
            2,
        )

    def test_unconfigured_desk_does_not_call_jira(self):
        with self.assertRaises(JiraServiceDeskNotFoundError):
            self.service.get_request_types("99")

        self.client.get_request_types.assert_not_called()

    def test_get_request_type(self):
        item = self.service.get_request_type(
            "12",
            "100",
        )

        self.assertEqual(item["name"], "Report a problem")
        self.assertEqual(
            item["helpText"],
            "Describe the problem.",
        )

    def test_unconfigured_request_type(self):
        with self.assertRaises(JiraRequestTypeNotFoundError):
            self.service.get_request_type("12", "999")

        self.client.get_request_types.assert_not_called()

    def test_unavailable_request_type(self):
        self.client.get_request_types.return_value = []

        with self.assertRaises(JiraRequestTypeNotFoundError):
            self.service.get_request_type("12", "100")

    def test_get_request_type_fields(self):
        fields = self.service.get_request_type_fields(
            "12",
            "100",
        )

        self.assertEqual(fields, REQUEST_TYPE_FIELDS)

        self.client.get_request_type_fields.assert_called_once_with(
            "12",
            "100",
        )

    def test_request_type_fields_are_cached(self):
        self.service.get_request_type_fields("12", "100")
        self.service.get_request_type_fields("12", "100")

        self.client.get_request_type_fields.assert_called_once()

    def test_request_type_field_caches_are_separate(self):
        self.service.get_request_type_fields("12", "100")
        self.service.get_request_type_fields("12", "101")

        self.assertEqual(
            self.client.get_request_type_fields.call_count,
            2,
        )

    def test_unconfigured_request_type_fields(self):
        with self.assertRaises(JiraRequestTypeNotFoundError):
            self.service.get_request_type_fields(
                "12",
                "999",
            )

        self.client.get_request_type_fields.assert_not_called()

    def test_invalid_field_response(self):
        self.client.get_request_type_fields.return_value = {}

        with self.assertRaises(JiraAPIError):
            self.service.get_request_type_fields(
                "12",
                "100",
            )

    def test_api_errors_are_not_cached(self):
        self.client.get_service_desks.side_effect = [
            JiraConnectionError("Connection failed."),
            SERVICE_DESKS,
        ]

        with self.assertRaises(JiraConnectionError):
            self.service.get_service_desks()

        desks = self.service.get_service_desks()

        self.assertEqual(len(desks), 2)
        self.assertEqual(
            self.client.get_service_desks.call_count,
            2,
        )

    def test_allowlist_changes_apply_to_cached_metadata(self):
        self.service.get_request_types("12")

        self.service.config["SERVICE_DESKS"][0]["request_types"] = ["101"]

        types = self.service.get_request_types("12")

        self.assertEqual(
            [item["id"] for item in types],
            ["101"],
        )

        self.client.get_request_types.assert_called_once()

    def test_cache_key_is_scoped_to_credentials(self):
        original = self.service._cache_key("service_desks")

        self.service.config["API_TOKEN"] = "different-token"

        changed = self.service._cache_key("service_desks")

        self.assertNotEqual(original, changed)
        self.assertNotIn("different-token", changed)
        self.assertNotIn("test-token", original)
