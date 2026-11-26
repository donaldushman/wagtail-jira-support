class JiraSupportError(Exception):
    """Base exception for wagtail-jira-support."""


class JiraConfigurationError(JiraSupportError):
    """Invalid or incomplete package configuration."""


class JiraAPIError(JiraSupportError):
    """An error occurred while communicating with Jira."""


class JiraAuthenticationError(JiraAPIError):
    """Jira authentication failed."""


class JiraPermissionError(JiraAPIError):
    """Insufficient permissions to perform a Jira operation."""


class JiraConnectionError(JiraAPIError):
    """Unable to communicate with Jira."""


class JiraUserNotFoundError(JiraSupportError):
    """Unable to resolve the requester to a Jira account."""
