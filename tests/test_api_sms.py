def test_sms_webhook_twilio_shape(client):
    r = client.post(
        "/webhooks/sms",
        data={"From": "+15551234567", "Body": "Lusaka"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    assert "Lusaka" in r.text

    r2 = client.get("/whereis/+15551234567")
    assert r2.status_code == 200
    assert "Lusaka" in r2.text


def test_sms_webhook_rejects_missing_body(client):
    r = client.post("/webhooks/sms", data={"From": "+15551234567"})
    assert r.status_code == 400


def test_sms_twiml_escapes_xml(client):
    from whereis.db import raw_connection

    with raw_connection() as cx:
        cx.execute(
            "INSERT INTO places (geonameid, name, asciiname, alternatenames, "
            "country_code, admin1, lat, lng, population, timezone) "
            "VALUES (9999, ?, ?, '', 'XX', '', 0.0, 0.0, 1, 'UTC')",
            ("<Ghost> & Co.", "Ghost"),
        )
        cx.execute(
            "INSERT INTO places_fts(rowid, name, asciiname, alternatenames) VALUES (9999, ?, ?, '')",
            ("<Ghost> & Co.", "Ghost"),
        )
        cx.commit()

    r = client.post("/webhooks/sms", data={"From": "+15551112222", "Body": "Ghost"})
    assert r.status_code == 200
    assert "&lt;Ghost&gt; &amp; Co." in r.text
    assert "<Ghost>" not in r.text


def test_sms_webhook_returns_json_on_accept(client):
    r = client.post(
        "/webhooks/sms",
        data={"From": "+15551234567", "Body": "Lusaka"},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["place"] == "Lusaka"
    assert body["country"] == "ZM"


def test_display_name_derived_from_email(client):
    client.post("/webhooks/sms", data={"From": "anna.li@dimagi.com", "Body": "Dodoma"})
    r = client.get("/whereis.json").json()
    assert r[0]["display_name"] == "Anna Li"
