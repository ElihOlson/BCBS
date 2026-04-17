import os
import re
import json
import warnings
import logging
from pathlib import Path

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
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

INPUT_FILE = "medical_mock_data.csv"
OUTPUT_DIR = Path("campaign_output")
OUTPUT_DIR.mkdir(exist_ok=True)

N_BUCKETS = 6
TOP_MATCH_PERCENT = 0.40
RANDOM_STATE = 42

# local model
GEN_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

# -------------------------
# campaign input
# -------------------------

campaign = input("Enter campaign cause: ").strip()
if not campaign:
    raise ValueError("Campaign cause cannot be empty.")

# -------------------------
# load data
# -------------------------

print("Loading data...")
df = pd.read_csv(INPUT_FILE)

required_cols = [
    "id", "first_name", "last_name", "email", "phone", "city", "state", "zip",
    "dob", "age", "sex", "race", "insurance", "condition", "smoker",
    "language", "opt_in_sms", "opt_in_email"
]

missing = [c for c in required_cols if c not in df.columns]
if missing:
    raise ValueError(f"Missing required columns: {missing}")

df = df[(df["opt_in_email"] == True) & (df["email"].notna())].copy()

for col in ["condition", "insurance", "language", "city", "state"]:
    df[col] = df[col].fillna("Unknown").astype(str).str.strip()

df["age"] = pd.to_numeric(df["age"], errors="coerce").fillna(40)
df["smoker"] = df["smoker"].fillna(False).astype(bool)

# -------------------------
# build profile text
# -------------------------

def profile(row: pd.Series) -> str:
    return (
        f"age {int(row['age'])} "
        f"condition {row['condition']} "
        f"insurance {row['insurance']} "
        f"language {row['language']} "
        f"city {row['city']} "
        f"state {row['state']} "
        f"smoker {'yes' if row['smoker'] else 'no'}"
    )

df["profile"] = df.apply(profile, axis=1)

# -------------------------
# match users to campaign
# -------------------------

print("Matching users to campaign...")

vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
matrix = vectorizer.fit_transform(df["profile"].tolist() + [campaign])

user_vecs = matrix[:-1]
campaign_vec = matrix[-1]

scores = cosine_similarity(user_vecs, campaign_vec).flatten()
df["score"] = scores

cutoff = df["score"].quantile(1 - TOP_MATCH_PERCENT)
target = df[df["score"] >= cutoff].copy()

if len(target) < N_BUCKETS:
    raise ValueError(
        f"Not enough matched users to create {N_BUCKETS} buckets. Found {len(target)}."
    )

# -------------------------
# create buckets
# -------------------------

print("Creating buckets...")

target_vecs = vectorizer.transform(target["profile"].tolist())

kmeans = KMeans(
    n_clusters=N_BUCKETS,
    n_init=10,
    random_state=RANDOM_STATE
)

target["bucket_id"] = kmeans.fit_predict(target_vecs)

# -------------------------
# summarize each bucket
# -------------------------

def safe_mode(series: pd.Series) -> str:
    mode = series.mode(dropna=True)
    return mode.iloc[0] if not mode.empty else "Unknown"

def summarize(group: pd.DataFrame) -> dict:
    return {
        "avg_age": round(group["age"].mean(), 1),
        "age_min": int(group["age"].min()),
        "age_max": int(group["age"].max()),
        "condition": safe_mode(group["condition"]),
        "insurance": safe_mode(group["insurance"]),
        "language": safe_mode(group["language"]),
        "city": safe_mode(group["city"]),
        "state": safe_mode(group["state"]),
        "smoker_rate": round(group["smoker"].mean() * 100, 1),
        "size": int(len(group)),
    }

