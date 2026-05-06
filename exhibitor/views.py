# =============================================================================
# IMPORTS
# =============================================================================
import json
import traceback

import pandas as pd
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CreateBadgeForm
from .models import User, Exhibitor, Event, Badge, Attendee
from math import ceil
from django.core.paginator import Paginator
from .tasks import bulk_upload_save_task,send_invite_email,process_invitations_batch
from celery.result import AsyncResult
from django.http import HttpResponse
import openpyxl
import re
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.contenttypes.models import ContentType
from auditlog.models import LogEntry
from itertools import chain
from .utils.redis_lock import acquire_lock,release_lock


# =============================================================================
# AUTH
# =============================================================================

def Login(request):
    """Handle exhibitor login via email + password."""
    if request.method == "POST":
        email    = request.POST.get("email")
        password = request.POST.get("password")
        user     = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")

        return render(request, "login.html", {"error": "Invalid credentials"})

    return render(request, "login.html")


# =============================================================================
# DASHBOARD
# =============================================================================
@login_required(login_url="login")
def index(request):
    exhibitor = request.user.exhibitor
    total_pass = exhibitor.pass_limit
    used_pass = Badge.objects.filter(attendee__exhibitor=exhibitor).count()

    # ── Detailed Stats per Ticket Type ──────────────────────────────────────
    ticket_types = [
        ("VIP", "VIP PASS", exhibitor.vip_pass_limit),
        ("EXHIBITOR", "EXHIBITOR PASS", exhibitor.exhibitor_pass_limit),
        ("VISITOR", "VISITOR PASS", exhibitor.visitor_pass_limit),
    ]
    
    badge_stats = []
    for t_code, t_label, t_limit in ticket_types:
        t_counts = Attendee.objects.filter(exhibitor=exhibitor, attendee_type=t_code).aggregate(
            confirmed=Count("id", filter=Q(status="CONFIRMED")),
            pending=Count("id", filter=Q(status="PENDING")),
            invited=Count("id", filter=Q(status="INVITED")),
        )
        t_used = Badge.objects.filter(attendee__exhibitor=exhibitor, badge_type=t_code).count()
        
        badge_stats.append({
            "label": t_label,
            "limit": t_limit,
            "used": t_used,
            "confirmed": t_counts["confirmed"],
            "pending": t_counts["pending"],
            "invited": t_counts["invited"],
            "percent": int((t_used / t_limit * 100)) if t_limit > 0 else 0
        })

    registrations_qs = Attendee.objects.filter(
        exhibitor=exhibitor
    ).select_related("badge", "exhibitor").order_by("-created_at")

    # ── Filters ─────────────────────────────────────────────────────────────
    search    = request.GET.get("search", "").strip()
    status    = request.GET.get("status", "").strip()
    ticket    = request.GET.get("ticket_type", "").strip()

    if search:
    # Split into words to handle "John Doe" → search first+last name combination
        parts = search.split()

        if len(parts) >= 2:
            # Multi-word: try full name match across first+last AND individual field matches
            registrations_qs = registrations_qs.filter(
                Q(first_name__icontains=parts[0], last_name__icontains=parts[1]) |  # "John Doe"
                Q(first_name__icontains=parts[1], last_name__icontains=parts[0]) |  # "Doe John" (reversed)
                Q(job_title__icontains=search)    |
                Q(company_name__icontains=search)
            )
        else:
            # Single word: search across all fields
            registrations_qs = registrations_qs.filter(
                Q(first_name__icontains=search)   |
                Q(last_name__icontains=search)    |
                Q(job_title__icontains=search)    |
                Q(company_name__icontains=search)
            )
    if status:
        registrations_qs = registrations_qs.filter(status__iexact=status)

    if ticket:
        registrations_qs = registrations_qs.filter(badge__badge_type__iexact=ticket)

    # Get page size from request or default to 10
    page_size = request.GET.get('page_size', 10)
    try:
        page_size = int(page_size)
        if page_size not in [10, 25, 50, 100]:
            page_size = 10
    except ValueError:
        page_size = 10

    # Pagination
    page_number = request.GET.get("page", 1)
    paginator = Paginator(registrations_qs, page_size)
    registrations = paginator.get_page(page_number)
    print(badge_stats,"__badgestats")

    return render(request, "index.html", {
        "registrations": registrations,
        "used_pass": used_pass,
        "total_pass": total_pass,
        "badge_stats": badge_stats,
        "current_page_size": page_size,  # Pass to template
    })

