def test_form_get(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Where are you" in r.text


def test_form_post_records_update(client):
    r = client.post("/", data={"identifier": "nick@dimagi.com", "location": "Dodoma"})
    assert r.status_code == 200
    assert "Dodoma" in r.text

    # Time-travel query picks it up.
    r2 = client.get("/whereis/nick@dimagi.com")
    assert "Dodoma" in r2.text


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