summaries = {
    b: summarize(target[target["bucket_id"] == b])
    for b in sorted(target["bucket_id"].unique())
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
# bucket angle so each bucket sounds different
# -------------------------

def bucket_angle(summary: dict, bucket_id: int) -> str:
    age = summary["avg_age"]
    condition = str(summary["condition"]).lower()
    insurance = str(summary["insurance"]).lower()
    language = str(summary["language"]).lower()
    city = str(summary["city"])
    state = str(summary["state"])

    angle_parts = []

    if age < 30:
        angle_parts.append("use a younger, concise, action-oriented tone")
    elif age < 55:
        angle_parts.append("use a practical, clear, everyday tone")
    else:
        angle_parts.append("use a reassuring, supportive, easy-to-follow tone")

    if "medicaid" in insurance:
        angle_parts.append("emphasize access, support, and easy next steps")
    elif "medicare" in insurance:
        angle_parts.append("emphasize clarity, trust, and guidance")
    else:
        angle_parts.append("emphasize useful information and convenience")

    if "diabetes" in condition:
        angle_parts.append("mention staying on track with ongoing care")
    elif "anxiety" in condition or "stress" in condition:
        angle_parts.append("sound supportive, calm, and encouraging")
    elif "asthma" in condition or "respiratory" in condition:
        angle_parts.append("emphasize prevention and staying prepared")
    elif "hypertension" in condition or "heart" in condition:
        angle_parts.append("sound steady, supportive, and preventive")
    else:
        angle_parts.append("focus on timely support and practical follow-up")

    if "spanish" in language:
        angle_parts.append("keep the wording especially simple and accessible")
    elif "vietnamese" in language or "arabic" in language or "chinese" in language:
        angle_parts.append("keep the wording very clear and easy to follow")
    else:
        angle_parts.append("keep the wording natural and human")

    if city != "Unknown" and state != "Unknown":
        angle_parts.append(f"make it feel locally relevant to {city}, {state}")

    style_modes = [
        "make it warm and supportive",
        "make it direct and practical",
        "make it encouraging and calm",
        "make it informative and helpful",
        "make it sound local and personal",
        "make it sound like a helpful reminder",
    ]
    angle_parts.append(style_modes[bucket_id % len(style_modes)])

    return "; ".join(angle_parts)

# -------------------------
# prompt + generation
# -------------------------

def build_prompt(summary: dict, campaign_text: str, previous_subjects: list[str], bucket_id: int) -> str:
    recent = " | ".join(previous_subjects[-5:]) if previous_subjects else "none"
    angle = bucket_angle(summary, bucket_id)

    return f"""
Write one outreach email for a healthcare campaign.

Campaign:
{campaign_text}

This is for bucket {bucket_id}.

Audience summary:
- average age: {summary['avg_age']}
- age range: {summary['age_min']} to {summary['age_max']}
- common condition: {summary['condition']}
- common insurance: {summary['insurance']}
- common language: {summary['language']}
- common location: {summary['city']}, {summary['state']}
- smoker rate: {summary['smoker_rate']}%
- bucket size: {summary['size']}

Writing guidance:
- {angle}

Requirements:
- make the email clearly related to the campaign
- explain why the reader is receiving the email
- include one clear next step
- use 2 short paragraphs
- do not use bullet points
- do not use markdown
- make this bucket feel distinct from the others
- do not copy or sound too similar to these recent subjects: {recent}

Return only valid JSON:
{{
  "subject": "subject line here",
  "body": "full email body here"
}}
""".strip()

def generate_raw(prompt: str, temperature: float = 0.85, max_new_tokens: int = 240) -> str:
    result = generator(
        prompt,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        do_sample=True,
        top_p=0.92,
        repetition_penalty=1.10,
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
    except:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass

    return None

def clean_subject(subject: str) -> str:
    if not isinstance(subject, str):
        return "Care reminder"

    subject = subject.strip().strip('"').strip()

    # remove obvious prompt/instruction leakage
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

    # remove wrapping punctuation
    subject = subject.strip(" -:;,.\"'`")
    subject = re.sub(r"\s+", " ", subject)

    # if model returned multiple lines, keep the first usable one
    if "\n" in subject:
        parts = [p.strip(" -:;,.\"'`") for p in subject.splitlines() if p.strip()]
        if parts:
            subject = parts[0]

    if not subject:
        subject = "Care reminder"

    return subject[:120]

def clean_body(body: str) -> str:
    if not isinstance(body, str):
        return ""

    body = body.strip().strip('"').strip()
    body = body.replace("\\n", "\n")
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n +", "\n", body)

    # remove prompty intro leakage if it appears at the top
    body = re.sub(r"^\s*body\s*:\s*", "", body, flags=re.IGNORECASE)
    body = re.sub(r"^\s*email\s+body\s*:\s*", "", body, flags=re.IGNORECASE)

    return body.strip()

def vary_subject(subject: str, bucket_id: int) -> str:
    subject = clean_subject(subject)

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

    subject = re.sub(r"\s+", " ", subject).strip(" -:;,.\"'`")
    return subject[:120]

def vary_body_wording(body: str, bucket_id: int) -> str:
    body = clean_body(body)

    swaps = [
        (r"\bplease contact our office\b", [
            "please contact our office",
            "please reach out to our office",
            "please get in touch with our office",
        ]),
        (r"\bclear next step\b", [
            "clear next step",
            "simple next step",
            "helpful next step",
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
    ]

    for pattern, options in swaps:
        if re.search(pattern, body, flags=re.IGNORECASE):
            replacement = options[bucket_id % len(options)]
            body = re.sub(pattern, replacement, body, count=1, flags=re.IGNORECASE)

    return body.strip()

def looks_good(subject: str, body: str, campaign_text: str) -> bool:
    if len(subject) < 4:
        return False

    if len(body) < 80:
        return False

    if body.count("\n\n") < 1:
        return False

    campaign_words = [
        w.lower() for w in re.findall(r"\w+", campaign_text)
        if len(w) > 3
    ]
    body_lower = body.lower()
    subject_lower = subject.lower()

    overlap = sum(1 for w in campaign_words if w in body_lower or w in subject_lower)
    if overlap == 0 and campaign_text.lower() not in body_lower:
        return False

    return True

def fallback_email(summary: dict, campaign_text: str, bucket_id: int):
    subject_options = [
        f"Support for {campaign_text}",
        f"Helpful update about {campaign_text}",
        f"Your next step for {campaign_text}",
        f"Reminder about {campaign_text}",
        f"Information about {campaign_text}",
        f"Resources for {campaign_text}",
    ]
    subject = vary_subject(subject_options[bucket_id % len(subject_options)], bucket_id)

    body = (
        f"We are reaching out to share information related to {campaign_text}. "
        f"This may be relevant to your care, and we wanted to make sure you have a clear next step.\n\n"
        f"If you would like support or more information, please contact our office and our team can help."
    )
    body = vary_body_wording(body, bucket_id)

    return subject, body

# -------------------------
# generate one email per bucket
# -------------------------

def generate_email(summary: dict, campaign_text: str, previous_subjects: list[str], bucket_id: int):
    prompt = build_prompt(summary, campaign_text, previous_subjects, bucket_id)

    best_subject = None
    best_body = None

    for i in range(4):
        raw = generate_raw(
            prompt,
            temperature=0.85 + (i * 0.05),
            max_new_tokens=240
        )

        parsed = extract_json(raw)
        if not parsed:
            continue

        subject = vary_subject(parsed.get("subject", ""), bucket_id)
        body = vary_body_wording(parsed.get("body", ""), bucket_id)

        if looks_good(subject, body, campaign_text):
            return subject, body

        if subject and body and best_subject is None:
            best_subject, best_body = subject, body

    if best_subject and best_body:
        return best_subject, best_body

    return fallback_email(summary, campaign_text, bucket_id)

# -------------------------
# generate all emails
# -------------------------

print("Generating emails...")

templates = []
previous_subjects = []

for bucket_id in sorted(summaries.keys()):
    summary = summaries[bucket_id]

    subject, body = generate_email(
        summary=summary,
        campaign_text=campaign,
        previous_subjects=previous_subjects,
        bucket_id=bucket_id
    )

    previous_subjects.append(subject)

    templates.append({
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