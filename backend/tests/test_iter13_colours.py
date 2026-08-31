"""Iteration 13 — colour-coding verification by rasterising the pack PDFs.

Samples the actual pixel colour of each data row (left of the row, inside the first
cell) and asserts a unique colour per owner (reconciliation) and per meter (meters).

Run serially:  python -m pytest tests/test_iter13_colours.py -n 0
"""
import os

import fitz
import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
MONTH = "2026-08"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@societyhub.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token") or r.json().get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def prop(client):
    props = client.get(f"{API}/properties").json()
    named = [p for p in props if p["name"] == "Sunrise Residency"]
    return (named or props)[0]


@pytest.fixture(scope="module")
def stmt(client, prop):
    return client.get(f"{API}/statement", params={"property_id": prop["id"], "month": MONTH}).json()


def row_colours(pdf_bytes, needles, section_marker=None):
    """Return {needle: '#rrggbb'} sampling the row background where the text sits.

    `section_marker` restricts sampling to pages from the one containing that
    marker onwards (needed for the combined pack, where owner names also appear
    in the meters section with the meter palette).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zoom = 2.0
    out = {}
    pages = list(doc)
    if section_marker:
        start = next((i for i, p in enumerate(pages) if p.search_for(section_marker)), 0)
        pages = pages[start:]
    for page in pages:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        for needle in needles:
            if needle in out:
                continue
            hits = page.search_for(needle)
            if not hits:
                continue
            r = hits[0]
            # sample a few px left of the text, vertically centred on the row
            x = int((r.x0 - 3) * zoom)
            y = int(((r.y0 + r.y1) / 2) * zoom)
            if x < 1 or y < 1 or x >= pix.width or y >= pix.height:
                continue
            out[needle] = "#%02x%02x%02x" % pix.pixel(x, y)
    return out


def test_reconciliation_unique_colour_per_owner(client, prop, stmt):
    r = client.get(f"{API}/reports/pack", params={"property_id": prop["id"], "month": MONTH,
                                                  "report": "reconciliation", "format": "pdf"})
    assert r.status_code == 200
    owners = sorted({x["owner_name"] for x in stmt["rows"] if x.get("owner_name")})
    got = row_colours(r.content, owners)
    assert len(got) == len(owners), f"owners not located in PDF: {set(owners) - set(got)}"
    assert all(c != "#ffffff" for c in got.values()), f"un-tinted owner rows: {got}"
    assert len(set(got.values())) == len(got), f"duplicate owner row colours: {got}"


def test_meters_unique_colour_per_meter(client, prop, stmt):
    r = client.get(f"{API}/reports/pack", params={"property_id": prop["id"], "month": MONTH,
                                                  "report": "meters", "format": "pdf"})
    assert r.status_code == 200
    labels = [m["label"] for m in stmt["meters"] if m.get("label")]
    got = row_colours(r.content, labels)
    assert len(got) == len(set(labels)), f"meters not located: {set(labels) - set(got)}"
    assert all(c != "#ffffff" for c in got.values()), f"un-tinted meter rows: {got}"
    assert len(set(got.values())) == len(got), f"duplicate meter row colours: {got}"


def test_owner_colour_stable_between_single_and_combined_pdf(client, prop, stmt):
    owners = sorted({x["owner_name"] for x in stmt["rows"] if x.get("owner_name")})
    single = client.get(f"{API}/reports/pack", params={"property_id": prop["id"], "month": MONTH,
                                                      "report": "reconciliation", "format": "pdf"}).content
    combined = client.get(f"{API}/reports/pack", params={"property_id": prop["id"], "month": MONTH,
                                                        "report": "all", "format": "pdf"}).content
    a = row_colours(single, owners)
    b = row_colours(combined, owners, section_marker="Water reconciliation")
    assert a == b, f"owner colours drift between single and combined pack: {a} vs {b}"
