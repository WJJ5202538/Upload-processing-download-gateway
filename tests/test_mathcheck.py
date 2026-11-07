from docmark.services.mathcheck import find_math_issues


def messages(text: str) -> list[str]:
    return [issue.message for issue in find_math_issues(text)]


def test_finds_wrong_calculation_and_keeps_original_equation() -> None:
    assert messages("计算：3 × 4 = 13。") == [
        "# 计算有误：3 × 4 = 13，正确结果应为 12。"
    ]


def test_ignores_correct_calculations() -> None:
    assert find_math_issues("2 + 2 = 4，0.1 + 0.2 = 0.3，10 ÷ 2 = 5") == []


def test_understands_full_width_operators_and_negative_result() -> None:
    assert messages("（1＋2）×3＝8")[0].startswith("# 计算有误")
    assert messages("5 - 8 = 2")[0].endswith("正确结果应为 −3。")


def test_division_by_zero_is_not_reported_as_a_wrong_result() -> None:
    assert find_math_issues("5 ÷ 0 = 0") == []


def test_does_not_match_part_of_a_larger_number() -> None:
    assert find_math_issues("1,000 + 2 = 1002") == []


def test_deduplicates_repeated_mistake_in_same_paragraph() -> None:
    assert len(find_math_issues("3 + 4 = 8；再次 3 + 4 = 8")) == 1