# =============================================================================
# SINGLE BADGE CREATION
# =============================================================================

# Maps form ticket_type strings → Attendee.AttendeeType enum values
TICKET_TYPE_MAP = {
    "VIP"      : Attendee.AttendeeType.VIP,
    "EXHIBITOR": Attendee.AttendeeType.EXHIBITOR,
    "VISITOR"  : Attendee.AttendeeType.VISITOR,
}

# Maps database error snippets → user-friendly messages
DB_ERROR_MESSAGES = {
    "UNIQUE constraint failed": {
        "email": "This email address is already registered."
    },
    "NOT NULL constraint"     : "Please fill in all required fields.",
    "value too long"          : "One of the entered values is too long.",
    "DataError"               : "One of the entered values is too long.",
}


def _friendly_db_error(error_str):
    """Convert a raw database error string into a user-friendly message."""
    if "UNIQUE constraint failed" in error_str and "email" in error_str:
        return "This email address is already registered."
    if "NOT NULL constraint" in error_str:
        return "Please fill in all required fields."
    if "value too long" in error_str or "DataError" in error_str:
        return "One of the entered values is too long."
    return "Something went wrong. Please try again or contact support."


def send_badge_confirmation_email(attendee, ticket_type: str) -> None:
    """
    Send a styled confirmation email to the attendee after badge creation.
    Silently swallows send errors so they never break the main request.
    """
    context = {
        "first_name"  : attendee.first_name,
        "last_name"   : attendee.last_name,
        "email"       : attendee.email,
        "company_name": attendee.company_name,
        "job_title"   : attendee.job_title,
        "country"     : attendee.country_of_residence,
        "ticket_type" : ticket_type,
        "event_name"  : attendee.event.name,  # adjust if your field name differs
    }

    html_body  = render_to_string("emails/badge_confirmation.html", context)
    plain_body = strip_tags(html_body)
    subject    = f"Badge Confirmed – {attendee.event.name}"

    msg = EmailMultiAlternatives(
        subject      = subject,
        body         = plain_body,
        from_email   = None,          # uses DEFAULT_FROM_EMAIL from settings
        to           = [attendee.email],
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        msg.send()
    except Exception as exc:
        # Log the failure but never let an email error break badge creation
        import logging
        logging.getLogger(__name__).error(
            "Badge confirmation email failed for %s: %s", attendee.email, exc
        )
import threading
@login_required
@require_http_methods(["POST"])
def create_single_badge(request):
    # ── 1. Form validation ──────────────────────────────────────────────────
    form = CreateBadgeForm(request.POST)
    if not form.is_valid():
        errors = {field: msgs[0] for field, msgs in form.errors.items()}
        return JsonResponse({"success": False, "errors": errors}, status=400)

    # ── 2. Resolve exhibitor ────────────────────────────────────────────────
    try:
        exhibitor = request.user.exhibitor
    except Exception:
        return JsonResponse(
            {"success": False, "errors": {"__all__": "User is not an exhibitor"}},
            status=403,
        )

    # ── 3. Per-type pass limit check ────────────────────────────────────────
    ticket_type = form.cleaned_data["ticket_type"]  # "VIP" / "EXHIBITOR" / "VISITOR"

    limit_map = {
        "VIP":       exhibitor.vip_pass_limit,
        "EXHIBITOR": exhibitor.exhibitor_pass_limit,
        "VISITOR":   exhibitor.visitor_pass_limit,
    }
    label_map = {
        "VIP":       "VIP",
        "EXHIBITOR": "Exhibitor",
        "VISITOR":   "Visitor",
    }

    limit = limit_map.get(ticket_type, 0)

    # Count only badges of this specific type for this exhibitor
    used = Badge.objects.filter(
        attendee__exhibitor=exhibitor,
        badge_type=ticket_type,
    ).count()

    if used >= limit:
        return JsonResponse({
            "success": False,
            "errors": (
                f"{label_map[ticket_type]} pass limit reached "
                f"({used}/{limit}). Cannot create more {label_map[ticket_type]} badges."
            ),
        }, status=400)

    # ── 4. Create Attendee + Badge ──────────────────────────────────────────
    try:
        with transaction.atomic():
            attendee = Attendee.objects.create(
                event                 = exhibitor.event,
                exhibitor             = exhibitor,
                first_name            = form.cleaned_data["first_name"],
                last_name             = form.cleaned_data["last_name"],
                email                 = form.cleaned_data["email"],
                mobile_number         = form.cleaned_data["mobile_number"],
                job_title             = form.cleaned_data["job_title"],
                company_name          = form.cleaned_data["company_name"],
                country_of_residence  = form.cleaned_data["country_of_residence"],
                nationality           = form.cleaned_data["nationality"],
                attendee_type         = TICKET_TYPE_MAP[ticket_type],
                source                = "Exhibitor Portal",
                status                = Attendee.Status.CONFIRMED,
                accepted_terms        = form.cleaned_data["accepted_terms"],
                accepted_data_sharing = form.cleaned_data["accepted_data_sharing"],
                accepted_marketing    = form.cleaned_data.get("accepted_marketing", False),
            )

            Badge.objects.create(
                attendee   = attendee,
                badge_type = ticket_type,
            )

    except Exception as e:
        print(str(e), 'checkerror')
        return JsonResponse(
            {"success": False, "errors": _friendly_db_error(str(e))},
            status=500,
        )

    threading.Thread(
        target=send_badge_confirmation_email,
        args=(attendee, ticket_type),
        daemon=True,
    ).start()

    return JsonResponse(
        {"success": True, "message": "Badge registered successfully."},
        status=201,
    )


# =============================================================================
# BULK UPLOAD — STEP 1: Get columns from uploaded file
# =============================================================================

@login_required
@require_POST
def get_columns(request):
    """
    Return the column headers from an uploaded CSV / Excel file.
    Used to populate the field-mapping UI before preview.
    """
    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

    if file.name.endswith(".csv"):
        df = pd.read_csv(file, nrows=1)
    else:
        df = pd.read_excel(file, nrows=1)


    return JsonResponse({"columns": list(df.columns)})


# =============================================================================
# BULK UPLOAD — STEP 2: Preview + validate rows
# =============================================================================

def _clean(value):
    """Return a stripped string, or None for NaN / blank values."""
    if pd.isna(value):
        return None
    return str(value).strip() or None


def _to_bool(value):
    """Convert a value to boolean."""
    if pd.isna(value) or value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes", "y", "checked")


def _validate_row(row, existing_emails):
    """
    Validate a single spreadsheet row.
    Returns a list of error strings (empty = valid).
    """
    errors = []

    first_name = row.get("first_name")
    email = row.get("email")
    ticket_type = row.get("ticket_type")
    accepted_terms = row.get("accepted_terms")
    country = row.get("country")
    nationality = row.get("nationality")

    # Required field validations
    if pd.isna(first_name) or not str(first_name).strip():
        errors.append("First name required")

    if pd.isna(email) or "@" not in str(email):
        errors.append("Invalid email")
    elif str(email).strip().lower() in existing_emails:
        errors.append("Email already exists")

    if not ticket_type or pd.isna(ticket_type):
        errors.append("Ticket type required")

    if pd.isna(country) or not str(country).strip():
        errors.append("Country required")

    if pd.isna(nationality) or not str(nationality).strip():
        errors.append("Nationality required")

    if not _to_bool(accepted_terms):
        errors.append("Terms must be accepted")

    # Note: accepted_data_sharing and accepted_marketing are optional
    # They don't cause validation errors if missing

    return errors

# =============================================================================
# BULK UPLOAD — STEP 2: Parse file, return ALL rows + existing emails to JS
# No server-side pagination or filtering needed anymore.
# JS handles everything after this single response.
# =============================================================================
 
@login_required
@require_POST
def bulk_upload_preview(request):
    """
    Parse the uploaded file once and return:
      - data: all rows (no pagination, no filter)
      - existing_emails: the full set of DB emails so JS can validate client-side
    """
    file    = request.FILES.get("file")
    mapping = json.loads(request.POST.get("mapping", "{}"))
 
    if not file:
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)
 
    try:
        # ── Parse ────────────────────────────────────────────────────────────
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
 
        df.columns = [col.strip() for col in df.columns]
        if mapping:
            df.rename(columns=mapping, inplace=True)
        df = df.where(pd.notnull(df), None)
 
        # ── Existing emails — sent to JS once so it can validate client-side ─
        existing_emails = list(
            Attendee.objects.values_list("email", flat=True)
        )
 
        # ── Build row list (no validation — JS does that) ────────────────────
        rows = []
        for index, row in df.iterrows():
            rows.append({
                "id"                  : index,
                "row"                 : index + 1,
                "first_name"          : _clean(row.get("first_name")),
                "last_name"           : _clean(row.get("last_name")),
                "email"               : _clean(row.get("email")),
                "mobile_number"       : _clean(row.get("mobile_number")),
                "country"             : _clean(row.get("country")),
                "nationality"         : _clean(row.get("nationality")),
                "company_name"        : _clean(row.get("company_name")),
                "job_title"           : _clean(row.get("job_title")),
                "ticket_type"         : _clean(row.get("ticket_type")),
                "accepted_terms"      : _to_bool(row.get("accepted_terms")),
                "accepted_data_sharing": _to_bool(row.get("accepted_data_sharing")),
                "accepted_marketing"  : _to_bool(row.get("accepted_marketing")),
                "digital_badge_issued": _to_bool(row.get("digital_badge_issued")),
                "onsite_badge_printed": _to_bool(row.get("onsite_badge_printed")),
                # status / errors intentionally omitted — JS computes them
            })
 
        return JsonResponse({
            "success"        : True,
            "data"           : rows,
            "existing_emails": existing_emails,  # ← new: JS uses this for validation
        })
 
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)
 
