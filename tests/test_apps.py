from django.apps import apps
from django.test import SimpleTestCase


class AppConfigTests(SimpleTestCase):
    def test_app_is_registered(self):
        config = apps.get_app_config("wagtail_jira_support")

        self.assertEqual(config.name, "wagtail_jira_support")
        self.assertEqual(config.verbose_name, "Wagtail Jira Support")
