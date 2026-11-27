from django.test import SimpleTestCase

from wagtail_jira_support.forms import SupportRequestForm


class SupportRequestFormTests(SimpleTestCase):
    def test_unbound_form(self):
        form = SupportRequestForm()

        self.assertFalse(form.is_bound)

    def test_required_fields(self):
        form = SupportRequestForm()

        self.assertTrue(form.fields["summary"].required)
        self.assertTrue(form.fields["description"].required)

    def test_billing_code_hidden_by_default(self):
        form = SupportRequestForm()

        self.assertNotIn("billing_code", form.fields)

    def test_billing_code_can_be_enabled(self):
        form = SupportRequestForm(show_billing_code=True)

        self.assertIn("billing_code", form.fields)
        self.assertFalse(form.fields["billing_code"].required)

    def test_valid_form(self):
        form = SupportRequestForm(
            data={
                "summary": "Example problem",
                "description": "Something is not working.",
            }
        )

        self.assertTrue(form.is_valid())

    def test_empty_form(self):
        form = SupportRequestForm(data={})

        self.assertFalse(form.is_valid())
        self.assertIn("summary", form.errors)
        self.assertIn("description", form.errors)

    def test_whitespace_only_fields(self):
        form = SupportRequestForm(
            data={
                "summary": "   ",
                "description": "   ",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("summary", form.errors)
        self.assertIn("description", form.errors)

    def test_summary_maximum_length(self):
        form = SupportRequestForm(
            data={
                "summary": "x" * 255,
                "description": "Example description.",
            }
        )

        self.assertTrue(form.is_valid())

    def test_summary_exceeds_maximum_length(self):
        form = SupportRequestForm(
            data={
                "summary": "x" * 256,
                "description": "Example description.",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("summary", form.errors)

    def test_billing_code_is_optional(self):
        form = SupportRequestForm(
            data={
                "summary": "Example problem",
                "description": "Example description.",
            },
            show_billing_code=True,
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["billing_code"], "")

    def test_billing_code_is_trimmed(self):
        form = SupportRequestForm(
            data={
                "summary": "Example problem",
                "description": "Example description.",
                "billing_code": "  ABC-123  ",
            },
            show_billing_code=True,
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["billing_code"],
            "ABC-123",
        )

    def test_billing_code_exceeds_maximum_length(self):
        form = SupportRequestForm(
            data={
                "summary": "Example problem",
                "description": "Example description.",
                "billing_code": "x" * 256,
            },
            show_billing_code=True,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("billing_code", form.errors)

    def test_hidden_billing_code_is_ignored(self):
        form = SupportRequestForm(
            data={
                "summary": "Example problem",
                "description": "Example description.",
                "billing_code": "UNEXPECTED",
            },
            show_billing_code=False,
        )

        self.assertTrue(form.is_valid())
        self.assertNotIn("billing_code", form.cleaned_data)

    def test_unexpected_fields_are_ignored(self):
        form = SupportRequestForm(
            data={
                "summary": "Example problem",
                "description": "Example description.",
                "serviceDeskId": "999",
                "requestTypeId": "999",
                "raiseOnBehalfOf": "another-user",
            }
        )

        self.assertTrue(form.is_valid())

        self.assertEqual(
            set(form.cleaned_data),
            {"summary", "description"},
        )