@login_required
@require_POST
def bulk_upload_save(request):
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({"success": False, "errors": "Invalid request body."}, status=400)

    rows         = body.get("rows", [])
    chunk_index  = body.get("chunk_index", 0)
    total_chunks = body.get("total_chunks", 1)

    if not rows:
        return JsonResponse({"success": False, "errors": "No valid rows received."}, status=400)

    exhibitor = request.user.exhibitor
    remaining = exhibitor.remaining_by_type()

    # ── Count requested rows per ticket type ─────────────────
    requested = {"VIP": 0, "EXHIBITOR": 0, "VISITOR": 0}
    for row in rows:
        t = str(row.get("ticket_type") or "").strip().upper()
        if t in requested:
            requested[t] += 1

    # ── Check each type ───────────────────────────────────────
    limit_errors = []
    for ticket_type, count in requested.items():
        if count == 0:
            continue
        rem = remaining[ticket_type]
        if rem <= 0:
            limit_errors.append(
                f"{ticket_type}: no passes remaining "
                f"(limit: {getattr(exhibitor, f'{ticket_type.lower()}_pass_limit')})."
            )
        elif count > rem:
            limit_errors.append(
                f"{ticket_type}: trying to import {count} but only {rem} pass(es) remaining "
                f"(limit: {getattr(exhibitor, f'{ticket_type.lower()}_pass_limit')})."
            )

    if limit_errors:
        return JsonResponse({
            "success": False,
            "errors": " | ".join(limit_errors),
        }, status=400)

    task = bulk_upload_save_task.delay(rows, exhibitor.id)

    return JsonResponse({
        "success":  True,
        "task_id":  task.id,
        "message":  f"Chunk {chunk_index + 1}/{total_chunks} queued",
    })
 
