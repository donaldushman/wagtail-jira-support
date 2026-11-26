from django.test import SimpleTestCase, override_settings

from wagtail_jira_support.conf import (
    get_settings,
    is_enabled,
    validate_settings,
)
from wagtail_jira_support.exceptions import JiraConfigurationError

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
            "default_fields": {
                "customfield_10000": {
                    "id": "20000",
                },
            },
        },
    ],
}


class ConfigurationTests(SimpleTestCase):
    @override_settings(WAGTAIL_JIRA_SUPPORT={})
    def test_disabled_by_default(self):
        self.assertFalse(is_enabled())

    @override_settings(WAGTAIL_JIRA_SUPPORT={})
    def test_default_settings(self):
        config = get_settings()

        self.assertEqual(config["TIMEOUT"], 10)
        self.assertEqual(config["CACHE_TIMEOUT"], 3600)
        self.assertEqual(config["MENU_LABEL"], "Request support")

    @override_settings(WAGTAIL_JIRA_SUPPORT={"TIMEOUT": 20})
    def test_settings_override_defaults(self):
        self.assertEqual(get_settings()["TIMEOUT"], 20)

    @override_settings(WAGTAIL_JIRA_SUPPORT={})
    def test_disabled_configuration_does_not_require_credentials(self):
        validate_settings()

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_valid_configuration(self):
        self.assertTrue(is_enabled())
        validate_settings()

    @override_settings(WAGTAIL_JIRA_SUPPORT={"ENABLED": True})
    def test_missing_required_settings(self):
        with self.assertRaises(JiraConfigurationError):
            validate_settings()

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_invalid_base_url(self):
        config = get_settings()
        config["BASE_URL"] = "http://example.atlassian.net"

        with self.assertRaises(JiraConfigurationError):
            validate_settings(config)

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_invalid_timeout(self):
        config = get_settings()
        config["TIMEOUT"] = 0

        with self.assertRaises(JiraConfigurationError):
            validate_settings(config)

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_invalid_service_desk(self):
        config = get_settings()
        config["SERVICE_DESKS"] = [{}]

        with self.assertRaises(JiraConfigurationError):
            validate_settings(config)

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_missing_request_types(self):
        config = get_settings()
        config["SERVICE_DESKS"][0]["request_types"] = []

        with self.assertRaises(JiraConfigurationError):
            validate_settings(config)

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_duplicate_service_desks(self):
        config = get_settings()
        config["SERVICE_DESKS"].append(config["SERVICE_DESKS"][0].copy())

        with self.assertRaises(JiraConfigurationError):
            validate_settings(config)

    @override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
    def test_configuration_is_independent(self):
        config = get_settings()
        config["SERVICE_DESKS"][0]["request_types"].append("999")

        fresh_config = get_settings()

        self.assertNotIn(
            "999",
            fresh_config["SERVICE_DESKS"][0]["request_types"],
        )

    @override_settings(WAGTAIL_JIRA_SUPPORT="invalid")
    def test_invalid_settings_type(self):
        with self.assertRaises(JiraConfigurationError):
            get_settings()
