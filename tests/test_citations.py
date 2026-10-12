from app.citations import cited_ids_in, renumber, split_claims, validate_answer


def test_valid_answer_passes():
    answer = "The pump motor is covered for 5 years [2]. Labor is covered for 2 years [1][3]."
    result = validate_answer(answer, num_blocks=6)
    assert result.ok
    assert result.cited_ids == [2, 1, 3]


def test_citation_after_period_counts_for_that_sentence():
    assert validate_answer("Returns take 30 days. [1] Pickup costs $49. [2]", 6).ok


def test_unknown_citation_id_fails():
    result = validate_answer("Returns take 30 days [7].", num_blocks=6)
    assert not result.ok
    assert result.invalid_ids == [7]


def test_zero_is_invalid():
    assert validate_answer("Yes [0].", 6).invalid_ids == [0]


def test_uncited_sentence_fails():
    result = validate_answer("Returns take 30 days [1]. You will love it here.", 6)
    assert not result.ok
    assert result.uncited_claims == ["You will love it here."]


def test_uncited_list_item_fails():
    answer = "Follow these steps:\n1. Open Orders [1].\n2. Choose Start a warranty claim."
    result = validate_answer(answer, 6)
    assert result.uncited_claims == ["Choose Start a warranty claim."]


def test_lead_in_line_and_code_block_are_not_claims():
    answer = "Create the app like this [1]:\n\n```python\napp = FastAPI()\n```\n\nThen run it [2]."
    assert split_claims(answer) == ["Create the app like this [1]:", "Then run it [2]."]
    assert validate_answer(answer, 6).ok


def test_answer_without_citations_fails():
    result = validate_answer("Returns take 30 days.", 6)
    assert not result.ok
    assert "no citations" in result.describe()


def test_grouped_citations_are_parsed():
    assert cited_ids_in("A [1, 3]. B [2].") == [1, 3, 2]


def test_renumber_in_order_of_appearance():
    text, mapping = renumber("A [4]. B [2, 4]. C [2][4].", [4, 2])
    assert mapping == {4: 1, 2: 2}
    assert text == "A [1]. B [2][1]. C [2][1]."


def test_code_fence_inside_list_item_is_not_a_claim():
    answer = (
        "Override the dependency in your tests [1]:\n"
        "1. Set the override [3]: ```python\n"
        "   app.dependency_overrides[common_parameters] = override_dependency\n"
        "   ```\n"
        "2. Reset it when you are done [3]:\n"
        "    ```python\n"
        "    app.dependency_overrides = {}\n"
        "    ```"
    )
    result = validate_answer(answer, 6)
    assert result.uncited_claims == []
    assert result.ok


def test_unclosed_fence_hides_the_rest_rather_than_flagging_code():
    assert validate_answer("Use this [1]:\n```python\nx = 1", 6).ok
