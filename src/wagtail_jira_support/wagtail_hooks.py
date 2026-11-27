from django.urls import include, path, reverse
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from .conf import get_settings, is_enabled


class JiraSupportMenuItem(MenuItem):
    """Menu item for the Jira support interface."""

    def is_shown(self, request):
        return (
            is_enabled()
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.has_perm("wagtailadmin.access_admin")
        )


@hooks.register("register_admin_urls")
def register_jira_support_urls():
    return [
        path(
            "jira-support/",
            include("wagtail_jira_support.urls"),
        ),
    ]


@hooks.register("register_admin_menu_item")
def register_jira_support_menu_item():
    config = get_settings()

    return JiraSupportMenuItem(
        config["MENU_LABEL"],
        reverse("wagtail_jira_support:index"),
        name="jira-support",
        icon_name="help",
        order=config["MENU_ORDER"],
    )
