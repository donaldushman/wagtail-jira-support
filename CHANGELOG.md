# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

- Initial package structure.
- Django application configuration.
- Unit test environment.
- Configurable package settings and validation.
- Application-specific exception hierarchy.
- Jira Cloud Service Management REST API client.
- Paginated retrieval of service desks and request types.
- Retrieval of request type field definitions.
- Jira user search.
- Support request creation, including submission on behalf of users.
- HTTP authentication, timeout, and error handling.
- Unit tests for Jira API communication.
- Django service layer for Jira request metadata.
- Configurable service desk and request type allowlists.
- Configuration-driven ordering of service desks and request types.
- Cached service desk, request type, and field metadata.
- Connection-scoped cache keys.
- Validation of service desk and request type availability.
- Unit tests for metadata retrieval, filtering, and caching.
- Support request payload preparation and validation.
- Automatic population of configured Jira custom fields.
- Conditional population of URL and billing code fields.
- Application and environment context in request descriptions.
- Source URL sanitization.
- Validation of required Jira request fields.
- Unit tests for request preparation and contextual information.
- Native Wagtail admin support interface.
- Configurable support menu label and ordering.
- Service desk and request type landing page.
- Dynamic display of Jira request type descriptions.
- Wagtail admin permission enforcement.
- Graceful handling of Jira API failures.
- Wagtail integration test environment.
- Automated tests for admin views, menu hooks, and permissions.