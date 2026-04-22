"""
CMS Bridge — after final AMS approval, push an approval record into CMS's
uploads table so it appears at /uploads/ in the CMS browser.

Behaviour:
  • If req.receipt is set   → encrypt & copy the receipt file to the shared volume
  • If req.receipt is empty → generate a JSON approval-summary document instead

The record is upserted using a deterministic UUID (derived from req.id) so
calling this function twice for the same request is idempotent.

Flow:
  AMS approval finalised
        ↓
  sync_receipt_to_cms(req)   ← called via transaction.on_commit
        ↓
  1. Build file bytes (receipt OR JSON summary)
  2. Fernet-encrypt with shared DOCUMENT_ENCRYPTION_KEY (same key as CMS)
  3. Write encrypted bytes to shared volume (shared_receipts/…)
  4. UPSERT into cms_schema.uploads_uploadeddocument (CMS table)
        ↓
  CMS /uploads/ shows the document — no code changes in CMS needed
"""
import json
import logging
import os
import uuid

from django.db import connection
from django.utils import timezone

logger = logging.getLogger(__name__)

_SHARED_DIR = "shared_receipts"


def _get_fernet():
    """Return a Fernet instance if DOCUMENT_ENCRYPTION_KEY is configured, else None."""
    try:
        from decouple import config
        key = config("DOCUMENT_ENCRYPTION_KEY", default="")
        if not key:
            return None
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def _doc_uuid(req):
    """Deterministic UUID for a request so repeated syncs are idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ams-request-{req.id}"))


def sync_receipt_to_cms(req):
    """
    Push an approved AMS request into CMS's uploads table.
    Always creates a record — uses the receipt file if present, otherwise a
    JSON approval summary.  Silently logs on failure so it never interrupts
    the approval flow.
    """
    try:
        now = timezone.now()
        doc_id = _doc_uuid(req)

        if req.receipt:
            with req.receipt.open("rb") as f:
                raw_bytes = f.read()
            original_name = os.path.basename(req.receipt.name)
            ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "pdf"
            content_type = "application/pdf"
        else:
            summary = {
                "ams_request_id": req.id,
                "title": req.title,
                "service": req.service_name,
                "request_type": req.get_request_type_display(),
                "status": req.state_display,
                "submitted_by": (
                    req.submitted_by.get_full_name() or req.submitted_by.username
                ),
                "cost": str(req.cost) if req.cost else None,
                "justification": req.justification,
                "synced_at": now.isoformat(),
            }
            raw_bytes = json.dumps(summary, indent=2, ensure_ascii=False).encode()
            original_name = f"ams_request_{req.id}.json"
            ext = "json"
            content_type = "application/json"

        fernet = _get_fernet()
        file_bytes = fernet.encrypt(raw_bytes) if fernet else raw_bytes
        file_size = len(raw_bytes)

        storage_key = f"{_SHARED_DIR}/{now.year}/{now.month:02d}/{doc_id}.{ext}"

        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        if default_storage.exists(storage_key):
            default_storage.delete(storage_key)
        default_storage.save(storage_key, ContentFile(file_bytes))

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM cms_schema.accounts_user"
                " WHERE is_staff = true ORDER BY id LIMIT 1"
            )
            row = cursor.fetchone()
            if not row:
                logger.warning(
                    "CMS bridge: no staff user in cms_schema.accounts_user"
                    " — skipping sync for AMS request #%s.",
                    req.id,
                )
                return
            cms_user_id = str(row[0])

        title = f"AMS: {req.service_name or req.title}"
        description = (
            f"Auto-synced from AMS. "
            f"Request #{req.id} | {req.get_request_type_display()} | "
            f"Status: {req.state_display}"
        )

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cms_schema.uploads_uploadeddocument
                    (id, title, document_type, description, storage_key,
                     original_filename, file_size, content_type,
                     is_confidential, uploaded_by_id, uploaded_at, company_id)
                VALUES (%s, %s, 'receipt', %s, %s, %s, %s, %s,
                        false, %s, NOW(), NULL)
                ON CONFLICT (id) DO UPDATE SET
                    title             = EXCLUDED.title,
                    description       = EXCLUDED.description,
                    storage_key       = EXCLUDED.storage_key,
                    original_filename = EXCLUDED.original_filename,
                    file_size         = EXCLUDED.file_size,
                    content_type      = EXCLUDED.content_type
                """,
                [
                    doc_id, title, description, storage_key,
                    original_name, file_size, content_type, cms_user_id,
                ],
            )

        logger.info(
            "CMS bridge: synced AMS request #%s → CMS upload %s",
            req.id, doc_id,
        )

    except Exception as exc:
        logger.error(
            "CMS bridge: failed to sync AMS request #%s: %s",
            req.id, exc, exc_info=True,
        )
