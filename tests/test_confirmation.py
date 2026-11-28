from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

VALID_CONFIG = {
    "ENABLED": True,
    "SUBMISSION_ENABLED": True,
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


@override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
class ConfirmationViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.user = user_model.objects.create_user(
            username="editor",
            email="editor@example.com",
            password="test-password",
        )

        cls.other_user = user_model.objects.create_user(
            username="other-editor",
            email="other@example.com",
            password="test-password",
        )

        cls.unauthorized_user = user_model.objects.create_user(
            username="regular-user",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        )

        cls.user.user_permissions.add(permission)
        cls.other_user.user_permissions.add(permission)

    def setUp(self):
        self.url = reverse("wagtail_jira_support:confirmation")

        self.index_url = reverse("wagtail_jira_support:index")

        self.client.force_login(self.user)

    def store_confirmation(self, **overrides):
        result = {
            "user_id": str(self.user.pk),
            "issue_key": "WD-123",
            "portal_url": (
                "https://example.atlassian.net/servicedesk/customer/portal/12/WD-123"
            ),
            "service_desk": "Website Development",
            "request_type": "Report a website problem",
            "application_name": "Example Website",
        }

        result.update(overrides)

        session = self.client.session

        session["wagtail_jira_support_confirmation"] = result

        session.save()

    def test_confirmation_url(self):
        self.assertEqual(
            self.url,
            "/admin/jira-support/confirmation/",
        )

    def test_confirmation_without_session_redirects(self):
        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            self.index_url,
            fetch_redirect_response=False,
        )

    def test_confirmation_uses_correct_template(self):
        self.store_confirmation()

        response = self.client.get(self.url)

        self.assertTemplateUsed(
            response,
            "wagtail_jira_support/confirmation.html",
        )

    def test_confirmation_displays_request_details(self):
        self.store_confirmation()

        response = self.client.get(self.url)

        for value in (
            "WD-123",
            "Website Development",
            "Report a website problem",
            "Example Website",
        ):
            self.assertContains(response, value)

    def test_confirmation_displays_return_link(self):
        self.store_confirmation()

        response = self.client.get(self.url)

        self.assertContains(
            response,
            f'href="{self.index_url}"',
        )

    def test_confirmation_belonging_to_another_user(self):
        self.store_confirmation(user_id=str(self.other_user.pk))

        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            self.index_url,
            fetch_redirect_response=False,
        )

    def test_invalid_confirmation_session_data(self):
        session = self.client.session

        session["wagtail_jira_support_confirmation"] = "invalid"

        session.save()

        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            self.index_url,
            fetch_redirect_response=False,
        )

    def test_anonymous_user_cannot_access_confirmation(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)

    def test_unauthorized_user_cannot_access_confirmation(self):
        self.client.force_login(self.unauthorized_user)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (302, 403))

    @override_settings(WAGTAIL_JIRA_SUPPORT={"ENABLED": False})
    def test_disabled_support_returns_404(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_confirmation_rejects_post(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 405)

    def test_confirmation_persists_after_refresh(self):
        self.store_confirmation()

        for _ in range(3):
            response = self.client.get(self.url)

            self.assertContains(response, "WD-123")
