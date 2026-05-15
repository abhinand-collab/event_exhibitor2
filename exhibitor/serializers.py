from django import forms
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import Attendee, Exhibitor
import re
import pandas as pd
import phonenumbers
from .utils.countries import COUNTRIES_MAP

class BulkAttendeeSerializer:
    """
    A lightweight serializer-like class for validating bulk attendee rows.
    Returns structured data and a dictionary of error messages.
    """
    
    REQUIRED_FIELDS = ['first_name', 'email', 'ticket_type', 'country', 'nationality', 'accepted_terms']
    VALID_TICKET_TYPES = ['VIP', 'VISITOR', 'EXHIBITOR']
    NAME_RE = re.compile(r"^[A-Za-z\s\-'.]+$")

    def __init__(self, data, exhibitor, existing_emails=None, seen_emails=None):
        self.data = data
        self.exhibitor = exhibitor
        self.existing_emails = existing_emails or set()
        self.seen_emails = seen_emails or set()
        self._errors = {} # Changed to dict: { field_name: [error_msgs] }
        self._validated_data = {}

    def is_valid(self):
        self._errors = {}
        self._validated_data = {}
        
        # 1. Normalize and Clean Data
        cleaned_data = {}
        for k, v in self.data.items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cleaned_data[k] = None
            elif isinstance(v, str):
                cleaned_data[k] = v.strip()
            else:
                cleaned_data[k] = v

        # 2. Basic Required Checks
        for field in self.REQUIRED_FIELDS:
            val = cleaned_data.get(field)
            if field == 'accepted_terms':
                if not self._to_bool(val):
                    self._add_error(field, "Terms must be accepted")
            elif val is None or val == "":
                self._add_error(field, f"Required")
        
        # 3. Field-specific validation
        first_name = str(cleaned_data.get('first_name') or "").strip()
        last_name = str(cleaned_data.get('last_name') or "").strip()
        email = str(cleaned_data.get('email') or "").strip().lower()
        ticket_type = str(cleaned_data.get('ticket_type') or "").strip().upper()
        country = str(cleaned_data.get('country') or "").strip()
        nationality = str(cleaned_data.get('nationality') or "").strip()
        mobile_number = str(cleaned_data.get('mobile_number') or "").strip()
        accepted_terms = self._to_bool(cleaned_data.get('accepted_terms'))

        # Name checks
        if first_name:
            if len(first_name) < 2:
                self._add_error('first_name', "Min 2 chars")
            elif not self.NAME_RE.match(first_name):
                self._add_error('first_name', "Invalid chars")

        if last_name:
            if len(last_name) < 2:
                self._add_error('last_name', "Min 2 chars")
            elif not self.NAME_RE.match(last_name):
                self._add_error('last_name', "Invalid chars")

        # Email checks
        if email:
            try:
                validate_email(email)
                if email in self.existing_emails:
                    self._add_error('email', "Email exists in DB")
                if email in self.seen_emails:
                    self._add_error('email', "Duplicate in file")
            except ValidationError:
                self._add_error('email', "Invalid format")

        # Country validation and mapping for phone validation
        country_code = COUNTRIES_MAP.get(country)
        if country and not country_code:
             self._add_error('country', "Invalid country")

        # Mobile number validation (Country-wise)
        if mobile_number:
            try:
                # If it doesn't start with +, use the country code
                region = country_code if not mobile_number.startswith('+') else None
                parsed_num = phonenumbers.parse(mobile_number, region)
                if not phonenumbers.is_valid_number(parsed_num):
                    self._add_error('mobile_number', "Invalid number for region")
                else:
                    # Normalize to E.164 format
                    mobile_number = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                self._add_error('mobile_number', "Invalid format")

        # Ticket type
        if ticket_type:
            if ticket_type not in self.VALID_TICKET_TYPES:
                self._add_error('ticket_type', f"Invalid type")

        if self._errors:
            return False

        # 4. All good - populate validated data
        self._validated_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'mobile_number': mobile_number or None,
            'job_title': str(cleaned_data.get('job_title') or "").strip() or None,
            'company_name': str(cleaned_data.get('company_name') or "").strip() or None,
            'country': country,
            'nationality': nationality,
            'ticket_type': ticket_type,
            'accepted_terms': accepted_terms,
            'accepted_data_sharing': self._to_bool(cleaned_data.get('accepted_data_sharing')),
            'accepted_marketing': self._to_bool(cleaned_data.get('accepted_marketing')),
        }
        return True

    @property
    def errors(self):
        return self._errors

    @property
    def validated_data(self):
        return self._validated_data

    def _add_error(self, field, message):
        if field not in self._errors:
            self._errors[field] = []
        self._errors[field].append(message)

    def _to_bool(self, val):
        if val is None: return False
        if isinstance(val, bool): return val
        return str(val).lower() in ('true', '1', 'yes', 'y', 'checked')

