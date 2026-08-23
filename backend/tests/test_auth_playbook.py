"""Auth playbook checks: bcrypt format, httpOnly cookies, brute-force lockout, seed_admin."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

API = (os.environ.get("REACT_APP_BACKEND_URL")
       or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
ADMIN = {"email": "admin@societyhub.com", "password": "admin123"}


def test_bcrypt_hash_format_in_db():
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    env = dotenv_values("/app/backend/.env")

    async def check():
        cli = AsyncIOMotorClient(env["MONGO_URL"])
        u = await cli[env["DB_NAME"]].users.find_one({"email": ADMIN["email"]})
        cli.close()
        return u

    u = asyncio.get_event_loop().run_until_complete(check()) if False else asyncio.run(check())
    assert u, "admin user not seeded"
    assert u["password_hash"].startswith("$2b$"), u["password_hash"][:10]
    assert "password" not in u


def test_login_sets_httponly_cookies():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body or "token" in body
    raw = r.headers.get("set-cookie", "")
    assert "access_token" in raw, raw
    assert "httponly" in raw.lower(), raw
    assert "secure" in raw.lower(), raw
    # /auth/me works with cookie only
    s = requests.Session()
    s.cookies.update(r.cookies)
    me = s.get(f"{API}/auth/me", timeout=30)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == ADMIN["email"]


def test_brute_force_lockout_on_throwaway_account():
    email = f"test_lock_{uuid.uuid4().hex[:8]}@example.com"
    codes = [requests.post(f"{API}/auth/login", json={"email": email, "password": "wrong"},
                           timeout=30).status_code for _ in range(6)]
    assert 429 in codes, f"no lockout after 6 bad logins: {codes}"
    assert codes.index(429) == 5, f"lockout triggered at attempt {codes.index(429) + 1}: {codes}"


def test_unauthenticated_access_blocked():
    r = requests.get(f"{API}/properties", timeout=30)
    assert r.status_code in (401, 403)
