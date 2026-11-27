from unittest.mock import Mock

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from wagtail_jira_support.views import index
from wagtail_jira_support.wagtail_hooks import (
    register_jira_support_menu_item,
)


@override_settings(WAGTAIL_JIRA_SUPPORT={"ENABLED": True})
class SupportMenuTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/admin/")
        self.request.user = Mock()
        self.request.user.is_authenticated = True
        self.request.user.is_active = True
        self.request.user.has_perm.return_value = True

        self.menu_item = register_jira_support_menu_item()

    def test_menu_label(self):
        self.assertEqual(
            self.menu_item.label,
            "Request support",
        )

    def test_menu_url(self):
        self.assertEqual(
            self.menu_item.url,
            reverse("wagtail_jira_support:index"),
        )

    def test_menu_order(self):
        self.assertEqual(self.menu_item.order, 10000)

    def test_menu_visible_to_authorized_user(self):
        self.assertTrue(self.menu_item.is_shown(self.request))

        self.request.user.has_perm.assert_called_once_with("wagtailadmin.access_admin")

    def test_menu_hidden_from_anonymous_user(self):
        self.request.user.is_authenticated = False

        self.assertFalse(self.menu_item.is_shown(self.request))

    def test_menu_hidden_from_inactive_user(self):
        self.request.user.is_active = False

        self.assertFalse(self.menu_item.is_shown(self.request))

    def test_menu_hidden_from_unauthorized_user(self):
        self.request.user.has_perm.return_value = False

        self.assertFalse(self.menu_item.is_shown(self.request))

    @override_settings(WAGTAIL_JIRA_SUPPORT={"ENABLED": False})
    def test_menu_hidden_when_disabled(self):
        self.assertFalse(self.menu_item.is_shown(self.request))

    @override_settings(
        WAGTAIL_JIRA_SUPPORT={
            "ENABLED": True,
            "MENU_LABEL": "Technical support",
            "MENU_ORDER": 500,
        }
    )
    def test_custom_menu_configuration(self):
        menu_item = register_jira_support_menu_item()

        self.assertEqual(menu_item.label, "Technical support")
        self.assertEqual(menu_item.order, 500)

    def test_view_rejects_anonymous_user(self):
        self.request.user.is_authenticated = False

        with self.assertRaises(PermissionDenied):
            index(self.request)

    def test_view_rejects_inactive_user(self):
        self.request.user.is_active = False

        with self.assertRaises(PermissionDenied):
            index(self.request)

    def test_view_rejects_unauthorized_user(self):
        self.request.user.has_perm.return_value = False

        with self.assertRaises(PermissionDenied):
            index(self.request)
