def normalize_address(sender: str) -> str:
    """Normalize phone numbers and emails for comparisons.

    - Emails: lowercase and strip whitespace.
    - Phones: strip spaces/dashes/parentheses, drop leading '+'
    """
    if not sender:
        return ""
    s = sender.strip()
    if "@" in s:
        return s.lower()
    # Phone: strip formatting
    s = s.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    if s.startswith("+"):
        s = s[1:]
    return s.lower()
