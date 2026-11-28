from django import forms


class SupportRequestForm(forms.Form):
    """Form for submitting a Jira support request."""

    summary = forms.CharField(
        label="Summary",
        max_length=255,
        help_text="Briefly summarize your request.",
    )

    description = forms.CharField(
        label="Description",
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text=(
            "Describe your request in detail. Where applicable, "
            "include steps to reproduce the problem and any "
            "relevant error messages."
        ),
    )

    billing_code = forms.CharField(
        label="Billing Code",
        required=False,
        max_length=255,
        help_text="Enter a billing code if applicable.",
    )

    def __init__(self, *args, show_billing_code=False, **kwargs):
        super().__init__(*args, **kwargs)

        if not show_billing_code:
            self.fields.pop("billing_code")
