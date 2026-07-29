import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

_key = os.getenv("FIELD_ENCRYPTION_KEY")
if not _key:
    raise RuntimeError(
        "FIELD_ENCRYPTION_KEY missing in .env — generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

fernet = Fernet(_key.encode())

def encrypt_value(value: str) -> str:
    if value is None or value == "":
        return value
    return fernet.encrypt(str(value).encode()).decode()

def decrypt_value(token: str) -> str:
    if token is None or token == "":
        return token
    try:
        return fernet.decrypt(token.encode()).decode()
    except Exception:
        return token