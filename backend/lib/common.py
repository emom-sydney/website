def now_utc():
    return datetime.now(timezone.utc)


def positive_int_from_env(name, default):
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        # not a throwable error
        return default
    if value <= 0:
        return default
    return value


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

# TODO Make the same as the one in mailer.py
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_text(value):
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def normalize_email(value):
    email = normalize_text(value)
    if not email:
        return None
    email = email.lower()
    if not EMAIL_PATTERN.match(email):
        return None
    return email
