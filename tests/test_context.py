from django.test import SimpleTestCase

from wagtail_jira_support.context import (
    build_description,
    sanitize_source_url,
)


class SanitizeSourceURLTests(SimpleTestCase):
    def test_valid_https_url(self):
        self.assertEqual(
            sanitize_source_url("https://example.com/events/"),
            "https://example.com/events/",
        )

    def test_valid_http_url(self):
        self.assertEqual(
            sanitize_source_url("http://localhost:8000/events/"),
            "http://localhost:8000/events/",
        )

    def test_query_string_is_removed(self):
        self.assertEqual(
            sanitize_source_url("https://example.com/events/?token=secret"),
            "https://example.com/events/",
        )

    def test_fragment_is_removed(self):
        self.assertEqual(
            sanitize_source_url("https://example.com/events/#registration"),
            "https://example.com/events/",
        )

    def test_missing_path(self):
        self.assertEqual(
            sanitize_source_url("https://example.com"),
            "https://example.com/",
        )

    def test_relative_url_is_rejected(self):
        self.assertEqual(
            sanitize_source_url("/events/"),
            "",
        )

    def test_unsupported_scheme_is_rejected(self):
        self.assertEqual(
            sanitize_source_url("javascript:alert(1)"),
            "",
        )

    def test_embedded_credentials_are_rejected(self):
        self.assertEqual(
            sanitize_source_url("https://user:password@example.com/"),
            "",
        )

    def test_missing_hostname(self):
        self.assertEqual(
            sanitize_source_url("https:///events/"),
            "",
        )

    def test_invalid_port(self):
        self.assertEqual(
            sanitize_source_url("https://example.com:invalid/"),
            "",
        )

    def test_empty_url(self):
        self.assertEqual(sanitize_source_url(""), "")

    def test_none_url(self):
        self.assertEqual(sanitize_source_url(None), "")

    def test_malformed_url(self):
        self.assertEqual(
            sanitize_source_url("https://[invalid/"),
            "",
        )


class BuildDescriptionTests(SimpleTestCase):
    def test_description_with_application_context(self):
        result = build_description(
            description="Example problem.",
            application_name="Example Website",
            environment="production",
            source_url="https://example.com/events/",
        )

        self.assertEqual(
            result,
            (
                "Example problem.\n"
                "\n"
                "---\n"
                "Application context\n"
                "\n"
                "Application: Example Website\n"
                "Environment: production\n"
                "Source URL: https://example.com/events/"
            ),
        )

    def test_optional_context_is_omitted(self):
        result = build_description(
            description="Example problem.",
            application_name="Example Website",
        )

        self.assertIn(
            "Application: Example Website",
            result,
        )

        self.assertNotIn("Environment:", result)
        self.assertNotIn("Source URL:", result)

    def test_description_is_trimmed(self):
        result = build_description(
            description="  Example problem.  ",
            application_name="Example Website",
        )

        self.assertTrue(result.startswith("Example problem.\n"))

    def test_source_url_is_sanitized(self):
        result = build_description(
            description="Example problem.",
            application_name="Example Website",
            source_url="https://example.com/?token=secret",
        )

        self.assertIn(
            "Source URL: https://example.com/",
            result,
        )

        self.assertNotIn("token=secret", result)
