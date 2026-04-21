from datetime import UTC

from whereis.services.parser import parse_body


def test_parse_plain_location():
    msg = parse_body("Dodoma", identifier="nick@dimagi.com", source="form")
    assert msg.raw_location == "Dodoma"
    assert msg.identifier == "nick@dimagi.com"
    assert msg.source == "form"


def test_parse_strips_prefix():
    msg = parse_body("here: Cape Town", identifier="+15551234567", source="sms")
    assert msg.raw_location == "Cape Town"


def test_parse_with_iso_date():
    msg = parse_body("2011-05-19 14:05 Dodoma", identifier="x@y.com", source="email")
    assert msg.raw_location == "Dodoma"
    assert msg.observed_at.year == 2011
    assert msg.observed_at.tzinfo is not None
    assert msg.observed_at.tzinfo.utcoffset(msg.observed_at) == UTC.utcoffset(msg.observed_at)


def test_parse_identifier_lowercased():
    msg = parse_body("Delhi", identifier="  Nick@Dimagi.com ", source="form")
    assert msg.identifier == "nick@dimagi.com"
