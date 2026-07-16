from app.services.parser import evaluate_result, normalize_structured_result, parse_follicle_string


def test_parse_follicle_string_accepts_manual_entry_formats():
    parsed = parse_follicle_string("10x2，12×1、13.5; 15")

    assert parsed == [
        {"size": 15.0, "count": 1},
        {"size": 13.5, "count": 1},
        {"size": 12.0, "count": 1},
        {"size": 10.0, "count": 2},
    ]


def test_parse_follicle_string_accepts_json_array_text():
    parsed = parse_follicle_string('[{"size": "10", "count": 2}, {"size": 12.5}]')

    assert parsed == [
        {"size": 12.5, "count": 1},
        {"size": 10.0, "count": 2},
    ]


def test_normalize_structured_result_recalculates_follicle_totals_from_details():
    structured = {
        "right_follicle_total": 12,
        "left_follicle_total": 1,
        "right_follicles": [
            {"size": 20.1, "count": 1},
            {"size": 15.9, "count": 2},
            {"size": 12.7, "count": 1},
        ],
        "left_follicles": [{"size": 18.2, "count": 1}],
        "uncertain_text": "原始不确定内容",
    }

    normalized = normalize_structured_result(structured)

    assert normalized["right_follicle_total"] == 4
    assert normalized["left_follicle_total"] == 1
    assert "右侧卵泡总数与明细不一致" in normalized["uncertain_text"]


def test_evaluate_result_compares_follicle_details_without_order_sensitivity():
    identified = {
        "right_follicle_total": 2,
        "right_follicles": [
            {"size": 15.9, "count": 1},
            {"size": 20.1, "count": 1},
        ],
    }
    ground_truth = {
        "right_follicle_total": 2,
        "right_follicles": [
            {"size": 20.1, "count": 1},
            {"size": 15.9, "count": 1},
        ],
    }

    evaluation = evaluate_result(identified, ground_truth)

    assert evaluation["fields"]["right_follicles"]["match"] is True


def test_evaluate_result_ignores_remark_for_accuracy():
    identified = {
        "right_follicle_total": 11,
        "left_follicle_total": 8,
        "right_follicles": [{"size": 20.1, "count": 1}],
        "left_follicles": [{"size": 18.2, "count": 1}],
        "endometrium_thickness": 9.5,
        "endometrium_type": "C",
        "right_ovary_length": 60,
        "right_ovary_width": 35,
        "left_ovary_length": 37,
        "left_ovary_width": 30,
        "remark": "已抽血；等抽完血再回来",
    }
    ground_truth = {
        "right_follicle_total": 11,
        "left_follicle_total": 8,
        "right_follicles": [{"size": 20.1, "count": 1}],
        "left_follicles": [{"size": 18.2, "count": 1}],
        "endometrium_thickness": 9.5,
        "endometrium_type": "C",
        "right_ovary_length": 60,
        "right_ovary_width": 35,
        "left_ovary_length": 37,
        "left_ovary_width": 30,
        "remark": "",
    }

    evaluation = evaluate_result(identified, ground_truth)

    assert "remark" not in evaluation["fields"]
    assert evaluation["total_fields"] == 10
    assert evaluation["correct_fields"] == 10
    assert evaluation["accuracy"] == 1.0


def test_evaluate_result_can_include_remark_for_accuracy():
    identified = {
        "right_follicle_total": 11,
        "left_follicle_total": 8,
        "right_follicles": [{"size": 20.1, "count": 1}],
        "left_follicles": [{"size": 18.2, "count": 1}],
        "endometrium_thickness": 9.5,
        "endometrium_type": "C",
        "right_ovary_length": 60,
        "right_ovary_width": 35,
        "left_ovary_length": 37,
        "left_ovary_width": 30,
        "remark": "已抽血；等抽完血再回来",
    }
    ground_truth = {
        "right_follicle_total": 11,
        "left_follicle_total": 8,
        "right_follicles": [{"size": 20.1, "count": 1}],
        "left_follicles": [{"size": 18.2, "count": 1}],
        "endometrium_thickness": 9.5,
        "endometrium_type": "C",
        "right_ovary_length": 60,
        "right_ovary_width": 35,
        "left_ovary_length": 37,
        "left_ovary_width": 30,
        "remark": "",
    }

    evaluation = evaluate_result(identified, ground_truth, include_remark=True)

    assert "remark" in evaluation["fields"]
    assert evaluation["total_fields"] == 11
    assert evaluation["correct_fields"] == 10
    assert evaluation["accuracy"] == 0.9091
