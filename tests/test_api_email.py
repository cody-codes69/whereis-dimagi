import pytest


def test_email_webhook_mailgun_shape(client):
    r = client.post(
        "/webhooks/email",
        data={"sender": "nick@dimagi.com", "body-plain": "here: Dodoma"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["place"] == "Dodoma"

    r2 = client.get("/whereis/nick@dimagi.com")
    assert "Dodoma" in r2.text


def test_email_simulator_module_removed():
    with pytest.raises(ImportError):
        import whereis.adapters.email_simulator  # noqa: F401


def test_email_webhook_still_accepts_simulator_shape(client):
    r = client.post(
        "/webhooks/email",
        data={"sender": "sim@dimagi.com", "body-plain": "here: Amsterdam"},
    )
    assert r.status_code == 200
    assert r.json()["place"] == "Amsterdam"


def test_email_webhook_json_shape(client):
    r = client.post(
        "/webhooks/email",
        json={"sender": "Jeremy <jeremy@dimagi.com>", "text": "Cape Town"},
    )
    assert r.status_code == 200
    assert r.json()["place"] == "Cape Town"
