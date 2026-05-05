from django import forms
from .models import Attendee


TICKET_TYPE_CHOICES = [
    ("", "Select Ticket Type"),
    ("VIP", "VIP Pass"),
    ("EXHIBITOR", "Exhibitor Pass"),
    ("VISITOR", "Visitor Pass"),
]


class CreateBadgeForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your firstname",
            "class": "form-control",
            "id": "firstName",
        }),
    )
    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your lastname",
            "class": "form-control",
            "id": "lastName",
        }),
    )
    job_title = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your job title",
            "class": "form-control",
            "id": "jobTitle",
        }),
    )
    company_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Enter your company name",
            "class": "form-control",
            "id": "companyName",
        }),
    )
    country_of_residence = forms.CharField(
    widget=forms.TextInput(attrs={
        "class": "form-control",
        "id": "countryResidence",
        "placeholder": "Enter country of residence"
    })
)
    nationality = forms.CharField(
    widget=forms.TextInput(attrs={
        "class": "form-control",
        "id": "nationality",
        "placeholder": "Enter nationality"
    })
)
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "Enter email",
            "class": "form-control",
            "id": "email",
            "style": "height: 42px;",
        }),
    )
    mobile_number = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={
            "type": "tel",
            "placeholder": "Enter mobile number",
            "class": "form-control",
            "id": "mobileNumber",
        }),
    )
    ticket_type = forms.ChoiceField(
        choices=TICKET_TYPE_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select select2-modal",
            "id": "ticketType",
        }),
    )
    accepted_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "consent1"}),
        error_messages={"required": "You must agree to the Terms & Conditions."},
    )
    accepted_data_sharing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "consent2"}),
        error_messages={"required": "You must acknowledge the data sharing notice."},
    )
    accepted_marketing = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "consent3"}),
    )

    def clean_first_name(self):
        value = self.cleaned_data.get("first_name", "").strip()
        if len(value) < 2:
            raise forms.ValidationError("First name must be at least 2 characters.")
        if not all(c.isalpha() or c in " -'." for c in value):
            raise forms.ValidationError("First name should only contain letters.")
        return value

    def clean_last_name(self):
        value = self.cleaned_data.get("last_name", "").strip()
        if value and  len(value) < 2:
            raise forms.ValidationError("Last name must be at least 2 characters.")
        if not all(c.isalpha() or c in " -'." for c in value):
            raise forms.ValidationError("Last name should only contain letters.")
        return value

    def clean_country_of_residence(self):
        value = self.cleaned_data.get("country_of_residence")
        if not value:
            raise forms.ValidationError("Please select your country of residence.")
        return value

    def clean_nationality(self):
        value = self.cleaned_data.get("nationality")
        if not value:
            raise forms.ValidationError("Please select your nationality.")
        return value

    def clean_ticket_type(self):
        value = self.cleaned_data.get("ticket_type")
        if not value:
            raise forms.ValidationError("Please select a ticket type.")
        return value