class BulkInvitationSerializer:
    """
    A lightweight serializer for validating bulk invitations.
    Required fields are minimal: first_name, email, ticket_type.
    """
    REQUIRED_FIELDS = ['first_name', 'email', 'ticket_type']
    VALID_TICKET_TYPES = ['VIP', 'VISITOR', 'EXHIBITOR']
    NAME_RE = re.compile(r"^[A-Za-z\s\-'.]+$")

    def __init__(self, data, exhibitor, existing_emails=None, seen_emails=None):
        self.data = data
        self.exhibitor = exhibitor
        self.existing_emails = existing_emails or set()
        self.seen_emails = seen_emails or set()
        self._errors = {}
        self._validated_data = {}

    def is_valid(self):
        self._errors = {}
        self._validated_data = {}

        # 1. Normalize and Clean Data
        cleaned_data = {}
        for k, v in self.data.items():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cleaned_data[k] = None
            elif isinstance(v, str):
                cleaned_data[k] = v.strip()
            else:
                cleaned_data[k] = v

        # 2. Basic Required Checks
        for field in self.REQUIRED_FIELDS:
            val = cleaned_data.get(field)
            if val is None or val == "":
                self._add_error(field, "Required")

        # 3. Field-specific validation
        first_name = str(cleaned_data.get('first_name') or "").strip()
        last_name = str(cleaned_data.get('last_name') or "").strip()
        email = str(cleaned_data.get('email') or "").strip().lower()
        ticket_type = str(cleaned_data.get('ticket_type') or "").strip().upper()
        mobile_number = str(cleaned_data.get('mobile_number') or "").strip()
        country = str(cleaned_data.get('country') or "").strip() # Optional for phone validation

        # Name checks
        if first_name:
            if len(first_name) < 2:
                self._add_error('first_name', "Min 2 chars")
            elif not self.NAME_RE.match(first_name):
                self._add_error('first_name', "Invalid chars")

        if last_name:
            if len(last_name) < 2:
                self._add_error('last_name', "Min 2 chars")
            elif not self.NAME_RE.match(last_name):
                self._add_error('last_name', "Invalid chars")

        # Email checks
        if email:
            try:
                validate_email(email)
                if email in self.existing_emails:
                    self._add_error('email', "Email exists in DB")
                if email in self.seen_emails:
                    self._add_error('email', "Duplicate in file")
            except (ValidationError, Exception):
                self._add_error('email', "Invalid format")

        # Mobile number validation
        if mobile_number:
            try:
                # Try to get country code if country is provided
                country_code = COUNTRIES_MAP.get(country)
                region = country_code if country_code and not mobile_number.startswith('+') else None
                parsed_num = phonenumbers.parse(mobile_number, region)
                if not phonenumbers.is_valid_number(parsed_num):
                    self._add_error('mobile_number', "Invalid number")
                else:
                    mobile_number = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                self._add_error('mobile_number', "Invalid format")

        # Ticket type
        if ticket_type:
            if ticket_type not in self.VALID_TICKET_TYPES:
                self._add_error('ticket_type', "Invalid type")

        if self._errors:
            return False

        # 4. Populate validated data
        self._validated_data = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'mobile_number': mobile_number or None,
            'ticket_type': ticket_type,
        }
        return True

    @property
    def errors(self):
        return self._errors

    @property
    def validated_data(self):
        return self._validated_data

    def _add_error(self, field, message):
        if field not in self._errors:
            self._errors[field] = []
        self._errors[field].append(message)


