import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from studio.utils.entropy_math import SemanticEntropyCalculator, VertexFlashJudge

class MockJudge:
    def __init__(self, samples=None, entailment_map=None):
        self.samples = samples or []
        self.entailment_map = entailment_map or {}

    async def generate_samples(self, prompt: str, n: int, temperature: float = 0.7):
        if self.samples:
            return (self.samples * (n // len(self.samples) + 1))[:n]
        return [f"Sample {i}" for i in range(n)]

    async def check_entailment(self, text_a: str, text_b: str, context: str) -> bool:
        if (text_a, text_b) in self.entailment_map:
            return self.entailment_map[(text_a, text_b)]
        if (text_b, text_a) in self.entailment_map:
            return self.entailment_map[(text_b, text_a)]
        return text_a == text_b

@pytest.mark.asyncio
async def test_perfect_consistency():
    judge = MockJudge(samples=["The answer is 42."])
    calculator = SemanticEntropyCalculator(judge)
    metric = await calculator.measure_uncertainty("What is the answer?", "General Knowledge")
    assert metric.entropy_score == 0.0
    assert not metric.is_tunneling

@pytest.mark.asyncio
async def test_high_uncertainty_no_longer_trips_at_2_32():
    # All samples are different and not entailed -> 5 clusters -> log2(5) approx 2.32
    samples = ["A", "B", "C", "D", "E"]
    judge = MockJudge(samples=samples)
    calculator = SemanticEntropyCalculator(judge)
    metric = await calculator.measure_uncertainty("Prompt", "Intent")
    assert 2.3 <= metric.entropy_score <= 2.33
    assert not metric.is_tunneling, "SE 2.32 should NOT trip with threshold 7.0"

@pytest.mark.asyncio
async def test_entropy_threshold_calibration():
    """
    TDD Test for SE Threshold Calibration.
    Requirement: SE = 2.32 (max for N=5) should NOT trip.
    Requirement: SE = 7.5 should TRIP.
    """
    mock_judge = AsyncMock()
    mock_judge.generate_samples.return_value = ["A", "B", "C", "D", "E"]
    calculator = SemanticEntropyCalculator(mock_judge)

    # Case 1: SE = 2.32 (Expected NOT to trip)
    with patch.object(SemanticEntropyCalculator, '_compute_shannon_entropy', return_value=(2.32, {"dist": 1.0})):
        metric = await calculator.measure_uncertainty("test prompt", "test intent")
        assert metric.entropy_score == 2.32
        assert not metric.is_tunneling

    # Case 2: SE = 7.5 (Expected TO TRIP)
    with patch.object(SemanticEntropyCalculator, '_compute_shannon_entropy', return_value=(7.5, {"dist": 1.0})):
        metric = await calculator.measure_uncertainty("test prompt", "test intent")
        assert metric.entropy_score == 7.5
        assert metric.is_tunneling is True

@pytest.mark.asyncio
async def test_empty_samples_always_trips():
    judge = AsyncMock()
    judge.generate_samples.return_value = []
    calculator = SemanticEntropyCalculator(judge)
    metric = await calculator.measure_uncertainty("Prompt", "Intent")
    assert metric.is_tunneling is True

@pytest.mark.asyncio
async def test_clustering_logic():
    # A and B are same meaning. C is different.
    # Samples: A, A, B, C, C
    # Expected: Cluster 1 {A, A, B}, Cluster 2 {C, C}
    # Entropy: P(1)=0.6, P(2)=0.4
    # H = -(0.6*log2(0.6) + 0.4*log2(0.4)) = -(-0.442 + -0.528) = 0.97
    samples = ["Answer A", "Answer A", "Answer B", "Answer C", "Answer C"]
    entailment_map = {
        ("Answer A", "Answer B"): True,
        ("Answer B", "Answer A"): True
    }
    judge = MockJudge(samples=samples, entailment_map=entailment_map)
    calculator = SemanticEntropyCalculator(judge)
    metric = await calculator.measure_uncertainty("Prompt", "Intent")
    assert 0.9 < metric.entropy_score < 1.0
    assert not metric.is_tunneling
    assert len(metric.cluster_distribution) == 2

@pytest.mark.asyncio
async def test_vertex_flash_judge():
    # Mock the GenerativeModel
    mock_model = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = "Generated Text"
    mock_model.generate_content_async.return_value = mock_response

    judge = VertexFlashJudge(mock_model)

    # Test generate_samples
    samples = await judge.generate_samples("Prompt", n=2)
    assert len(samples) == 2
    assert samples[0] == "Generated Text"
    assert mock_model.generate_content_async.call_count == 2

    # Test check_entailment
    mock_response.text = "TRUE"
    mock_model.generate_content_async.return_value = mock_response

    result = await judge.check_entailment("A", "B", "Context")
    assert result is True

    mock_response.text = "FALSE"
    result = await judge.check_entailment("A", "B", "Context")
    assert result is False
