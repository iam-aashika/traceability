import pytest
import json
from app.schemas.generation import TestCase, TestCaseCollection
from app.services.llm_service import LLMService

def test_valid_test_case_validation():
    valid_tc_data = {
        "test_case_id": "TC-001",
        "title": "Verify Overpressure Valve Venting at 299 mmHg",
        "objective": "Ensure emergency deflation valve opens when cuff pressure reaches 299 mmHg.",
        "preconditions": ["Pneumatic test bench connected to monitor"],
        "test_steps": ["Start measurement", "Ramp pressure to 300 mmHg", "Measure vent time"],
        "expected_result": "Valve vents cuff within 2 seconds.",
        "priority": "Critical",
        "test_type": "Safety",
        "source_node_ids": ["node_test_4_1"],
        "source_requirements": ["If cuff pressure exceeds 299 mmHg... immediately triggers emergency deflation valve"],
        "source_content_hashes": ["hash123"],
        "assumptions": ["Standard test chamber volume"]
    }
    tc = TestCase.model_validate(valid_tc_data)
    assert tc.test_case_id == "TC-001"
    assert tc.priority == "Critical"
    assert tc.test_type == "Safety"

def test_pydantic_rejects_missing_required_fields():
    # Missing expected_result and test_steps
    invalid_tc_data = {
        "test_case_id": "TC-002",
        "title": "Incomplete Test Case",
        "objective": "Missing essential fields",
        "priority": "High",
        "test_type": "Functional",
        "source_node_ids": ["node_1"],
        "source_requirements": ["Req text"]
    }
    with pytest.raises(ValueError):
        TestCase.model_validate(invalid_tc_data)

def test_pydantic_rejects_invalid_priority():
    invalid_data = {
        "test_case_id": "TC-003",
        "title": "Invalid Priority Test",
        "objective": "Verifies that invalid priorities trigger error",
        "test_steps": ["Execute step"],
        "expected_result": "Passes",
        "priority": "SuperUrgent",  # Invalid
        "test_type": "Functional",
        "source_node_ids": ["n1"],
        "source_requirements": ["r1"]
    }
    with pytest.raises(ValueError) as exc:
        TestCase.model_validate(invalid_data)
    assert "Priority must be one of" in str(exc.value)

def test_pydantic_enforces_count_constraints():
    sample_tc = {
        "test_case_id": "TC-001",
        "title": "Sample Valid Test",
        "objective": "Validate constraint enforcement",
        "test_steps": ["Step 1"],
        "expected_result": "Success outcome",
        "priority": "High",
        "test_type": "Functional",
        "source_node_ids": ["node_1"],
        "source_requirements": ["Req text"]
    }
    # 2 test cases (below minimum of 3)
    with pytest.raises(ValueError):
        TestCaseCollection.model_validate({"test_cases": [sample_tc, sample_tc]})

    # 6 test cases (above maximum of 5)
    with pytest.raises(ValueError):
        TestCaseCollection.model_validate({"test_cases": [sample_tc] * 6})

def test_json_extractor_handles_code_fences():
    text_with_fences = """Here are the test cases:
```json
{
  "test_cases": [
    {
      "test_case_id": "TC-001",
      "title": "Sample Valid Test",
      "objective": "Validate markdown parsing",
      "test_steps": ["Step 1"],
      "expected_result": "Success outcome",
      "priority": "High",
      "test_type": "Functional",
      "source_node_ids": ["node_1"],
      "source_requirements": ["Req text"]
    },
    {
      "test_case_id": "TC-002",
      "title": "Sample Valid Test 2",
      "objective": "Validate markdown parsing 2",
      "test_steps": ["Step 1"],
      "expected_result": "Success outcome",
      "priority": "High",
      "test_type": "Functional",
      "source_node_ids": ["node_1"],
      "source_requirements": ["Req text"]
    },
    {
      "test_case_id": "TC-003",
      "title": "Sample Valid Test 3",
      "objective": "Validate markdown parsing 3",
      "test_steps": ["Step 1"],
      "expected_result": "Success outcome",
      "priority": "High",
      "test_type": "Functional",
      "source_node_ids": ["node_1"],
      "source_requirements": ["Req text"]
    }
  ]
}
```
Hope this helps!"""
    res = LLMService._extract_json(text_with_fences)
    assert "test_cases" in res
    assert len(res["test_cases"]) == 3

def test_mock_llm_generation_grounding():
    snapshot = {
        "node_v1_3_2": {
            "section_number": "3.2",
            "heading": "Cuff Inflation Sequence",
            "body_text": "The device inflates the cuff to an initial target of 180 mmHg in 40 mmHg increments up to a maximum of 299 mmHg.",
            "content_hash": "hash_3_2"
        }
    }
    cases = LLMService.generate_test_cases(snapshot, provider="mock")
    assert 3 <= len(cases) <= 5
    assert all(isinstance(tc, TestCase) for tc in cases)
    # Check that increment from text was reflected
    assert any("40" in tc.title or "40" in tc.objective for tc in cases)
