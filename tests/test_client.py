from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from wagtail_jira_support.client import JiraClient
from wagtail_jira_support.exceptions import (
    JiraAPIError,
    JiraAuthenticationError,
    JiraConnectionError,
    JiraPermissionError,
    JiraSubmissionUncertainError,
)


class JiraClientTests(SimpleTestCase):
    def setUp(self):
        self.client = JiraClient(
            base_url="https://example.atlassian.net/",
            email="integration@example.com",
            api_token="test-token",
        )

        self.addCleanup(self.client.close)

        self.request_mock = patch.object(
            self.client.session,
            "request",
        ).start()

        self.addCleanup(patch.stopall)

    def make_response(self, status_code=200, data=None):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = data
        return response

    def test_base_url_is_normalized(self):
        self.assertEqual(
            self.client.base_url,
            "https://example.atlassian.net",
        )

    def test_authentication(self):
        self.assertEqual(
            self.client.session.auth,
            ("integration@example.com", "test-token"),
        )

    def test_default_headers(self):
        self.assertEqual(
            self.client.session.headers["Accept"],
            "application/json",
        )
        self.assertEqual(
            self.client.session.headers["Content-Type"],
            "application/json",
        )

    def test_get_current_user(self):
        data = {
            "accountId": "example-account",
            "displayName": "Example User",
        }

        self.request_mock.return_value = self.make_response(
            data=data,
        )

        result = self.client.get_current_user()

        self.assertEqual(result, data)

        self.request_mock.assert_called_once_with(
            "GET",
            "https://example.atlassian.net/rest/api/3/myself",
            timeout=10,
            allow_redirects=False,
        )

    def test_authentication_error(self):
        self.request_mock.return_value = self.make_response(
            status_code=401,
        )

        with self.assertRaises(JiraAuthenticationError):
            self.client.get_current_user()

    def test_permission_error(self):
        self.request_mock.return_value = self.make_response(
            status_code=403,
        )

        with self.assertRaises(JiraPermissionError):
            self.client.get_current_user()

    def test_api_error(self):
        self.request_mock.return_value = self.make_response(
            status_code=500,
        )

        with self.assertRaises(JiraAPIError):
            self.client.get_current_user()

    def test_redirect_is_rejected(self):
        self.request_mock.return_value = self.make_response(
            status_code=302,
        )

        with self.assertRaises(JiraAPIError):
            self.client.get_current_user()

    def test_timeout(self):
        self.request_mock.side_effect = requests.Timeout

        with self.assertRaises(JiraConnectionError):
            self.client.get_current_user()

    def test_connection_error(self):
        self.request_mock.side_effect = requests.ConnectionError

        with self.assertRaises(JiraConnectionError):
            self.client.get_current_user()

    def test_invalid_json(self):
        response = self.make_response()
        response.json.side_effect = ValueError

        self.request_mock.return_value = response

        with self.assertRaises(JiraAPIError):
            self.client.get_current_user()

    def test_no_content_response(self):
        self.request_mock.return_value = self.make_response(
            status_code=204,
        )

        self.assertIsNone(self.client._request("GET", "/example"))

    def test_absolute_url_is_rejected(self):
        with self.assertRaises(JiraAPIError):
            self.client._request(
                "GET",
                "https://other.example.com",
            )

        self.request_mock.assert_not_called()

    def test_get_service_desks(self):
        desks = [
            {"id": "12", "projectName": "Example Desk"},
        ]

        self.request_mock.return_value = self.make_response(
            data={
                "values": desks,
                "isLastPage": True,
            },
        )

        self.assertEqual(
            self.client.get_service_desks(),
            desks,
        )

    def test_pagination(self):
        self.request_mock.side_effect = [
            self.make_response(
                data={
                    "values": [{"id": "1"}],
                    "isLastPage": False,
                },
            ),
            self.make_response(
                data={
                    "values": [{"id": "2"}],
                    "isLastPage": True,
                },
            ),
        ]

        result = self.client.get_service_desks()

        self.assertEqual(
            result,
            [{"id": "1"}, {"id": "2"}],
        )

        self.assertEqual(self.request_mock.call_count, 2)

        last_call = self.request_mock.call_args

        self.assertEqual(
            last_call.kwargs["params"]["start"],
            1,
        )

    def test_invalid_paginated_response(self):
        self.request_mock.return_value = self.make_response(
            data=[],
        )

        with self.assertRaises(JiraAPIError):
            self.client.get_service_desks()

    def test_empty_intermediate_page(self):
        self.request_mock.return_value = self.make_response(
            data={
                "values": [],
                "isLastPage": False,
            },
        )

        with self.assertRaises(JiraAPIError):
            self.client.get_service_desks()

    def test_get_request_types(self):
        self.request_mock.return_value = self.make_response(
            data={
                "values": [{"id": "100"}],
                "isLastPage": True,
            },
        )

        result = self.client.get_request_types("12")

        self.assertEqual(result, [{"id": "100"}])

        self.assertEqual(
            self.request_mock.call_args.args[1],
            "https://example.atlassian.net"
            "/rest/servicedeskapi/servicedesk/12/requesttype",
        )

    def test_get_request_type_fields(self):
        data = {
            "requestTypeFields": [
                {
                    "fieldId": "summary",
                    "required": True,
                },
            ],
        }

        self.request_mock.return_value = self.make_response(
            data=data,
        )

        result = self.client.get_request_type_fields(
            "12",
            "100",
        )

        self.assertEqual(result, data)

        self.assertEqual(
            self.request_mock.call_args.args[1],
            "https://example.atlassian.net"
            "/rest/servicedeskapi/servicedesk/12"
            "/requesttype/100/field",
        )

    def test_search_users(self):
        data = [
            {
                "accountId": "example-account",
                "emailAddress": "user@example.com",
            },
        ]

        self.request_mock.return_value = self.make_response(
            data=data,
        )

        result = self.client.search_users("user@example.com")

        self.assertEqual(result, data)

        self.assertEqual(
            self.request_mock.call_args.kwargs["params"],
            {
                "query": "user@example.com",
                "maxResults": 50,
            },
        )

    def test_create_request(self):
        self.request_mock.return_value = self.make_response(
            status_code=201,
            data={"issueKey": "TEST-123"},
        )

        fields = {
            "summary": "Example support request",
            "description": "Example description",
        }

        result = self.client.create_request(
            service_desk_id="12",
            request_type_id="100",
            fields=fields,
        )

        self.assertEqual(result["issueKey"], "TEST-123")

        self.request_mock.assert_called_once_with(
            "POST",
            "https://example.atlassian.net/rest/servicedeskapi/request",
            timeout=10,
            allow_redirects=False,
            json={
                "serviceDeskId": "12",
                "requestTypeId": "100",
                "requestFieldValues": fields,
            },
        )

    def test_create_request_on_behalf_of_user(self):
        self.request_mock.return_value = self.make_response(
            status_code=201,
            data={"issueKey": "TEST-124"},
        )

        self.client.create_request(
            service_desk_id="12",
            request_type_id="100",
            fields={"summary": "Example request"},
            raise_on_behalf_of="example-account",
        )

        payload = self.request_mock.call_args.kwargs["json"]

        self.assertEqual(
            payload["raiseOnBehalfOf"],
            "example-account",
        )

    def test_create_request_is_not_retried_after_timeout(self):
        self.request_mock.side_effect = requests.Timeout

        with self.assertRaises(JiraConnectionError):
            self.client.create_request(
                service_desk_id="12",
                request_type_id="100",
                fields={"summary": "Example request"},
            )

        self.request_mock.assert_called_once()

    def test_context_manager_closes_session(self):
        with patch.object(self.client.session, "close") as close:
            with self.client as client:
                self.assertIs(client, self.client)

            close.assert_called_once()


