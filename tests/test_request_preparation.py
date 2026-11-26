from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from wagtail_jira_support.exceptions import (
    JiraConfigurationError,
    JiraRequestTypeNotFoundError,
    JiraRequestValidationError,
    JiraServiceDeskNotFoundError,
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
            "request_types": ["100", "101"],
            "default_fields": {
                "customfield_10000": {"id": "20000"},
            },
            "url_field": "customfield_10001",
            "billing_code_field": "customfield_10002",
        },
    ],
}


REQUEST_TYPE_FIELDS = {
    "canRaiseOnBehalfOf": True,
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
        {
            "fieldId": "customfield_10000",
            "name": "Application",
            "required": True,
        },
        {
            "fieldId": "customfield_10001",
            "name": "URL",
            "required": False,
        },
        {
            "fieldId": "customfield_10002",
            "name": "Billing Code",
            "required": False,
        },
    ],
}


@override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
class RequestPreparationTests(SimpleTestCase):
    def setUp(self):
        self.service = JiraSupportService()

        self.metadata = deepcopy(REQUEST_TYPE_FIELDS)

        patcher = patch.object(
            self.service,
            "get_request_type_fields",
            return_value=self.metadata,
        )

        self.get_fields = patcher.start()
        self.addCleanup(patcher.stop)

    def prepare(self, **overrides):
        kwargs = {
            "service_desk_id": "12",
            "request_type_id": "100",
            "summary": "Example problem",
            "description": "Something is not working.",
        }

        kwargs.update(overrides)

        return self.service.prepare_request(**kwargs)

    def remove_field(self, field_id):
        self.metadata["requestTypeFields"] = [
            field
            for field in self.metadata["requestTypeFields"]
            if field["fieldId"] != field_id
        ]

    def test_prepare_request(self):
        result = self.prepare()

        self.assertEqual(result["serviceDeskId"], "12")
        self.assertEqual(result["requestTypeId"], "100")

        fields = result["requestFieldValues"]

        self.assertEqual(fields["summary"], "Example problem")

        self.assertIn(
            "Something is not working.",
            fields["description"],
        )

    def test_default_fields_are_populated(self):
        fields = self.prepare()["requestFieldValues"]

        self.assertEqual(
            fields["customfield_10000"],
            {"id": "20000"},
        )

    def test_default_fields_are_copied(self):
        fields = self.prepare()["requestFieldValues"]

        fields["customfield_10000"]["id"] = "changed"

        config = self.service.get_service_desk_config("12")

        self.assertEqual(
            config["default_fields"]["customfield_10000"]["id"],
            "20000",
        )

    def test_application_context_is_included(self):
        fields = self.prepare()["requestFieldValues"]

        self.assertIn(
            "Application: Example Website",
            fields["description"],
        )

        self.assertIn(
            "Environment: development",
            fields["description"],
        )

    def test_source_url_is_populated(self):
        fields = self.prepare(
            source_url="https://example.com/events/",
        )["requestFieldValues"]

        self.assertEqual(
            fields["customfield_10001"],
            "https://example.com/events/",
        )

        self.assertIn(
            "Source URL: https://example.com/events/",
            fields["description"],
        )

    def test_source_url_is_sanitized(self):
        fields = self.prepare(
            source_url="https://example.com/?token=secret#section",
        )["requestFieldValues"]

        self.assertEqual(
            fields["customfield_10001"],
            "https://example.com/",
        )

        self.assertNotIn(
            "token=secret",
            fields["description"],
        )

    def test_invalid_source_url_is_omitted(self):
        fields = self.prepare(
            source_url="javascript:alert(1)",
        )["requestFieldValues"]

        self.assertNotIn("customfield_10001", fields)
        self.assertNotIn("Source URL:", fields["description"])

    def test_unavailable_url_field_is_omitted(self):
        self.remove_field("customfield_10001")

        fields = self.prepare(
            source_url="https://example.com/",
        )["requestFieldValues"]

        self.assertNotIn("customfield_10001", fields)

        self.assertIn(
            "Source URL: https://example.com/",
            fields["description"],
        )

    def test_billing_code_is_populated(self):
        fields = self.prepare(
            billing_code="  ABC-123  ",
        )["requestFieldValues"]

        self.assertEqual(
            fields["customfield_10002"],
            "ABC-123",
        )

    def test_empty_billing_code_is_omitted(self):
        fields = self.prepare(
            billing_code="   ",
        )["requestFieldValues"]

        self.assertNotIn("customfield_10002", fields)

    def test_unavailable_billing_code_field_is_omitted(self):
        self.remove_field("customfield_10002")

        fields = self.prepare(
            billing_code="ABC-123",
        )["requestFieldValues"]

        self.assertNotIn("customfield_10002", fields)

    def test_missing_summary(self):
        with self.assertRaises(JiraRequestValidationError):
            self.prepare(summary="   ")

    def test_missing_description(self):
        with self.assertRaises(JiraRequestValidationError):
            self.prepare(description="   ")

    def test_summary_is_trimmed(self):
        fields = self.prepare(
            summary="  Example problem  ",
        )["requestFieldValues"]

        self.assertEqual(fields["summary"], "Example problem")

    def test_summary_maximum_length(self):
        fields = self.prepare(
            summary="x" * 255,
        )["requestFieldValues"]

        self.assertEqual(len(fields["summary"]), 255)

    def test_summary_exceeds_maximum_length(self):
        with self.assertRaises(JiraRequestValidationError):
            self.prepare(summary="x" * 256)

    def test_unconfigured_service_desk(self):
        with self.assertRaises(JiraServiceDeskNotFoundError):
            self.prepare(service_desk_id="99")

    def test_unconfigured_request_type(self):
        self.get_fields.side_effect = JiraRequestTypeNotFoundError(
            "Request type is not configured."
        )

        with self.assertRaises(JiraRequestTypeNotFoundError):
            self.prepare(request_type_id="999")

    def test_unavailable_default_field(self):
        self.remove_field("customfield_10000")

        with self.assertRaises(JiraConfigurationError):
            self.prepare()

    def test_missing_required_field(self):
        self.metadata["requestTypeFields"].append(
            {
                "fieldId": "customfield_99999",
                "name": "Additional Required Field",
                "required": True,
            }
        )

        with self.assertRaisesMessage(
            JiraRequestValidationError,
            "Missing required Jira fields: Additional Required Field",
        ):
            self.prepare()

    def test_missing_required_default_value(self):
        desk = self.service.get_service_desk_config("12")

        desk["default_fields"]["customfield_10000"] = {}

        with self.assertRaisesMessage(
            JiraRequestValidationError,
            "Missing required Jira fields: Application",
        ):
            self.prepare()

    def test_unsupported_description_field(self):
        self.remove_field("description")

        with self.assertRaises(JiraRequestValidationError):
            self.prepare()

    def test_prepare_request_does_not_submit_ticket(self):
        with patch.object(self.service, "_get_client") as client:
            self.prepare()

            client.assert_not_called()
