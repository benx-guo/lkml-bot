"""Thread backfill from lore.kernel.org

Fetches existing replies for a thread via t.mbox.gz and saves them to the DB,
so the Thread Overview is complete from the start.
"""

import email.header
import email.utils
import gzip
import logging
import mailbox
import tempfile
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.repo import FeedMessageData, FeedMessageRepository
from .feed_message_classifier import classify_message

logger = logging.getLogger(__name__)


async def fetch_thread_mbox(subsystem: str, message_id_header: str) -> Optional[bytes]:
    """Fetch the t.mbox.gz archive for a thread from lore.kernel.org.

    Args:
        subsystem: Subsystem name (e.g. "rust-for-linux")
        message_id_header: Root message ID header

    Returns:
        Raw gzipped mbox bytes on success, None on error
    """
    url = f"https://lore.kernel.org/{subsystem}/{message_id_header}/t.mbox.gz"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.warning(
                    "Failed to fetch thread mbox from %s (status %d)",
                    url,
                    response.status_code,
                )
                return None
            return response.content
    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching thread mbox from %s: %s", url, e)
        return None


def _decode_header(value: Optional[str]) -> str:
    """Decode an RFC 2047 encoded email header."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return "".join(decoded)


def _strip_angle_brackets(value: Optional[str]) -> Optional[str]:
    """Strip angle brackets from a Message-ID string."""
    if not value:
        return None
    value = value.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    return value


def _get_text_payload(msg: mailbox.mboxMessage) -> str:
    """Extract text/plain content from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def _parse_single_mbox_message(msg, subsystem_name: str) -> Optional[FeedMessageData]:
    """Parse a single mbox message into FeedMessageData.

    Returns:
        FeedMessageData or None if parsing fails
    """
    mid = _strip_angle_brackets(msg.get("Message-ID"))
    if not mid:
        return None

    in_reply_to = _strip_angle_brackets(msg.get("In-Reply-To"))
    subject = _decode_header(msg.get("Subject", ""))
    author_name, author_email = email.utils.parseaddr(
        _decode_header(msg.get("From", ""))
    )

    received_at: Optional[datetime] = None
    date_str = msg.get("Date")
    if date_str:
        try:
            received_at = email.utils.parsedate_to_datetime(date_str)
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            received_at = None

    classification = classify_message(
        subject=subject,
        in_reply_to_header=in_reply_to,
        message_id_header=mid,
    )
    patch_info = classification.patch_info

    return FeedMessageData(
        subsystem_name=subsystem_name,
        message_id_header=mid,
        message_id=mid,
        in_reply_to_header=in_reply_to,
        subject=subject,
        author=author_name or author_email or "unknown",
        author_email=author_email or "unknown@example.com",
        content=_get_text_payload(msg),
        url=f"https://lore.kernel.org/{subsystem_name}/{mid}/",
        received_at=received_at,
        is_patch=classification.is_patch,
        is_reply=classification.is_reply,
        is_series_patch=classification.is_series_patch,
        patch_version=patch_info.version if patch_info else None,
        patch_index=patch_info.index if patch_info else None,
        patch_total=patch_info.total if patch_info else None,
        is_cover_letter=patch_info.is_cover_letter if patch_info else False,
        series_message_id=classification.series_message_id,
    )


def parse_mbox_messages(mbox_data: bytes, subsystem_name: str) -> list[FeedMessageData]:
    """Parse a gzipped mbox archive into FeedMessageData objects.

    Args:
        mbox_data: Raw gzipped mbox bytes
        subsystem_name: Subsystem name for URL construction

    Returns:
        List of FeedMessageData parsed from the mbox
    """
    try:
        raw = gzip.decompress(mbox_data)
    except (gzip.BadGzipFile, OSError) as e:
        logger.warning("Failed to decompress mbox data: %s", e)
        return []

    results: list[FeedMessageData] = []

    with tempfile.NamedTemporaryFile(suffix=".mbox") as tmp:
        tmp.write(raw)
        tmp.flush()
        mbox = mailbox.mbox(tmp.name)

        for msg in mbox:
            try:
                parsed = _parse_single_mbox_message(msg, subsystem_name)
                if parsed:
                    results.append(parsed)
            except (
                ValueError,
                TypeError,
                KeyError,
                UnicodeDecodeError,
                AttributeError,
                LookupError,
            ):
                logger.debug("Failed to parse mbox message", exc_info=True)
                continue

    logger.info("Parsed %d messages from mbox for %s", len(results), subsystem_name)
    return results


def find_root_patch_in_messages(
    messages: list[FeedMessageData],
) -> Optional[FeedMessageData]:
    """Find the root patch (Cover Letter or single patch) in parsed mbox messages.

    Looks for the primary patch message that should be used to create a PatchCard.

    Args:
        messages: List of FeedMessageData parsed from mbox

    Returns:
        The root patch FeedMessageData, or None if not found
    """
    # First: patch without in_reply_to (Cover Letter or standalone)
    for msg in messages:
        if msg.is_patch and not msg.is_reply and not msg.in_reply_to_header:
            return msg
    # Fallback: any non-reply patch message
    for msg in messages:
        if msg.is_patch and not msg.is_reply:
            return msg
    return None


async def backfill_thread_replies(
    session: AsyncSession, subsystem: str, message_id_header: str
) -> int:
    """Backfill existing thread replies from lore.kernel.org into the DB.

    Args:
        session: Database session
        subsystem: Subsystem name
        message_id_header: Root message ID header of the thread

    Returns:
        Number of newly saved messages
    """
    mbox_data = await fetch_thread_mbox(subsystem, message_id_header)
    if not mbox_data:
        return 0

    messages = parse_mbox_messages(mbox_data, subsystem)
    if not messages:
        return 0

    repo = FeedMessageRepository(session)
    new_count = 0

    for msg in messages:
        existing = await repo.find_by_message_id_header(msg.message_id_header)
        if existing:
            continue
        await repo.create_or_update(data=msg)
        new_count += 1

    if new_count > 0:
        logger.info(
            "Backfilled %d new messages (of %d total) for thread %s",
            new_count,
            len(messages),
            message_id_header,
        )

    return new_count
