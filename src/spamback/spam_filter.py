"""Spam classification using RoBERTa model."""

from transformers import RobertaTokenizer, RobertaForSequenceClassification
import torch
import re

MODEL_NAME = "roshana1s/spam-message-classifier"

# Device
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load model and tokenizer on startup
print(f"Loading spam model: {MODEL_NAME}...")
model = RobertaForSequenceClassification.from_pretrained(MODEL_NAME).to(device).eval()
tokenizer = RobertaTokenizer.from_pretrained(MODEL_NAME)


def _preprocess_text(text: str) -> str:
    """Normalize text: mask URLs, collapse whitespace."""
    text = re.sub(r"(https?://\S+|www\.\S+)", "<URL>", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_spam(message_text: str) -> bool:
    """Return True if message is spam."""
    if not message_text:
        return False

    # Preprocess and tokenize
    text = _preprocess_text(message_text)
    inputs = tokenizer(
        text, return_tensors="pt", truncation=True, padding=False, max_length=128
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Run inference
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1).squeeze(0)

    # Index 0 = ham, 1 = spam
    spam_score = float(probs[1])
    ham_score = float(probs[0])

    return spam_score > ham_score
