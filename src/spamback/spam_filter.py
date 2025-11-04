# Determines whether a message is spam or not


# TODO: Hook this up to a real spam detection model
def is_spam(message_text):
    spam_keywords = ["prize"]
    message_text_lower = message_text.lower()
    for keyword in spam_keywords:
        if keyword in message_text_lower:
            return True
    return False
