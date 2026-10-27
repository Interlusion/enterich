"""Example configuration: placeholders only, never a real site's values."""

from erpel.config import Settings, load

RESOURCE_URL = "https://erp.example.com/mcp"
ISSUER = "https://id.example.com/realms/example"
JWKS_URL = ISSUER + "/protocol/openid-connect/certs"
CLIENT_ID = "erpel-agent"
SUBJECT = "00000000-0000-0000-0000-000000000001"
API_KEY = "example-api-key"
API_SECRET = "example-api-secret"

ENV: dict[str, str] = {
    "ERPEL_RESOURCE_URL": RESOURCE_URL,
    "ERPEL_ISSUER": ISSUER,
    "ERPEL_JWKS_URL": JWKS_URL,
    "ERPEL_CLIENT_ID": CLIENT_ID,
    "ERPEL_SUBJECT": SUBJECT,
    "ERPEL_ERPNEXT_URL": "http://127.0.0.1:8080",
    "ERPEL_ERPNEXT_PUBLIC_URL": "https://erp.example.com",
    "ERPEL_ERPNEXT_API_KEY": API_KEY,
    "ERPEL_ERPNEXT_API_SECRET": API_SECRET,
    "ERPEL_COMPANY": "Example GmbH",
}


def settings(**overrides: str) -> Settings:
    env = {**ENV, **{f"ERPEL_{k.upper()}": v for k, v in overrides.items()}}
    return load(env, ())
