"""Contact lookup helpers using macOS Contacts via native framework."""

import subprocess
from typing import Tuple
from Contacts import CNContactStore, CNPhoneNumber, CNContactFetchRequest
import Contacts
from .utils import normalize_address


def is_contact(sender: str) -> Tuple[bool, str]:
    """Return (True, name) if sender is found in Contacts; otherwise (False, "").

    Args:
        sender: Phone number or email address to check

    Returns:
        Tuple of (is_contact: bool, contact_name: str)
    """
    if not sender:
        return False, ""

    normalized = normalize_address(sender)
    if not normalized:
        return False, ""

    result = _check_contact_native(sender, normalized)
    if result is not None:
        return result

    return False, ""


def _check_contact_native(
    original_sender: str, normalized_sender: str
) -> Tuple[bool, str] | None:
    """Try to check contact using native Python framework.

    Returns None if framework not available or error occurs.
    """
    try:
        store = CNContactStore.alloc().init()
        keys = [
            Contacts.CNContactPhoneNumbersKey,
            Contacts.CNContactEmailAddressesKey,
            Contacts.CNContactFamilyNameKey,
            Contacts.CNContactGivenNameKey,
        ]

        # Result container
        found_contact = [None]  # Use list for closure capture

        def check_contact(contact, stop_ptr):
            """Block to check each contact."""
            try:
                name = contact.givenName() or ""
                if contact.familyName():
                    name = f"{name} {contact.familyName()}".strip()

                # Check phone numbers
                phones = contact.phoneNumbers()
                if phones:
                    for phone_label in phones:
                        phone_number = phone_label.value()
                        phone_str = phone_number.stringValue()

                        # Normalize both sides and compare
                        stored_normalized = normalize_address(phone_str)

                        # Try exact match first
                        if phone_str == original_sender:
                            found_contact[0] = (True, name)
                            stop_ptr[0] = True
                            return

                        # Try normalized comparison
                        if stored_normalized == normalized_sender:
                            found_contact[0] = (True, name)
                            stop_ptr[0] = True
                            return

                # Check emails
                emails = contact.emailAddresses()
                if emails:
                    for email_label in emails:
                        email_str = email_label.value()
                        if email_str.lower() == normalized_sender:
                            found_contact[0] = (True, name)
                            stop_ptr[0] = True
                            return
            except Exception:
                pass

        # Create fetch request
        fetch_request = Contacts.CNContactFetchRequest.alloc().initWithKeysToFetch_(
            keys
        )

        # Enumerate contacts
        store.enumerateContactsWithFetchRequest_error_usingBlock_(
            fetch_request, None, check_contact
        )

        if found_contact[0]:
            return found_contact[0]

        return False, ""
    except Exception:
        return None
