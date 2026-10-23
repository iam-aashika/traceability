from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional
from datetime import datetime

class TestCase(BaseModel):
    test_case_id: str = Field(..., description="Unique test case identifier e.g. TC-001")
    title: str = Field(..., min_length=5, description="Clear, descriptive title")
    objective: str = Field(..., min_length=10, description="Testing objective")
    preconditions: List[str] = Field(default_factory=list, description="Preconditions required before test execution")
    test_steps: List[str] = Field(..., min_length=1, description="Sequential, actionable steps to execute the check")
    expected_result: str = Field(..., min_length=5, description="Expected device behavior and display output")
    priority: str = Field(..., description="Priority: Critical, High, Medium, or Low")
    test_type: str = Field(..., description="Functional, Boundary, Safety, Negative, or Error-Handling")
    source_node_ids: List[str] = Field(..., min_length=1, description="Referenced node IDs")
    source_requirements: List[str] = Field(..., min_length=1, description="Specific requirement sentences or sections")
    source_content_hashes: List[str] = Field(default_factory=list, description="Content hashes of referenced nodes")
    assumptions: List[str] = Field(default_factory=list, description="Explicit assumptions or test constraints")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        valid = {"Critical", "High", "Medium", "Low"}
        if v.capitalize() not in valid:
            raise ValueError(f"Priority must be one of {valid}, got {v}")
        return v.capitalize()

    @field_validator("test_type")
    @classmethod
    def validate_test_type(cls, v: str) -> str:
        valid = {"Functional", "Boundary", "Safety", "Negative", "Error-Handling", "Error Handling"}
        if v not in valid and v.capitalize() not in valid:
            # Normalize to valid category
            return v.capitalize()
        return v

class TestCaseCollection(BaseModel):
    test_cases: List[TestCase] = Field(..., min_length=3, max_length=5, description="Between 3 and 5 test cases")

    @model_validator(mode="after")
    def validate_test_cases_count(self):
        count = len(self.test_cases)
        if count < 3 or count > 5:
            raise ValueError(f"Test case count must be between 3 and 5, got {count}")
        return self

class GenerationMetadata(BaseModel):
    generation_id: str
    selection_id: str
    selection_name: str
    document_id: str
    version_id: str
    version_label: str
    created_at: datetime
    llm_provider: str
    model_name: str
    prompt_version: str = "v1.0"
    source_node_ids: List[str]
    logical_node_ids: List[str]
    source_content_hashes: Dict[str, str]

class GenerationResponse(BaseModel):
    generation_id: str
    selection_id: str
    selection_name: str
    document_id: str
    version_id: str
    version_label: str
    created_at: datetime
    llm_provider: str
    model_name: str
    prompt_version: str
    source_node_ids: List[str]
    logical_node_ids: List[str]
    source_content_hashes: Dict[str, str]
    test_cases: List[TestCase]
    was_cached: bool = False

class NodeStalenessDetail(BaseModel):
    node_id: str
    logical_node_id: str
    heading: str
    original_version: str
    original_hash: str
    current_version: Optional[str] = None
    current_hash: Optional[str] = None
    staleness_status: str  # CURRENT, STALE, SOURCE_REMOVED, REVIEW_REQUIRED
    change_category: str   # NONE, NUMERICAL_THRESHOLD, ERROR_CODE, SAFETY_BEHAVIOR, TEXT_MODIFIED, DELETED
    reason: str
    human_review_recommendation: str
    diff_text: Optional[str] = None

class TestTraceabilityResponse(BaseModel):
    generation_id: str
    selection_id: str
    selection_name: str
    document_id: str
    original_version: str
    latest_document_version: str
    overall_staleness_status: str  # CURRENT, STALE, SOURCE_REMOVED, REVIEW_REQUIRED
    has_stale_requirements: bool
    summary_reason: str
    human_review_recommendation: str
    node_staleness_details: List[NodeStalenessDetail]
    test_cases: List[TestCase]
    source_snapshot: Dict[str, Any]
