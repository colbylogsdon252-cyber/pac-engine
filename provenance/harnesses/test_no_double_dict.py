from pac_engine_v1_interface import evaluate_payload

def test_no_double_dict_serialization():
    sample_payload = {
        "signal_id": "TEST-BOUNDARY",
        "evidence": [],
        "threshold": "L1"
    }

    try:
        result = evaluate_payload(sample_payload)
        assert isinstance(result, dict)
    except Exception as e:
        assert False, f"Boundary violation detected: {e}"