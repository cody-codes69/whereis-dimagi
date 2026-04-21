def test_form_get(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Where are you" in r.text


def test_form_post_redirects_prg(client):
    """POST /  → 303 See Other → GET /?ok=<id>&ident=... (Post/Redirect/Get)."""
    r = client.post(
        "/",
        data={"identifier": "nick@dimagi.com", "location": "Dodoma"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/?ok=")
    assert "ident=nick%40dimagi.com" in loc or "ident=nick@dimagi.com" in loc

    # Following the redirect renders the success card AND a blank location field.
    r2 = client.get(loc)
    assert r2.status_code == 200
    assert "Dodoma" in r2.text            # shown in the result card
    # Location input is empty — refresh here cannot re-submit.
    loc_idx = r2.text.find('name="location"')
    assert loc_idx != -1
    assert 'value=""' in r2.text[loc_idx : loc_idx + 250] or \
           'value="' not in r2.text[loc_idx : loc_idx + 250]

    # Time-travel query still picks it up.
    r3 = client.get("/whereis/nick@dimagi.com")
    assert "Dodoma" in r3.text


def test_form_refresh_after_submit_does_not_resubmit(client):
    """Refreshing /?ok=<id> must NOT create another LocationUpdate."""
    r = client.post(
        "/",
        data={"identifier": "dup@dimagi.com", "location": "Dodoma"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    result_url = r.headers["location"]

    # Simulate the user hitting refresh five times.
    for _ in range(5):
        client.get(result_url)

    count = client.get("/whereis.json").json()
    dup_rows = [row for row in count if row["identifier"] == "dup@dimagi.com"]
    assert len(dup_rows) == 1, "PRG should leave exactly one row for the user"


def test_api_batch_tuple_format(client):
    payload = [
        ["alex@dimagi.com", "2011-05-22 16:22", "Lusaka"],
        ["nick@dimagi.com", "2011-05-19 14:05", "Dodoma"],
    ]
    r = client.post("/updates", json=payload)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert {i["place"]["name"] for i in items} == {"Lusaka", "Dodoma"}


def test_api_single_object(client):
    r = client.post("/updates", json={"identifier": "x@y.com", "location": "Boston"})
    assert r.status_code == 200
    assert r.json()[0]["place"]["country_code"] == "US"


def test_whereis_txt_is_tab_separated(client):
    client.post("/updates", json=[["tsv@dimagi.com", "2024-01-01 10:00", "Dodoma"]])
    r = client.get("/whereis.txt")
    assert r.status_code == 200
    assert "tsv@dimagi.com" in r.text
    data_lines = [ln for ln in r.text.splitlines() if ln and not ln.startswith("#")]
    assert data_lines
    parts = data_lines[0].split("\t")
    assert len(parts) == 3
    assert parts[0] == "tsv@dimagi.com"
    assert "Dodoma" in parts[2]


def test_api_rejects_invalid_strategy(client):
    r = client.post(
        "/updates?strategy=not-a-strategy",
        json=[["bob@dimagi.com", "2024-01-01 10:00", "Dodoma"]],
    )
    assert r.status_code == 422


def test_api_accepts_valid_strategy(client):
    r = client.post(
        "/updates?strategy=first",
        json=[["bob@dimagi.com", "2024-01-01 10:00", "Dodoma"]],
    )
    assert r.status_code == 200


def test_shared_secret_blocks_when_missing(client, monkeypatch):
    from whereis.config import settings

    monkeypatch.setattr(settings, "shared_secret", "s3cret")
    r = client.post("/updates", json=[["x@dimagi.com", "2024-01-01 10:00", "Dodoma"]])
    assert r.status_code == 401


def test_shared_secret_accepts_when_header_matches(client, monkeypatch):
    from whereis.config import settings

    monkeypatch.setattr(settings, "shared_secret", "s3cret")
    r = client.post(
        "/updates",
        json=[["x@dimagi.com", "2024-01-01 10:00", "Dodoma"]],
        headers={"X-Shared-Secret": "s3cret"},
    )
    assert r.status_code == 200


def test_batch_commit_single_transaction(client):
    payload = [
        ["batch@dimagi.com", "2024-01-01 10:00", "Dodoma"],
        ["batch@dimagi.com", "2024-01-02 10:00", "Lusaka"],
        ["batch@dimagi.com", "2024-01-03 10:00", "Kampala"],
    ]
    r = client.post("/updates", json=payload)
    assert r.status_code == 200
    assert len(r.json()) == 3
    rows = client.get("/whereis.json").json()
    assert len(rows) == 1
    assert rows[0]["place"] == "Kampala"
