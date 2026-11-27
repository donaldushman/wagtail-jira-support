from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from wagtail_jira_support.exceptions import JiraConnectionError

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
        },
        {
            "id": "52",
            "request_types": ["200"],
        },
    ],
}


SERVICE_DESKS = [
    {
        "id": "12",
        "projectName": "Website Development",
    },
    {
        "id": "52",
        "projectName": "Salesforce Service Desk",
    },
]


REQUEST_TYPES = {
    "12": [
        {
            "id": "100",
            "name": "Report a website problem",
            "description": "Report a problem with the website.",
        },
    ],
    "52": [
        {
            "id": "200",
            "name": "Report an application problem",
            "description": "Report a Salesforce application problem.",
        },
    ],
}


@override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
class SupportIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.authorized_user = user_model.objects.create_user(
            username="editor",
            email="editor@example.com",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        )

        cls.authorized_user.user_permissions.add(permission)

        cls.unauthorized_user = user_model.objects.create_user(
            username="regular-user",
            email="user@example.com",
            password="test-password",
        )

    def setUp(self):
        self.url = reverse("wagtail_jira_support:index")

        patcher = patch("wagtail_jira_support.views.JiraSupportService")

        self.service_class = patcher.start()
        self.addCleanup(patcher.stop)

        self.service = self.service_class.return_value

        self.service.get_service_desks.return_value = SERVICE_DESKS

        self.service.get_request_types.side_effect = lambda desk_id: REQUEST_TYPES[
            desk_id
        ]

    def test_url_registration(self):
        self.assertEqual(
            self.url,
            "/admin/jira-support/",
        )

    def test_authorized_user_can_access_page(self):
        self.client.force_login(self.authorized_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "wagtail_jira_support/index.html",
        )

    def test_anonymous_user_cannot_access_page(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

        self.service_class.assert_not_called()

    def test_unauthorized_user_cannot_access_page(self):
        self.client.force_login(self.unauthorized_user)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (302, 403))

        self.service_class.assert_not_called()

    @override_settings(WAGTAIL_JIRA_SUPPORT={"ENABLED": False})
    def test_disabled_support_returns_404(self):
        self.client.force_login(self.authorized_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

        self.service_class.assert_not_called()

    def test_application_name_is_displayed(self):
        self.client.force_login(self.authorized_user)

        response = self.client.get(self.url)

        self.assertContains(response, "Example Website")

    def test_service_desks_are_displayed(self):
        self.client.force_login(self.authorized_user)

        response = self.client.get(self.url)

        self.assertContains(response, "Website Development")
        self.assertContains(response, "Salesforce Service Desk")

    def test_request_types_are_displayed(self):
        self.client.force_login(self.authorized_user)

        response = self.client.get(self.url)

        self.assertContains(response, "Report a website problem")
        self.assertContains(response, "Report an application problem")

    def test_request_descriptions_are_displayed(self):
        self.client.force_login(self.authorized_user)

        response = self.client.get(self.url)

        self.assertContains(
            response,
            "Report a problem with the website.",
        )

        self.assertContains(
            response,
            "Report a Salesforce application problem.",
        )

    def test_no_service_desks_available(self):
        self.client.force_login(self.authorized_user)

        self.service.get_service_desks.return_value = []

        response = self.client.get(self.url)

        self.assertContains(
            response,
            "No support options are currently available.",
        )

    def test_no_request_types_available(self):
        self.client.force_login(self.authorized_user)

        self.service.get_request_types.side_effect = None
        self.service.get_request_types.return_value = []

        response = self.client.get(self.url)

        self.assertContains(
            response,
            "No request types are currently available.",
        )

    def test_jira_connection_failure(self):
        self.client.force_login(self.authorized_user)

        self.service.get_service_desks.side_effect = JiraConnectionError(
            "Connection failed."
        )

        with self.assertLogs(
            "wagtail_jira_support.views",
            level="WARNING",
        ):
            response = self.client.get(self.url)

        self.assertContains(
            response,
            "Support options are temporarily unavailable.",
        )

    def test_post_is_not_allowed(self):
        self.client.force_login(self.authorized_user)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 405)

        self.service_class.assert_not_called()
