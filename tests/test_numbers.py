from pitchguard.numbers import number_ok, parse_numbers


def test_lakh_and_rupees():
    assert parse_numbers("50 lakh ka cover sirf 549 rupaye") == [5_000_000, 549]


def test_hindi_words_with_units():
    assert parse_numbers("pachaas lakh") == [5_000_000]
    assert parse_numbers("do hazaar paanch sau rupaye") == [2500]


def test_do_as_verb_is_not_a_number():
    assert parse_numbers("details bhej do") == []


def test_indian_commas_and_decimals():
    assert parse_numbers("₹10,00,000") == [1_000_000]
    assert parse_numbers("97.8 percent") == [97.8]


def test_compound_amount():
    assert parse_numbers("2 lakh 50 hazaar") == [250_000]


def test_devanagari():
    assert parse_numbers("५० लाख रुपये") == [5_000_000]


def test_number_ok_tolerance_and_ranges():
    assert number_ok(98, [97.8], [])                 # rounding is fine
    assert not number_ok(349, [549, 5_000_000, 30], [])
    assert number_ok(500_000, [50_000, 1_000_000], [(50_000, 1_000_000)])