# =============================================================================
# NEW — GET EXISTING EMAILS  (called once on "Upload & Process" click)
# Returns all attendee emails so the client can do duplicate detection.
# Replaces the old /get-columns/ and /bulk-upload-preview/ calls entirely.
# =============================================================================
 
@login_required
@require_POST
def get_existing_emails(request):
    """
    Lightweight endpoint: return every existing attendee email.
    The JS stores these in existingEmailsSet for client-side validation.
    No file parsing happens here — SheetJS handles that in the browser.
    """
    emails = list(Attendee.objects.values_list("email", flat=True))
    return JsonResponse({"success": True, "emails": emails})

# =============================================================================
# UTILITY — Real-time email duplicate check (called from frontend)
# =============================================================================

@login_required
@require_POST
def validate_email(request):
    """Return whether an email is already registered as an Attendee."""
    data  = json.loads(request.body)
    email = data.get("email", "").strip().lower()

    exists = Attendee.objects.filter(email=email).exists()
    return JsonResponse({"exists": exists})

@login_required
@require_POST
def bulk_update_session(request):
    """Update session data with edited rows."""
    data = json.loads(request.body)
    updates = data.get("rows", [])

    preview_data = request.session.get("bulk_preview_data", [])
    
    if not preview_data:
        return JsonResponse({"success": False, "error": "No session data found"}, status=400)
    
    # Convert to dict for O(1) lookup
    preview_map = {row["id"]: row for row in preview_data}

    for upd in updates:
        row_id = upd["id"]
        if row_id in preview_map:
            # Update the row with new data
            preview_map[row_id].update(upd)
            
            # Re-validate with existing emails (excluding current email)
            current_email = upd.get("email", "")
            existing_emails = set(
                Attendee.objects.exclude(email=current_email)
                .values_list("email", flat=True)
            )
            
            # Create a copy for validation
            row_copy = preview_map[row_id].copy()
            errors = _validate_row(row_copy, existing_emails)
            
            preview_map[row_id]["errors"] = errors
            preview_map[row_id]["status"] = "valid" if not errors else "invalid"

    # Save back to session
    request.session["bulk_preview_data"] = list(preview_map.values())
    
    # Update counts in session for quick access
    valid_count = sum(1 for row in request.session["bulk_preview_data"] if row["status"] == "valid")
    invalid_count = sum(1 for row in request.session["bulk_preview_data"] if row["status"] == "invalid")
    request.session["bulk_valid_count"] = valid_count
    request.session["bulk_invalid_count"] = invalid_count
    request.session["bulk_total_records"] = len(preview_data)
    
    request.session.modified = True

    return JsonResponse({"success": True})

