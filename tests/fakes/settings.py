"""Example configuration: placeholders only, never a real site's values."""

from enterich import tools
from enterich.config import Settings, load

RESOURCE_URL = "https://erp.example.com/mcp"
ISSUER = "https://id.example.com/realms/example"
JWKS_URL = ISSUER + "/protocol/openid-connect/certs"
CLIENT_ID = "enterich-agent"
SUBJECT = "00000000-0000-0000-0000-000000000001"
API_KEY = "example-api-key"
API_SECRET = "example-api-secret"

ENV: dict[str, str] = {
    "ENTERICH_RESOURCE_URL": RESOURCE_URL,
    "ENTERICH_ISSUER": ISSUER,
    "ENTERICH_JWKS_URL": JWKS_URL,
    "ENTERICH_CLIENT_ID": CLIENT_ID,
    "ENTERICH_SUBJECT": SUBJECT,
    "ENTERICH_ERPNEXT_URL": "http://127.0.0.1:8080",
    "ENTERICH_ERPNEXT_PUBLIC_URL": "https://erp.example.com",
    "ENTERICH_ERPNEXT_API_KEY": API_KEY,
    "ENTERICH_ERPNEXT_API_SECRET": API_SECRET,
    "ENTERICH_COMPANY": "Example GmbH",
}


def settings(**overrides: str) -> Settings:
    env = {**ENV, **{f"ENTERICH_{k.upper()}": v for k, v in overrides.items()}}
    return load(env, tools.names())
