from celery import shared_task
from django.db import transaction,IntegrityError
from .models import Attendee, Badge, Exhibitor
from django.core.mail import send_mail
import logging
from django.utils import timezone
from .utils.emails import send_pending_reminder_email
from .utils.redis_lock import acquire_lock,release_lock
from collections import Counter
from django.db.models import Count


logger = logging.getLogger(__name__)

@shared_task(bind=True)
def bulk_upload_save_task(self, rows, exhibitor_id):
    import re
    import threading
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    try:
        exhibitor = Exhibitor.objects.get(id=exhibitor_id)
        event     = exhibitor.event

        # Initial progress
        self.update_state(state='PROGRESS', meta={'current': 0, 'total': len(rows), 'created': 0, 'skipped': 0})

        # ── Live per-type counters (DB state at task start) ──────────────────
        used_at_start = exhibitor.passes_used_by_type()
        limits = {
            "VIP":      exhibitor.vip_pass_limit,
            "EXHIBITOR": exhibitor.exhibitor_pass_limit,
            "VISITOR":  exhibitor.visitor_pass_limit,
        }
        # Track how many we've created per type in this task run
        created_by_type = {"VIP": 0, "EXHIBITOR": 0, "VISITOR": 0}

        created     = 0
        skipped     = 0
        seen_emails = set()

        VALID_TICKET_TYPES = {"VIP", "EXHIBITOR", "VISITOR"}
        NAME_RE            = re.compile(r"^[A-Za-z \-'.]+$")
        BATCH_SIZE         = 200

        existing_emails = set(
            Attendee.objects.filter(exhibitor=exhibitor)
            .values_list("email", flat=True)
        )

        def is_valid_row(row, email, ticket_type):
            first_name   = str(row.get("first_name")  or "").strip()
            last_name    = str(row.get("last_name")   or "").strip()
            country      = str(row.get("country")     or "").strip()
            nationality  = str(row.get("nationality") or "").strip()
            accepted_terms = row.get("accepted_terms", False)

            if not first_name:
                return False, "First name is required"
            if len(first_name) < 2:
                return False, "First name must be at least 2 characters"
            if not NAME_RE.match(first_name):
                return False, "First name contains invalid characters"

            if last_name:
                if len(last_name) < 2:
                    return False, "Last name must be at least 2 characters"
                if not NAME_RE.match(last_name):
                    return False, "Last name contains invalid characters"

            if not email or "@" not in email:
                return False, "Invalid email address"
            try:
                validate_email(email)
            except ValidationError:
                return False, "Email address format is invalid"
            if email in existing_emails:
                return False, "Email already exists in database"
            if email in seen_emails:
                return False, "Duplicate email within this upload"

            if not country:
                return False, "Country is required"
            if not nationality:
                return False, "Nationality is required"

            if not ticket_type:
                return False, "Ticket type is required"
            if ticket_type not in VALID_TICKET_TYPES:
                return False, f"Invalid ticket type: {ticket_type}"

            if not accepted_terms:
                return False, "Terms & Conditions must be accepted"

            # ── Per-type limit check ──────────────────────────────────────────
            total_used_for_type = used_at_start[ticket_type] + created_by_type[ticket_type]
            if total_used_for_type >= limits[ticket_type]:
                return False, f"{ticket_type} pass limit reached ({limits[ticket_type]})"

            return True, None

        emails_to_send = []

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            
            # Update progress
            self.update_state(state='PROGRESS', meta={
                'current': i,
                'total': len(rows),
                'created': created,
                'skipped': skipped
            })

            with transaction.atomic():
                batch_emails = []

                for row in batch:
                    raw_email   = row.get("email") or ""
                    email       = raw_email.strip().lower()
                    ticket_type = str(row.get("ticket_type") or "").strip().upper()

                    valid, reason = is_valid_row(row, email, ticket_type)
                    if not valid:
                        skipped += 1
                        logger.warning(f"Row skipped — {reason} | email={email}")
                        continue

                    seen_emails.add(email)

                    try:
                        attendee = Attendee.objects.create(
                            event                = event,
                            exhibitor            = exhibitor,
                            first_name           = str(row.get("first_name") or "").strip(),
                            last_name            = str(row.get("last_name")  or "").strip(),
                            email                = email,
                            mobile_number        = row.get("mobile_number") or None,
                            job_title            = row.get("job_title")     or None,
                            company_name         = row.get("company_name")  or None,
                            country_of_residence = str(row.get("country")     or "").strip(),
                            nationality          = str(row.get("nationality") or "").strip(),
                            attendee_type        = ticket_type,
                            source               = "Bulk Upload",
                            status               = "CONFIRMED",
                            accepted_terms        = bool(row.get("accepted_terms",         False)),
                            accepted_data_sharing = bool(row.get("accepted_data_sharing",  False)),
                            accepted_marketing    = bool(row.get("accepted_marketing",      False)),
                            digital_badge_issued  = bool(row.get("digital_badge_issued",   False)),
                            onsite_badge_printed  = bool(row.get("onsite_badge_printed",   False)),
                        )

                        Badge.objects.create(
                            attendee   = attendee,
                            badge_type = ticket_type,
                        )

                        created += 1
                        created_by_type[ticket_type] += 1
                        batch_emails.append((attendee, ticket_type))

                    except IntegrityError as e:
                        logger.warning(f"IntegrityError for {email}: {e}", exc_info=True)
                        skipped += 1
                    except Exception as e:
                        logger.error(f"Unexpected error for row {row}: {e}", exc_info=True)
                        skipped += 1

            emails_to_send.extend(batch_emails)

        def send_all_emails(pairs):
            for attendee, ticket_type in pairs:
                try:
                    send_badge_confirmation_email(attendee, ticket_type)
                except Exception as exc:
                    logger.error("Bulk confirmation email failed for %s: %s", attendee.email, exc)

        if emails_to_send:
            threading.Thread(target=send_all_emails, args=(emails_to_send,), daemon=True).start()

    finally:
        pass

    return {
        "created":     created,
        "skipped":     skipped,
        "total_valid": len(rows),
        # ── Return per-type summary for the frontend ──────────
        "created_by_type": created_by_type,
    }

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


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
        logger.info(f"Successfully sent invitation email to {attendee.email}")

    except Exception as exc:
        # Log the failure but never let an email error break badge creation
        import logging
        logging.getLogger(__name__).error(
            "Badge confirmation email failed for %s: %s", attendee.email, exc
        )