@login_required
def bulk_task_status(request, task_id):
    result = AsyncResult(task_id)
    
    if result.state == "PENDING":
        return JsonResponse({"state": "PENDING"})
    
    elif result.state == "PROGRESS":
        # info contains the custom meta dict from task.update_state
        return JsonResponse({
            "state": "PROGRESS",
            "progress": result.info
        })
    
    elif result.state == "SUCCESS":
        return JsonResponse({
            "state": "SUCCESS",
            "result": result.result  # spreads created, skipped, total_valid, created_by_type
        })
    
    elif result.state == "FAILURE":
        return JsonResponse({
            "state": "FAILURE",
            "error": str(result.result)
        }, status=500)
    
    return JsonResponse({"state": result.state})


# =============================================================================
# EDIT ATTENDEE — GET current data
# =============================================================================
@login_required
@require_http_methods(["GET"])
def get_attendee(request, attendee_id):
    exhibitor = request.user.exhibitor
    attendee  = get_object_or_404(Attendee, id=attendee_id, exhibitor=exhibitor)

    ticket_type  = ''
    ticket_class = ''
    try:
        ticket_type  = attendee.badge.badge_type   or ''
        ticket_class = attendee.badge.ticket_class or ''
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'attendee': {
            'id'                   : attendee.id,
            'first_name'           : attendee.first_name,
            'last_name'            : attendee.last_name  or '',
            'email'                : attendee.email,
            'mobile_number'        : attendee.mobile_number or '',
            'job_title'            : attendee.job_title     or '',
            'company_name'         : attendee.company_name  or '',
            'country_of_residence' : attendee.country_of_residence or '',
            'nationality'          : attendee.nationality or '',
            'status'               : attendee.status,
            'accepted_terms'       : attendee.accepted_terms,
            'accepted_data_sharing': attendee.accepted_data_sharing,
            'accepted_marketing'   : attendee.accepted_marketing,
            'ticket_type'          : ticket_type,
            'ticket_class'         : ticket_class,
        }
    })


