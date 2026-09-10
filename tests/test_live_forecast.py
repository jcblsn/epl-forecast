from epl_forecast.live_forecast import flatten_rows


def test_flatten_rows_removes_optional_nested_fields_from_every_row():
    rows, fields = flatten_rows(
        [
            {"match_id": "a", "probabilities": {"home": 0.5}, "price": 2},
            {"match_id": "b", "probabilities": None, "price": None},
        ]
    )
    assert fields == ["match_id", "price"]
    assert rows == [{"match_id": "a", "price": 2}, {"match_id": "b", "price": None}]