class JiraSubmissionClientTests(SimpleTestCase):
    def setUp(self):
        self.client = JiraClient(
            base_url="https://example.atlassian.net",
            email="integration@example.com",
            api_token="test-token",
        )

        self.addCleanup(self.client.close)

        patcher = patch.object(
            self.client.session,
            "request",
        )

        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def create_request(self):
        return self.client.create_request(
            service_desk_id="12",
            request_type_id="100",
            fields={
                "summary": "Example problem",
                "description": "Example description.",
            },
            raise_on_behalf_of="example-account-id",
        )

    def test_post_server_errors_are_uncertain(self):
        for status_code in (500, 502, 503, 504):
            with self.subTest(status_code=status_code):
                self.request.reset_mock()

                response = Mock()
                response.status_code = status_code

                self.request.return_value = response

                with self.assertRaises(JiraSubmissionUncertainError):
                    self.create_request()

                self.request.assert_called_once()

    def test_get_server_error_is_api_error(self):
        response = Mock()
        response.status_code = 500

        self.request.return_value = response

        with self.assertRaises(JiraAPIError):
            self.client.get_current_user()

    def test_post_invalid_json_is_uncertain(self):
        response = Mock()
        response.status_code = 201
        response.json.side_effect = ValueError("Invalid JSON")

        self.request.return_value = response

        with self.assertRaises(JiraSubmissionUncertainError):
            self.create_request()

        self.request.assert_called_once()

    def test_get_invalid_json_is_api_error(self):
        response = Mock()
        response.status_code = 200
        response.json.side_effect = ValueError("Invalid JSON")

        self.request.return_value = response

        with self.assertRaises(JiraAPIError):
            self.client.get_current_user()

    def test_post_client_error_is_api_error(self):
        response = Mock()
        response.status_code = 400

        self.request.return_value = response

        with self.assertRaises(JiraAPIError):
            self.create_request()

        self.request.assert_called_once()