# =============================================================================
# EDIT ATTENDEE — SAVE changes
# =============================================================================
@login_required
@require_http_methods(["POST", "PUT"])
def update_attendee(request, attendee_id):
    exhibitor = request.user.exhibitor
    attendee  = get_object_or_404(Attendee, id=attendee_id, exhibitor=exhibitor)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'errors': 'Invalid JSON.'}, status=400)

    # ── Basic validation ──────────────────────────────────────────────────────
    errors = {}
    first_name   = data.get('first_name', '').strip()
    email        = data.get('email', '').strip()
    ticket_type  = data.get('ticket_type', '').strip()
    country      = data.get('country_of_residence', '').strip()
    nationality  = data.get('nationality', '').strip()

    if not first_name:
        errors['first_name'] = 'First name is required.'
    if not email or '@' not in email:
        errors['email'] = 'A valid email is required.'
    if not ticket_type:
        errors['ticket_type'] = 'Ticket type is required.'
    if not country:
        errors['country_of_residence'] = 'Country of residence is required.'
    if not nationality:
        errors['nationality'] = 'Nationality is required.'

    # Email uniqueness (exclude self)
    if email and not errors.get('email'):
        if Attendee.objects.filter(email=email).exclude(id=attendee_id).exists():
            errors['email'] = 'This email is already registered to another attendee.'

    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    # ── Persist ───────────────────────────────────────────────────────────────
    ticket_class = f"{ticket_type} Pass"
    try:
        with transaction.atomic():
            attendee.first_name           = first_name
            attendee.last_name            = data.get('last_name', '').strip()
            attendee.email                = email
            attendee.mobile_number        = data.get('mobile_number', '').strip() or None
            attendee.job_title            = data.get('job_title', '').strip()     or None
            attendee.company_name         = data.get('company_name', '').strip()  or None
            attendee.country_of_residence = country
            attendee.nationality          = nationality
            attendee.status               = data.get('status', attendee.status)
            attendee.save()

            try:
                badge = attendee.badge
                badge.badge_type   = ticket_type
                badge.ticket_class = ticket_class
                badge.save()
            except Exception:
                Badge.objects.create(
                    attendee     = attendee,
                    badge_type   = ticket_type,
                    ticket_class = ticket_class,
                )

    except Exception as e:
        return JsonResponse({'success': False, 'errors': _friendly_db_error(str(e))}, status=500)

    return JsonResponse({
        'success': True,
        'message': 'Registration updated successfully.',
        'attendee': {
            'first_name'    : attendee.first_name,
            'last_name'     : attendee.last_name     or '',
            'email'         : attendee.email,
            'job_title'     : attendee.job_title     or '',
            'company_name'  : attendee.company_name  or '',
            'status'        : attendee.status,
            'status_display': attendee.get_status_display(),
            'ticket_class'  : ticket_class,
        }
    })