class SingleAttendeeSerializer:
    """
    Serializer for single attendee create/update.
    Replaces CreateBadgeForm and manual view validation.
    """
    VALID_TICKET_TYPES = ['VIP', 'VISITOR', 'EXHIBITOR']
    NAME_RE = re.compile(r"^[A-Za-z\s\-'.]+$")

    def __init__(self, data, exhibitor, attendee_id=None):
        self.data = data
        self.exhibitor = exhibitor
        self.attendee_id = attendee_id
        self._errors = {}
        self._validated_data = {}

    def is_valid(self):
        self._errors = {}
        self._validated_data = {}

        # 1. Normalize and Clean Data
        cleaned_data = {}
        for k, v in self.data.items():
            if v is None:
                cleaned_data[k] = None
            elif isinstance(v, str):
                cleaned_data[k] = v.strip()
            else:
                cleaned_data[k] = v

        # 2. Extract fields
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        email = cleaned_data.get('email')
        ticket_type = cleaned_data.get('ticket_type')
        country = cleaned_data.get('country_of_residence')
        nationality = cleaned_data.get('nationality')
        mobile_number = cleaned_data.get('mobile_number')
        accepted_terms = self._to_bool(cleaned_data.get('accepted_terms'))

        # ── REQUIRED CHECKS ──
        if not first_name:
            self._add_error('first_name', "First name is required.")
        
        if not email:
            self._add_error('email', "Email is required.")
        
        if not ticket_type:
            self._add_error('ticket_type', "Ticket type is required.")

        # Country/Nationality mandatory only on create
        if not self.attendee_id:
            if not country:
                self._add_error('country_of_residence', "Country is required.")
            if not nationality:
                self._add_error('nationality', "Nationality is required.")
            if not accepted_terms:
                self._add_error('accepted_terms', "You must agree to the Terms & Conditions.")

        # ── FORMAT CHECKS ──
        if first_name:
            if len(first_name) < 2:
                self._add_error('first_name', "Min 2 characters.")
            elif not self.NAME_RE.match(first_name):
                self._add_error('first_name', "Only letters allowed.")

        if last_name:
            if len(last_name) < 2:
                self._add_error('last_name', "Min 2 characters.")
            elif not self.NAME_RE.match(last_name):
                self._add_error('last_name', "Only letters allowed.")

        if email:
            try:
                validate_email(email)
                qs = Attendee.objects.filter(email=email.lower())
                if self.attendee_id:
                    qs = qs.exclude(id=self.attendee_id)
                if qs.exists():
                    self._add_error('email', "This email is already registered.")
            except ValidationError:
                self._add_error('email', "Invalid email format.")

        if ticket_type:
            if ticket_type.upper() not in self.VALID_TICKET_TYPES:
                self._add_error('ticket_type', "Invalid ticket type.")

        # Mobile number validation (Country-wise)
        if mobile_number:
            try:
                country_code = COUNTRIES_MAP.get(country)
                region = country_code if country and not mobile_number.startswith('+') else None
                parsed_num = phonenumbers.parse(mobile_number, region)
                if not phonenumbers.is_valid_number(parsed_num):
                    self._add_error('mobile_number', "Invalid phone number.")
                else:
                    mobile_number = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                self._add_error('mobile_number', "Invalid format.")

        if self._errors:
            return False

        # 3. All good - populate validated data
        self._validated_data = {
            'first_name': first_name,
            'last_name': last_name or None,
            'email': email.lower() if email else None,
            'mobile_number': mobile_number or None,
            'job_title': cleaned_data.get('job_title') or None,
            'company_name': cleaned_data.get('company_name') or None,
            'country_of_residence': country or None,
            'nationality': nationality or None,
            'ticket_type': ticket_type.upper() if ticket_type else None,
            'accepted_terms': accepted_terms,
            'accepted_data_sharing': self._to_bool(cleaned_data.get('accepted_data_sharing')),
            'accepted_marketing': self._to_bool(cleaned_data.get('accepted_marketing')),
        }
        return True

    @property
    def errors(self):
        return self._errors

    @property
    def validated_data(self):
        return self._validated_data

    def _add_error(self, field, message):
        self._errors[field] = message

    def _to_bool(self, val):
        if val is None: return False
        if isinstance(val, bool): return val
        return str(val).lower() in ('true', '1', 'yes', 'y', 'checked', 'on')
