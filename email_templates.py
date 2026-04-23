import os
import re
import json
import random
import warnings
import logging
from pathlib import Path

import pandas as pd
from transformers import pipeline, logging as hf_logging

# -------------------------
# setup
# -------------------------

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "true"
os.environ["HF_ENABLE_PARALLEL_LOADING"] = "true"

warnings.filterwarnings("ignore")
hf_logging.set_verbosity_error()
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

INPUT_FILE = "bucket_output.csv"
OUTPUT_DIR = Path("campaign_output")
OUTPUT_DIR.mkdir(exist_ok=True)

GEN_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
RANDOM_STATE = 42
random.seed(RANDOM_STATE)

# -------------------------
# campaign input
# -------------------------

campaign = input("Enter campaign cause: ").strip()
if not campaign:
    raise ValueError("Campaign cause cannot be empty.")

# -------------------------
# load bucket csv
# -------------------------

print("Loading data...")
df = pd.read_csv(INPUT_FILE)

required_cols = [
    "Name of bucket",
    "Count of bucket",
    "Rational of the bucket",
    "Suggested treatment",
    "SQL"
]

missing = [c for c in required_cols if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

df = df.fillna("Unknown").copy()

# -------------------------
# turn each csv row into a bucket summary
# -------------------------

def summarize_bucket(row: pd.Series, bucket_id: int) -> dict:
    try:
        bucket_size = int(row["Count of bucket"])
    except Exception:
        bucket_size = 0

    return {
        "bucket_name": str(row["Name of bucket"]).strip(),
        "bucket_rationale": str(row["Rational of the bucket"]).strip(),
        "suggested_treatment": str(row["Suggested treatment"]).strip(),
        "sql": str(row["SQL"]).strip(),
        "size": bucket_size,
        "bucket_id": bucket_id,
    }

summaries = {
    idx: summarize_bucket(row, idx)
    for idx, (_, row) in enumerate(df.iterrows())
}

# -------------------------
# load local model
# -------------------------

print("Loading local model...")
generator = pipeline(
    "text-generation",
    model=GEN_MODEL,
    device="cpu"
)

# -------------------------
# style helpers
# -------------------------

OPENING_STYLES = [
    "warm and reassuring",
    "practical and clear",
    "encouraging and upbeat",
    "friendly and conversational",
    "supportive and calm",
    "direct but caring",
]

CTA_STYLES = [
    "invite the reader to take one simple next step",
    "encourage a low-pressure follow-up action",
    "suggest a practical next step without sounding pushy",
    "make the next step feel easy and approachable",
]

BODY_FLAVORS = [
    "sound human and natural, not corporate",
    "include a little warmth and personality",
    "feel specific rather than generic",
    "avoid sounding like a template",
    "sound like a helpful outreach message from a real care team",
]

# -------------------------
# bucket angle so each bucket sounds different
# -------------------------

def bucket_angle(summary: dict, bucket_id: int) -> str:
    bucket_name = summary["bucket_name"].lower()
    rationale = summary["bucket_rationale"].lower()
    treatment = summary["suggested_treatment"].lower()

    angle_parts = []

    if "preventive" in bucket_name or "care gap" in bucket_name:
        angle_parts.append("emphasize prevention, timely follow-up, and simple next steps")
    elif "sms engagement" in bucket_name:
        angle_parts.append("use a more responsive, conversational, action-oriented tone")
    elif "no prior" in bucket_name or "no engagement" in bucket_name:
        angle_parts.append("use a gentle, encouraging, low-pressure tone")
    else:
        angle_parts.append("use a practical, clear, member-friendly tone")

    if "primary care" in treatment:
        angle_parts.append("encourage reconnecting with a primary care provider")
    elif "screening" in treatment or "wellness" in treatment:
        angle_parts.append("focus on checkups, screenings, and prevention")
    elif "outreach" in treatment:
        angle_parts.append("make the message feel like a thoughtful reminder")
    else:
        angle_parts.append("keep the action step easy and realistic")

    if "high risk" in rationale or "chronic" in rationale:
        angle_parts.append("sound supportive and proactive")
    elif "engagement" in rationale:
        angle_parts.append("sound helpful and responsive")
    else:
        angle_parts.append("sound informative and easy to follow")

    angle_parts.append(OPENING_STYLES[bucket_id % len(OPENING_STYLES)])
    angle_parts.append(CTA_STYLES[bucket_id % len(CTA_STYLES)])
    angle_parts.append(BODY_FLAVORS[bucket_id % len(BODY_FLAVORS)])

    return "; ".join(angle_parts)

def bucket_hook(summary: dict, bucket_id: int) -> str:
    bucket_name = summary["bucket_name"]
    treatment = summary["suggested_treatment"]

    hooks = [
        f"make the email feel relevant to people in the {bucket_name} group",
        f"naturally connect the message to {treatment.lower()}",
        f"make the outreach feel timely and useful instead of routine",
        f"sound like the message was written with this bucket in mind",
        f"let the language feel a little more personal and less scripted",
    ]
    return hooks[bucket_id % len(hooks)]

# -------------------------
# prompt + generation
# -------------------------

def build_prompt(summary: dict, campaign_text: str, previous_subjects: list[str], bucket_id: int) -> str:
    recent = " | ".join(previous_subjects[-10:]) if previous_subjects else "none"
    angle = bucket_angle(summary, bucket_id)
    hook = bucket_hook(summary, bucket_id)

    return f"""
Write one outreach email for a healthcare campaign.

Campaign:
{campaign_text}

This is for bucket {bucket_id}.

Bucket summary:
- bucket name: {summary['bucket_name']}
- rationale: {summary['bucket_rationale']}
- suggested treatment: {summary['suggested_treatment']}
- bucket size: {summary['size']}

Writing guidance:
- {angle}
- {hook}

Requirements:
- make the email clearly related to the campaign
- explain in a natural way why the reader is receiving the email
- include one clear next step
- use exactly 2 short paragraphs
- do not use bullet points
- do not use markdown
- do not use hashtags
- do not use placeholders like [Recipient Name], [Reader Name], [Member Name], or [Your Name]
- do not begin with greetings like Dear _, Hi _, Hello _, Dear [Name], or Dear Member
- do not write generic labels like "Subject line" or "Full Email Body"
- do not sound like an ad, press release, or social media post
- use normal sentence capitalization
- do not write in all caps
- keep punctuation and spacing clean
- make the writing feel warm, natural, and specific
- vary sentence openings and word choice
- avoid repeating the same phrasing from prior emails
- make this bucket feel distinct from the others
- do not copy or sound too similar to these recent subjects: {recent}

Return only valid JSON:
{{
  "subject": "subject line here",
  "body": "full email body here"
}}
""".strip()

def generate_raw(prompt: str, temperature: float = 0.92, max_new_tokens: int = 240) -> str:
    result = generator(
        prompt,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        do_sample=True,
        top_p=0.94,
        repetition_penalty=1.08,
        num_return_sequences=1,
        return_full_text=False
    )[0]["generated_text"]
    return result.strip()

# -------------------------
# cleanup helpers
# -------------------------

def extract_json(text: str):
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return None

def normalize_whitespace(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def strip_wrapping_quotes(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    text = text.strip('"').strip("'").strip("`")
    return text.strip()

def fix_spacing_before_punctuation(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([A-Za-z])", r"\1 \2", text)
    return text

def smart_sentence_case(text: str) -> str:
    if not text:
        return ""

    if text.isupper():
        text = text.lower()

    chars = list(text)
    capitalize_next = True

    for i, ch in enumerate(chars):
        if capitalize_next and ch.isalpha():
            chars[i] = ch.upper()
            capitalize_next = False
        elif ch in ".!?":
            capitalize_next = True
        elif ch.isalpha():
            capitalize_next = False

    return "".join(chars)

def normalize_subject_case(subject: str) -> str:
    if not subject:
        return ""

    subject = normalize_whitespace(subject)
    subject = strip_wrapping_quotes(subject)
    subject = fix_spacing_before_punctuation(subject)

    if subject.isupper():
        subject = subject.lower()

    parts = subject.split()
    if parts:
        normalized = []
        for i, w in enumerate(parts):
            if i == 0:
                normalized.append(w.capitalize())
            elif re.fullmatch(r"[A-Z]{2,}", w):
                normalized.append(w.title())
            else:
                normalized.append(w)
        subject = " ".join(normalized)

    subject = re.sub(r"\s+", " ", subject).strip(" -:;,.\"'`")
    return subject[:120]

def normalize_body_case(body: str) -> str:
    if not body:
        return ""

    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    cleaned = []

    for p in paragraphs:
        p = normalize_whitespace(p)
        p = strip_wrapping_quotes(p)
        p = fix_spacing_before_punctuation(p)

        if p.isupper():
            p = p.lower()

        p = smart_sentence_case(p)
        cleaned.append(p)

    body = "\n\n".join(cleaned)

    replacements = {
        " i ": " I ",
        "\ni ": "\nI ",
        "\ni'm": "\nI'm",
        " i've ": " I've ",
        " i'll ": " I'll ",
        " i'd ": " I'd ",
    }
    for old, new in replacements.items():
        body = body.replace(old, new)

    body = re.sub(r"\s+", " ", body.replace("\n\n", "<<<PARA>>>"))
    body = body.replace("<<<PARA>>>", "\n\n")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return body

def clean_subject(subject: str) -> str:
    if not isinstance(subject, str):
        return ""

    subject = strip_wrapping_quotes(subject)

    leak_patterns = [
        r"^\s*subject\s*:\s*",
        r"^\s*subject line\s*:\s*",
        r"^\s*here(?:'s| is)\s+(?:a\s+)?subject(?:\s+line)?\s*:\s*",
        r"^\s*suggested\s+subject(?:\s+line)?\s*:\s*",
        r"^\s*use\s+this\s+subject(?:\s+line)?\s*:\s*",
        r"^\s*email\s+subject\s*:\s*",
        r"^\s*json\s*:\s*",
    ]

    for pattern in leak_patterns:
        subject = re.sub(pattern, "", subject, flags=re.IGNORECASE)

    if "\n" in subject:
        parts = [p.strip(" -:;,.\"'`") for p in subject.splitlines() if p.strip()]
        if parts:
            subject = parts[0]

    subject = normalize_subject_case(subject)

    bad_subjects = {
        "subject line",
        "subject",
        "email subject",
        "care reminder",
    }

    if subject.lower() in bad_subjects:
        return ""

    return subject

def clean_body(body: str) -> str:
    if not isinstance(body, str):
        return ""

    body = strip_wrapping_quotes(body)
    body = body.replace("\\n", "\n")

    body = re.sub(r"^\s*body\s*:\s*", "", body, flags=re.IGNORECASE)
    body = re.sub(r"^\s*email\s+body\s*:\s*", "", body, flags=re.IGNORECASE)
    body = re.sub(r"^\s*full\s+email\s+body\s*:\s*", "", body, flags=re.IGNORECASE)

    body = re.sub(
        r"^\s*(dear|hi|hello)\s+[_\-\[\]A-Za-z]{0,20}[,\s]*\n*",
        "",
        body,
        flags=re.IGNORECASE
    )

    body = normalize_whitespace(body)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if len(paragraphs) >= 2:
        body = "\n\n".join(paragraphs[:2])
    else:
        body = paragraphs[0] if paragraphs else ""

    body = normalize_body_case(body)
    return body

def has_bad_placeholders(text: str) -> bool:
    bad_patterns = [
        r"\[recipient.*?\]",
        r"\[reader.*?\]",
        r"\[your name\]",
        r"\[member.*?\]",
        r"\[name\]",
        r"\bfull email body\b",
        r"\bsubject line\b",
        r"#\w+",
        r"\bdear\s+[_\-\[]",
        r"\bhi\s+[_\-\[]",
        r"\bhello\s+[_\-\[]",
    ]
    text_lower = text.lower()
    return any(re.search(p, text_lower, flags=re.IGNORECASE) for p in bad_patterns)

def is_greeting_only_body(body: str) -> bool:
    if not body:
        return True

    test = body.strip().lower()

    bad_exact = {
        "dear",
        "dear _",
        "dear __",
        "dear [name]",
        "dear member",
        "hi",
        "hi _",
        "hello",
        "hello _",
    }
    if test in bad_exact:
        return True

    stripped = re.sub(
        r"^(dear|hi|hello)\s+[^\n,]{0,40}[,\s]*",
        "",
        test,
        flags=re.IGNORECASE
    ).strip()

    words = re.findall(r"\w+", stripped)
    if len(words) < 18:
        return True

    if not re.search(r"[.!?]", body):
        return True

    return False

def count_phrase_overlap(text: str, prior_texts: list[str]) -> int:
    if not text or not prior_texts:
        return 0

    text_ngrams = set()
    words = re.findall(r"\w+", text.lower())
    for i in range(len(words) - 2):
        text_ngrams.add(" ".join(words[i:i+3]))

    overlap = 0
    for prior in prior_texts[-8:]:
        prior_words = re.findall(r"\w+", prior.lower())
        for i in range(len(prior_words) - 2):
            ngram = " ".join(prior_words[i:i+3])
            if ngram in text_ngrams:
                overlap += 1
    return overlap

def vary_subject(subject: str, bucket_id: int) -> str:
    subject = clean_subject(subject)

    if not subject:
        return ""

    replacements = [
        ("Support for", ["Support for", "Help for", "Resources for"]),
        ("Reminder about", ["Reminder about", "Update on", "Information about"]),
        ("Your next step for", ["Your next step for", "Next steps for", "What to know about"]),
        ("Helpful update about", ["Helpful update about", "A quick update about", "New information about"]),
        ("Care reminder", ["Care reminder", "Health reminder", "Care update"]),
    ]

    for base, options in replacements:
        if subject.lower().startswith(base.lower()):
            picked = options[bucket_id % len(options)]
            subject = re.sub(rf"^{re.escape(base)}", picked, subject, flags=re.IGNORECASE)
            break

    subject = normalize_subject_case(subject)
    return subject[:120]

def vary_body_wording(body: str, bucket_id: int) -> str:
    body = clean_body(body)

    swaps = [
        (r"\bplease contact our office\b", [
            "please contact our office",
            "please reach out to our office",
            "please get in touch with our office",
        ]),
        (r"\bwe are reaching out\b", [
            "we are reaching out",
            "our team is reaching out",
            "we wanted to reach out",
        ]),
        (r"\bthis may be relevant to your care\b", [
            "this may be relevant to your care",
            "this may be helpful for your care",
            "this may be relevant to your health needs",
        ]),
        (r"\blearn more\b", [
            "learn more",
            "find out more",
            "get more information",
        ]),
        (r"\bnext step\b", [
            "next step",
            "next move",
            "helpful next step",
        ]),
    ]

    for pattern, options in swaps:
        if re.search(pattern, body, flags=re.IGNORECASE):
            replacement = options[bucket_id % len(options)]
            body = re.sub(pattern, replacement, body, count=1, flags=re.IGNORECASE)

    body = clean_body(body)
    return body.strip()

def looks_good(subject: str, body: str, campaign_text: str, previous_bodies: list[str]) -> bool:
    if not subject or len(subject) < 6:
        return False

    if not body or len(body) < 120:
        return False

    if has_bad_placeholders(subject) or has_bad_placeholders(body):
        return False

    if is_greeting_only_body(body):
        return False

    if body.count("\n\n") != 1:
        return False

    subject_lower = subject.lower()
    body_lower = body.lower()

    bad_phrases = [
        "millions of patients",
        "important news",
        "thank you! #",
        "dear [",
        "dear _",
        "hi _",
        "hello _",
        "full email body",
        "subject line",
        "click here now",
    ]
    if any(p in subject_lower or p in body_lower for p in bad_phrases):
        return False

    campaign_words = [
        w.lower() for w in re.findall(r"\w+", campaign_text)
        if len(w) > 3
    ]
    overlap = sum(1 for w in campaign_words if w in body_lower or w in subject_lower)
    if overlap == 0 and campaign_text.lower() not in body_lower:
        return False

    if count_phrase_overlap(body, previous_bodies) > 4:
        return False

    return True

def fallback_email(summary: dict, campaign_text: str, bucket_id: int):
    bucket_name = summary["bucket_name"]
    treatment = summary["suggested_treatment"]

    subject_options = [
        f"Support for {campaign_text}",
        f"Helpful update about {campaign_text}",
        f"Your next step for {campaign_text}",
        f"Reminder about {campaign_text}",
        f"Information about {campaign_text}",
        f"Resources for {campaign_text}",
    ]
    subject = vary_subject(subject_options[bucket_id % len(subject_options)], bucket_id)

    if not subject:
        subject = normalize_subject_case(f"Support for {campaign_text}")

    fallback_openers = [
        f"We wanted to share information that may be useful for people in the {bucket_name} group.",
        f"We're reaching out because this information may be especially relevant to members in the {bucket_name} group.",
        f"This message is intended to share support and guidance that may be helpful for people in the {bucket_name} group.",
        f"We're sharing this because the topic of {campaign_text} may be relevant for members in the {bucket_name} group.",
    ]

    fallback_ctas = [
        f"If you'd like to take the next step, consider {treatment.lower()} or contacting your care team for more guidance.",
        f"If this applies to you, a good next step may be to explore {treatment.lower()} or reach out to your health plan.",
        f"If you'd like more support, consider {treatment.lower()} or talking with your care team about what makes sense for you.",
        f"If you want to learn more, you may want to look into {treatment.lower()} or connect with your provider for follow-up.",
    ]

    body = (
        f"{fallback_openers[bucket_id % len(fallback_openers)]} "
        f"This outreach is related to {campaign_text} and is meant to offer a clear, helpful next step.\n\n"
        f"{fallback_ctas[bucket_id % len(fallback_ctas)]}"
    )

    body = vary_body_wording(body, bucket_id)
    return subject, body

# -------------------------
# generate one email per bucket
# -------------------------

def generate_email(summary: dict, campaign_text: str, previous_subjects: list[str], previous_bodies: list[str], bucket_id: int):
    prompt = build_prompt(summary, campaign_text, previous_subjects, bucket_id)

    candidates = []

    for i in range(8):
        raw = generate_raw(
            prompt,
            temperature=0.88 + (i * 0.03),
            max_new_tokens=230
        )

        parsed = extract_json(raw)
        if not parsed:
            continue

        subject = vary_subject(parsed.get("subject", ""), bucket_id)
        body = vary_body_wording(parsed.get("body", ""), bucket_id)

        if looks_good(subject, body, campaign_text, previous_bodies):
            return subject, body

        if subject and body and not is_greeting_only_body(body):
            score = len(subject) + len(body) - (count_phrase_overlap(body, previous_bodies) * 20)
            candidates.append((score, subject, body))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        _, subject, body = candidates[0]
        return subject, body

    return fallback_email(summary, campaign_text, bucket_id)

# -------------------------
# generate all emails
# -------------------------

print("Generating emails...")

templates = []
previous_subjects = []
previous_bodies = []

for bucket_id in sorted(summaries.keys()):
    summary = summaries[bucket_id]

    subject, body = generate_email(
        summary=summary,
        campaign_text=campaign,
        previous_subjects=previous_subjects,
        previous_bodies=previous_bodies,
        bucket_id=bucket_id
    )

    previous_subjects.append(subject)
    previous_bodies.append(body)

    templates.append({
        "bucket_id": bucket_id,
        "bucket_name": summary["bucket_name"],
        "count_of_bucket": summary["size"],
        "subject": subject,
        "body": body
    })

    print(f"Bucket {bucket_id} done")

# -------------------------
# save final output
# -------------------------

templates_df = pd.DataFrame(templates)
templates_df.to_csv(OUTPUT_DIR / "email_templates.csv", index=False)

print("\nDONE")
print(f"Saved to: {OUTPUT_DIR / 'email_templates.csv'}")