# =============================================================================
# DELETE ATTENDEE
# =============================================================================
@login_required
@require_POST
def delete_attendee(request, attendee_id):
    exhibitor = request.user.exhibitor
    attendee  = get_object_or_404(Attendee, id=attendee_id, exhibitor=exhibitor)
    
    try:
        attendee.delete()
        return JsonResponse({'success': True, 'message': 'Registration deleted successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    

@login_required
@require_http_methods(["GET"])
def export_registrations(request):
    exhibitor = request.user.exhibitor
    qs = Attendee.objects.filter(exhibitor=exhibitor).select_related("badge").order_by("-id")

    # Apply same filters as index view
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()
    ticket = request.GET.get("ticket_type", "").strip()

    if search:
        parts = search.split()
        if len(parts) >= 2:
            qs = qs.filter(
                Q(first_name__icontains=parts[0], last_name__icontains=parts[1]) |
                Q(first_name__icontains=parts[1], last_name__icontains=parts[0]) |
                Q(job_title__icontains=search) |
                Q(company_name__icontains=search)
            )
        else:
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search) |
                Q(job_title__icontains=search)  | Q(company_name__icontains=search)
            )
    if status:
        qs = qs.filter(status__iexact=status)
    if ticket:
        qs = qs.filter(badge__badge_type__iexact=ticket)

    # Build workbook
    wb = openpyxl       .Workbook()
    ws = wb.active
    ws.title = "Registrations"

    headers = [
        "First Name", "Last Name", "Email", "Job Title", "Company Name",
        "Source", "Mobile Number",
        "Country of Residence", "Nationality",
        "Accepted Terms", "Accepted Data Sharing", "Accepted Marketing",
        "Status",
    ]
    ws.append(headers)

    for reg in qs:
        badge        = getattr(reg, "badge", None)
        # ticket_id    = str(badge.ticket_id) if badge and badge.ticket_id else ""
        ws.append([
            reg.first_name,
            reg.last_name or "",
            reg.email,
            reg.job_title or "",
            reg.company_name or "",
            reg.source or "",
            # ticket_id,
            reg.mobile_number or "",
            reg.country_of_residence or "",
            reg.nationality or "",
            # "Yes" if reg.digital_badge_issued else "No",
            # "Yes" if reg.onsite_badge_printed else "No",
            "Yes" if reg.accepted_terms else "No",
            "Yes" if reg.accepted_data_sharing else "No",
            "Yes" if reg.accepted_marketing else "No",
            reg.get_status_display(),
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="registrations.xlsx"'
    wb.save(response)
    return response


# @login_required
# @require_POST
# def send_invitations(request):
#     try:
#         data    = json.loads(request.body)
#         entries = data.get('entries', [])
#     except json.JSONDecodeError:
#         return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

#     if not entries:
#         return JsonResponse({'success': False, 'error': 'No entries provided.'}, status=400)

#     exhibitor = request.user.exhibitor
#     event     = exhibitor.event

#     sent_count    = 0
#     skipped_count = 0
#     errors        = []   # human-readable skip reasons returned to frontend

#     for entry in entries:
#         first_name    = (entry.get("first_name") or "").strip()
#         last_name     = (entry.get("last_name")  or "").strip()
#         email         = (entry.get("email")      or "").strip().lower()
#         attendee_type = (entry.get("ticket_type") or "").strip().upper()

#         # ── Server-side guard (frontend already filters, but be safe) ──
#         if not first_name or not email or not attendee_type:
#             errors.append(f"{email or '(no email)'}: missing required fields — skipped")
#             skipped_count += 1
#             continue

#         try:
#             attendee = Attendee.objects.create(
#                 event         = event,
#                 exhibitor     = exhibitor,
#                 first_name    = first_name,
#                 last_name     = last_name,
#                 email         = email,
#                 attendee_type = attendee_type,
#                 status        = Attendee.Status.INVITED,
#             )
#             # Fire Celery task
#             send_invite_email.delay(attendee.email, str(attendee.invite_token))
#             sent_count += 1

#         except IntegrityError:
#             errors.append(f"{email}: already registered — skipped")
#             skipped_count += 1
#         except Exception as e:
#             errors.append(f"{email}: {str(e)} — skipped")
#             skipped_count += 1

#     return JsonResponse({
#         'success'       : True,
#         'sent_count'    : sent_count,
#         'skipped_count' : skipped_count,
#         'errors'        : errors,
#         'message'       : f'{sent_count} invitation(s) sent, {skipped_count} skipped.',
#     })


@login_required
@require_POST  
def send_invitations(request):
    data = json.loads(request.body)
    entries = data.get('entries', [])

    task = process_invitations_batch.delay(
        entries=entries,
        exhibitor_id=request.user.exhibitor.id,
    )

    return JsonResponse({
        'success': True,
        'task_id': task.id,
        'message': f'Processing {len(entries)} entries in background.'
    })

@login_required
def task_status_invitation(request, task_id):
    result = AsyncResult(task_id)

    response = {"state": result.state}  # PENDING / SUCCESS / FAILURE

    if result.state == "SUCCESS":
        response["result"] = result.result  # {"sent_count": X, "skipped_count": Y}
    elif result.state == "FAILURE":
        response["error"] = str(result.result)

    return JsonResponse(response)

def register_attendee(request, token):
    attendee = get_object_or_404(Attendee, invite_token=token)
 
    # Already confirmed — render template (JS will show success screen)
    if attendee.status == Attendee.Status.CONFIRMED:
        return render(request, "invite_registration.html", {"attendee": attendee})
 
    errors = []
    NAME_RE = re.compile(r"^[a-zA-Z \-'.]+$")
 
    if request.method == "POST":
        mobile      = request.POST.get("mobile", "").strip()
        company     = request.POST.get("company", "").strip()
        country     = request.POST.get("country", "").strip()
        nationality = request.POST.get("nationality", "").strip()
        job_title   = request.POST.get("job_title", "").strip()
 
        # Only terms is required; data sharing and marketing are optional
        accepted_terms        = bool(request.POST.get("accepted_terms"))
        accepted_data_sharing = bool(request.POST.get("accepted_data_sharing"))
        accepted_marketing    = bool(request.POST.get("accepted_marketing"))
 
        # ── Validation (mirrors front-end rules) ────────────────────────────
 
        # mobile
        if not mobile:
            errors.append("Mobile number is required.")
 
        # company
        if not company:
            errors.append("Company name is required.")
        elif len(company) < 2:
            errors.append("Company name must be at least 2 characters.")
 
        # country — text input, letters only
        if not country:
            errors.append("Country of residence is required.")
        elif len(country) < 2:
            errors.append("Please enter a valid country.")
        elif not NAME_RE.match(country):
            errors.append("Country should only contain letters.")
 
        # nationality — letters only
        if not nationality:
            errors.append("Nationality is required.")
        elif len(nationality) < 2:
            errors.append("Please enter a valid nationality.")
        elif not NAME_RE.match(nationality):
            errors.append("Nationality should only contain letters.")
 
        # terms — only required consent
        if not accepted_terms:
            errors.append("You must accept the Terms & Conditions.")
 
        if not errors:
            exhibitor = attendee.exhibitor
 
            used_pass = Attendee.objects.filter(
                exhibitor=exhibitor,
                status=Attendee.Status.CONFIRMED,
            ).count()
 
            if used_pass >= exhibitor.pass_limit:
                errors.append("Pass limit exceeded. Cannot register more attendees.")
            else:
                attendee.mobile_number         = mobile
                attendee.company_name          = company
                attendee.country_of_residence  = country
                attendee.nationality           = nationality
                attendee.job_title             = job_title
                attendee.accepted_terms        = accepted_terms
                attendee.accepted_data_sharing = accepted_data_sharing
                attendee.accepted_marketing    = accepted_marketing
                attendee.source                = "Invitation Portal"
                attendee.status                = Attendee.Status.CONFIRMED
                attendee.save()

                Badge.objects.create(
                    attendee   = attendee,
                    badge_type = attendee.attendee_type,
                )
 
            # Re-render — JS switches to success screen when status == CONFIRMED
            return render(request, "invite_registration.html", {"attendee": attendee})
 
    return render(request, "invite_registration.html", {
        "attendee": attendee,
        "errors"  : errors,
    })

def attendee_audit_logs(request, attendee_id):
    attendee = get_object_or_404(Attendee, id=attendee_id)

    attendee_ct = ContentType.objects.get_for_model(Attendee)
    badge_ct = ContentType.objects.get_for_model(Badge)

    attendee_logs = LogEntry.objects.filter(
        content_type=attendee_ct,
        object_id=str(attendee.id)
    ).select_related("actor")

    badge_logs = LogEntry.objects.none()
    if hasattr(attendee, 'badge'):
        badge_logs = LogEntry.objects.filter(
            content_type=badge_ct,
            object_id=str(attendee.badge.id)
        ).select_related("actor")

    # Build lookup maps
    event_map = {str(e.id): e.name for e in Event.objects.all()}
    exhibitor_map = {str(ex.id): ex.company_name for ex in Exhibitor.objects.all()}

    FK_RESOLVERS = {
        "event":    lambda v: event_map.get(str(v), v),
        "exhibitor": lambda v: exhibitor_map.get(str(v), v),
    }

    def resolve_changes(changes):
        if not changes:
            return {}
        resolved = {}
        for field, vals in changes.items():
            resolver = FK_RESOLVERS.get(field)
            if isinstance(vals, list):
                resolved_vals = []
                for v in vals:
                    if v is None or v == "None":
                        resolved_vals.append(None)  # keep as None, handle in template
                    elif resolver:
                        resolved_vals.append(resolver(str(v)))
                    else:
                        resolved_vals.append(v)
                resolved[field] = resolved_vals
            else:
                resolved[field] = vals
        return resolved

    all_logs = sorted(
        chain(attendee_logs, badge_logs),
        key=lambda x: x.timestamp,
        reverse=True
    )

    # Attach resolved changes to each log as a new attribute
    for log in all_logs:
        log.resolved_changes = resolve_changes(log.changes)

    return render(request, "attendee.html", {
        "attendee": attendee,
        "logs": all_logs,
    })