@shared_task(
    bind=True,
    rate_limit='100/m',  # max 100 emails per minute
    max_retries=3
)
def send_invite_email(self,email, token):
    try:
        logger.info(f"Attempting to send invitation email to {email}")
        link = f"http://127.0.0.1:8000/register/{token}/"

        send_mail(
            subject="You're Invited!",
            message=f"Click to register: {link}",
            from_email="abhinand@veuz.in",
            recipient_list=[email],
        )
        logger.info(f"Successfully sent invitation email to {email}")
    except Exception as exc:
        logger.error(f"Error sending invitation email to {email}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True)
def process_invitations_batch(self, entries, exhibitor_id):
    from .models import Attendee, Exhibitor

    try:
        exhibitor = Exhibitor.objects.get(id=exhibitor_id)
        event = exhibitor.event

        incoming_emails = {
            (e.get("email") or "").strip().lower()
            for e in entries if (e.get("email") or "").strip()
        }

        # ── Fix: chunk the email__in query to avoid SQLite's 999 variable limit ──
        SQLITE_CHUNK = 900  # safe margin under 999

        incoming_emails_list = list(incoming_emails)
        existing_emails = set()

        for i in range(0, len(incoming_emails_list), SQLITE_CHUNK):
            chunk = incoming_emails_list[i:i + SQLITE_CHUNK]
            existing_emails.update(
                Attendee.objects.filter(event=event, email__in=chunk)
                .values_list("email", flat=True)
            )

        to_create = []
        skipped_count = 0

        for entry in entries:
            email      = (entry.get("email") or "").strip().lower()
            first_name = (entry.get("first_name") or "").strip()
            last_name  = (entry.get("last_name") or "").strip()
            ticket_type=(entry.get("ticket_type") or "").strip()

            if not email or not first_name:
                skipped_count += 1
                continue

            if email in existing_emails:
                logger.info(f"Skipping {email} — already exists.")
                skipped_count += 1
                continue

            to_create.append(Attendee(
                event=event,
                exhibitor=exhibitor,
                email=email,
                first_name=first_name,
                last_name=last_name,
                attendee_type=ticket_type,
                status=Attendee.Status.INVITED,
            ))
        

         # ── Ticket type limit validation ──────────────────────────
        ticket_counts = Counter(att.attendee_type for att in to_create)

        existing_counts = dict(
            Attendee.objects.filter(exhibitor=exhibitor)
            .values_list('attendee_type')
            .annotate(cnt=Count('id'))
            .values_list('attendee_type', 'cnt')
        )

        remaining = {
            "VIP":       max(0, exhibitor.vip_pass_limit       - existing_counts.get("VIP", 0)),
            "EXHIBITOR": max(0, exhibitor.exhibitor_pass_limit - existing_counts.get("EXHIBITOR", 0)),
            "VISITOR":   max(0, exhibitor.visitor_pass_limit   - existing_counts.get("VISITOR", 0)),
        }

        errors = []
        for ticket_type, needed in ticket_counts.items():
            available = remaining.get(ticket_type, 0)
            if needed > available:
                limit = getattr(exhibitor, f"{ticket_type.lower()}_pass_limit", 0)
                errors.append(
                    f"{ticket_type}: requested {needed}, only {available} remaining (limit {limit})"
                )

        if errors:
            raise ValueError("Ticket type limits exceeded: " + "; ".join(errors))

        created = []
        for i in range(0, len(to_create), 500):
            created += Attendee.objects.bulk_create(to_create[i:i + 500])

        sent_count = 0
        for attendee in created:
            if attendee.pk:
                send_invite_email.delay(attendee.email, str(attendee.invite_token))
                sent_count += 1
            else:
                skipped_count += 1

        logger.info(f"✅ Batch complete — Sent: {sent_count} | Skipped: {skipped_count}")

        # 👇 This is what makes the result available to poll
        return {
            "sent_count":    sent_count,
            "skipped_count": skipped_count,
        }

    except Exhibitor.DoesNotExist:
        logger.error(f"Exhibitor {exhibitor_id} not found.")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        raise


@shared_task(bind=True,max_tries=3)
def send_pending_attendee_reminders(self):

    now=timezone.now()
    pending_attendees=Attendee.objects.filter(
        status=Attendee.Status.PENDING,
        event__end_date__gte=now
    ).select_related("event","exhibitor")
    total=pending_attendees.count()
    sent=0
    failed=0

    for attendee in pending_attendees:
        try:
            send_pending_reminder_email(attendee)
            sent+=1
            logger.info(f"Reminder sent to {attendee.email}")
        except Exception as exc:
            failed+=1
            logger.error(f"Failed to send reminder to {attendee.email}: {exc}")
    logger.info(f"Pending reminders done — sent: {sent}, failed: {failed}, total: {total}")
    return {"sent": sent, "failed": failed, "total": total}


