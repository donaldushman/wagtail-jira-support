from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from wagtail_jira_support.exceptions import (
    JiraConnectionError,
    JiraPermissionError,
    JiraRequestTypeNotFoundError,
    JiraRequestValidationError,
    JiraServiceDeskNotFoundError,
    JiraSubmissionUncertainError,
    JiraUserAmbiguousError,
    JiraUserNotFoundError,
)

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
            "billing_code_field": "customfield_10093",
        },
    ],
}


SERVICE_DESK = {
    "id": "12",
    "projectName": "Website Development",
}


REQUEST_TYPE = {
    "id": "100",
    "name": "Report a website problem",
    "description": "Report a problem with the website.",
    "helpText": "Include steps to reproduce the problem.",
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
            "fieldId": "customfield_10093",
            "name": "Billing Code",
            "required": False,
        },
    ],
}


VALID_FORM_DATA = {
    "summary": "Example problem",
    "description": "Something is not working.",
    "billing_code": "ABC-123",
}


@override_settings(WAGTAIL_JIRA_SUPPORT=VALID_CONFIG)
class SupportRequestViewTests(TestCase):
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
        self.url = reverse(
            "wagtail_jira_support:request",
            args=[12, 100],
        )

        patcher = patch("wagtail_jira_support.views.JiraSupportService")

        self.service_class = patcher.start()
        self.addCleanup(patcher.stop)

        self.service = self.service_class.return_value

        self.service.get_service_desk_config.return_value = VALID_CONFIG[
            "SERVICE_DESKS"
        ][0].copy()

        self.service.get_service_desks.return_value = [
            SERVICE_DESK,
        ]

        self.service.get_request_type.return_value = REQUEST_TYPE

        self.service.get_request_type_fields.return_value = REQUEST_TYPE_FIELDS

        self.client.force_login(self.authorized_user)

    def test_url_registration(self):
        self.assertEqual(
            self.url,
            "/admin/jira-support/12/100/",
        )

    def test_authorized_user_can_access_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "wagtail_jira_support/request.html",
        )

    def test_anonymous_user_cannot_access_form(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.service_class.assert_not_called()

    def test_unauthorized_user_cannot_access_form(self):
        self.client.force_login(self.unauthorized_user)

        response = self.client.get(self.url)

        self.assertIn(response.status_code, (302, 403))
        self.service_class.assert_not_called()

    def test_unauthorized_user_cannot_submit_form(self):
        self.client.force_login(self.unauthorized_user)

        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertIn(response.status_code, (302, 403))
        self.service_class.assert_not_called()

    @override_settings(WAGTAIL_JIRA_SUPPORT={"ENABLED": False})
    def test_disabled_support_returns_404(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.service_class.assert_not_called()

    def test_request_type_name_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(
            response,
            "Report a website problem",
        )

    def test_service_desk_name_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Website Development")

    def test_request_description_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(
            response,
            "Report a problem with the website.",
        )

    def test_jira_help_text_is_not_displayed(self):
        response = self.client.get(self.url)

        self.assertNotContains(
            response,
            "Include steps to reproduce the problem.",
        )

    def test_application_context_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Example Website")
        self.assertContains(response, "development")

    def test_billing_code_is_displayed(self):
        response = self.client.get(self.url)

        self.assertIn(
            "billing_code",
            response.context["form"].fields,
        )

    def test_billing_code_is_hidden_when_not_configured(self):
        self.service.get_service_desk_config.return_value = {
            "id": "12",
            "request_types": ["100"],
        }

        response = self.client.get(self.url)

        self.assertNotIn(
            "billing_code",
            response.context["form"].fields,
        )

    def test_billing_code_is_hidden_when_unavailable(self):
        self.service.get_request_type_fields.return_value = {
            "requestTypeFields": [
                {"fieldId": "summary"},
                {"fieldId": "description"},
            ],
        }

        response = self.client.get(self.url)

        self.assertNotIn(
            "billing_code",
            response.context["form"].fields,
        )

    def test_unconfigured_service_desk_returns_404(self):
        self.service.get_service_desk_config.side_effect = JiraServiceDeskNotFoundError(
            "Not configured."
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_unconfigured_request_type_returns_404(self):
        self.service.get_request_type.side_effect = JiraRequestTypeNotFoundError(
            "Not configured."
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_unavailable_service_desk_returns_404(self):
        self.service.get_service_desks.return_value = []

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_invalid_form_displays_errors(self):
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, 200)

        form = response.context["form"]

        self.assertIn("summary", form.errors)
        self.assertIn("description", form.errors)

        self.service.prepare_request.assert_not_called()

    def test_valid_form_prepares_request(self):
        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertEqual(response.status_code, 200)

        self.service.prepare_request.assert_called_once_with(
            service_desk_id="12",
            request_type_id="100",
            summary="Example problem",
            description="Something is not working.",
            billing_code="ABC-123",
        )

        self.assertTrue(response.context["prepared"])

    def test_validation_confirmation_is_displayed(self):
        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertContains(
            response,
            "Request validated successfully",
        )

        self.assertContains(
            response,
            "No Jira ticket has been created.",
        )

    def test_unexpected_post_fields_are_ignored(self):
        data = {
            **VALID_FORM_DATA,
            "serviceDeskId": "999",
            "requestTypeId": "999",
            "raiseOnBehalfOf": "another-user",
        }

        self.client.post(self.url, data)

        self.service.prepare_request.assert_called_once_with(
            service_desk_id="12",
            request_type_id="100",
            summary="Example problem",
            description="Something is not working.",
            billing_code="ABC-123",
        )

    def test_request_validation_failure(self):
        self.service.prepare_request.side_effect = JiraRequestValidationError(
            "Missing required Jira fields."
        )

        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertContains(
            response,
            "Missing required Jira fields.",
        )

        self.assertFalse(response.context["prepared"])

    def test_jira_connection_failure(self):
        self.service.get_request_type.side_effect = JiraConnectionError(
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

    def test_unsupported_http_method(self):
        response = self.client.put(self.url)

        self.assertEqual(response.status_code, 405)
        self.service_class.assert_not_called()

    def test_get_does_not_prepare_request(self):
        self.client.get(self.url)

        self.service.prepare_request.assert_not_called()

    def test_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.authorized_user)

        response = csrf_client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertEqual(response.status_code, 403)
        self.service.prepare_request.assert_not_called()


@override_settings(
    WAGTAIL_JIRA_SUPPORT={
        **VALID_CONFIG,
        "SUBMISSION_ENABLED": True,
    }
)
class SupportSubmissionViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.user = user_model.objects.create_user(
            username="editor",
            email="editor@example.com",
            first_name="Example",
            last_name="Editor",
            password="test-password",
        )

        permission = Permission.objects.get(
            content_type__app_label="wagtailadmin",
            codename="access_admin",
        )

        cls.user.user_permissions.add(permission)

    def setUp(self):
        self.url = reverse(
            "wagtail_jira_support:request",
            args=[12, 100],
        )

        self.confirmation_url = reverse("wagtail_jira_support:confirmation")

        patcher = patch("wagtail_jira_support.views.JiraSupportService")

        self.service_class = patcher.start()
        self.addCleanup(patcher.stop)

        self.service = self.service_class.return_value

        self.service.get_service_desk_config.return_value = VALID_CONFIG[
            "SERVICE_DESKS"
        ][0].copy()

        self.service.get_service_desks.return_value = [
            SERVICE_DESK,
        ]

        self.service.get_request_type.return_value = REQUEST_TYPE

        self.service.get_request_type_fields.return_value = REQUEST_TYPE_FIELDS

        self.service.submit_request.return_value = {
            "issue_key": "WD-123",
            "issue_id": "12345",
            "portal_url": (
                "https://example.atlassian.net/servicedesk/customer/portal/12/WD-123"
            ),
        }

        self.client.force_login(self.user)

    def test_submission_button_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(
            response,
            "Submit support request",
        )

        self.assertNotContains(
            response,
            "Validate support request",
        )

    def test_requester_name_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Example Editor")

    def test_requester_email_is_displayed(self):
        response = self.client.get(self.url)

        self.assertContains(
            response,
            "editor@example.com",
        )

    def test_get_does_not_submit_request(self):
        self.client.get(self.url)

        self.service.submit_request.assert_not_called()

    def test_invalid_form_does_not_submit_request(self):
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, 200)
        self.service.submit_request.assert_not_called()

    def test_valid_form_submits_request(self):
        self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.service.submit_request.assert_called_once_with(
            service_desk_id="12",
            request_type_id="100",
            requester_email="editor@example.com",
            summary="Example problem",
            description="Something is not working.",
            billing_code="ABC-123",
        )

    def test_requester_cannot_be_overridden(self):
        data = {
            **VALID_FORM_DATA,
            "requester_email": "another@example.com",
            "raiseOnBehalfOf": "another-account",
        }

        self.client.post(self.url, data)

        kwargs = self.service.submit_request.call_args.kwargs

        self.assertEqual(
            kwargs["requester_email"],
            "editor@example.com",
        )

    def test_successful_submission_redirects(self):
        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertRedirects(
            response,
            self.confirmation_url,
        )

    def test_successful_submission_stores_confirmation(self):
        self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        result = self.client.session["wagtail_jira_support_confirmation"]

        self.assertEqual(result["issue_key"], "WD-123")
        self.assertEqual(result["user_id"], str(self.user.pk))

        self.assertEqual(
            result["service_desk"],
            SERVICE_DESK["projectName"],
        )

        self.assertEqual(
            result["request_type"],
            REQUEST_TYPE["name"],
        )

        self.assertEqual(
            result["application_name"],
            VALID_CONFIG["APPLICATION_NAME"],
        )

    def test_confirmation_displays_ticket_number(self):
        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
            follow=True,
        )

        self.assertContains(
            response,
            "Support request submitted",
        )

        self.assertContains(response, "WD-123")

    def test_confirmation_displays_portal_link(self):
        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
            follow=True,
        )

        self.assertContains(
            response,
            self.service.submit_request.return_value["portal_url"],
        )

        self.assertContains(
            response,
            "View request in Jira",
        )

    def test_confirmation_without_portal_link(self):
        self.service.submit_request.return_value["portal_url"] = ""

        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
            follow=True,
        )

        self.assertContains(response, "WD-123")

        self.assertNotContains(
            response,
            "View request in Jira",
        )

    def test_refresh_does_not_create_duplicate_request(self):
        self.client.post(
            self.url,
            VALID_FORM_DATA,
            follow=True,
        )

        for _ in range(3):
            response = self.client.get(self.confirmation_url)

            self.assertContains(response, "WD-123")

        self.service.submit_request.assert_called_once()

    def test_requester_not_found(self):
        self.service.submit_request.side_effect = JiraUserNotFoundError(
            "Account not found."
        )

        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertContains(
            response,
            "We could not identify your Jira account.",
        )

    def test_ambiguous_requester(self):
        self.service.submit_request.side_effect = JiraUserAmbiguousError(
            "Ambiguous account."
        )

        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertContains(
            response,
            "We could not uniquely identify your Jira",
        )

    def test_request_validation_error(self):
        self.service.submit_request.side_effect = JiraRequestValidationError(
            "Missing required Jira fields."
        )

        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertContains(
            response,
            "Missing required Jira fields.",
        )

    def test_permission_error(self):
        self.service.submit_request.side_effect = JiraPermissionError(
            "Permission denied."
        )

        with self.assertLogs(
            "wagtail_jira_support.views",
            level="WARNING",
        ):
            response = self.client.post(
                self.url,
                VALID_FORM_DATA,
            )

        self.assertContains(
            response,
            "Unable to submit your support request.",
        )

    def test_failed_submission_preserves_form_data(self):
        self.service.submit_request.side_effect = JiraConnectionError(
            "Connection failed."
        )

        with self.assertLogs(
            "wagtail_jira_support.views",
            level="WARNING",
        ):
            response = self.client.post(
                self.url,
                VALID_FORM_DATA,
            )

        form = response.context["form"]

        self.assertTrue(form.is_bound)

        for field, value in VALID_FORM_DATA.items():
            self.assertEqual(form[field].value(), value)

    def test_uncertain_submission_displays_warning(self):
        self.service.submit_request.side_effect = JiraSubmissionUncertainError(
            "Unable to confirm submission."
        )

        with self.assertLogs(
            "wagtail_jira_support.views",
            level="WARNING",
        ):
            response = self.client.post(
                self.url,
                VALID_FORM_DATA,
            )

        self.assertContains(
            response,
            "Your request may have been created",
        )

        self.assertTrue(response.context["submission_uncertain"])

    def test_uncertain_submission_hides_submit_button(self):
        self.service.submit_request.side_effect = JiraSubmissionUncertainError(
            "Unable to confirm submission."
        )

        with self.assertLogs(
            "wagtail_jira_support.views",
            level="WARNING",
        ):
            response = self.client.post(
                self.url,
                VALID_FORM_DATA,
            )

        self.assertNotContains(
            response,
            'type="submit"',
        )

    def test_failed_submission_does_not_store_confirmation(self):
        self.service.submit_request.side_effect = JiraUserNotFoundError(
            "Account not found."
        )

        self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertNotIn(
            "wagtail_jira_support_confirmation",
            self.client.session,
        )

    @override_settings(
        WAGTAIL_JIRA_SUPPORT={
            **VALID_CONFIG,
            "SUBMISSION_ENABLED": False,
        }
    )
    def test_validation_mode_does_not_submit_request(self):
        response = self.client.post(
            self.url,
            VALID_FORM_DATA,
        )

        self.assertTrue(response.context["prepared"])

        self.service.prepare_request.assert_called_once()
        self.service.submit_request.assert_not_called()
