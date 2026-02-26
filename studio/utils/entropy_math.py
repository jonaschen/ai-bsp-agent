"""
studio/utils/entropy_math.py
----------------------------
The "Sensor" Module for the AI Agent Studio.
Implements the Semantic Entropy (SE) algorithm to detect Cognitive Tunneling.

Algorithm:
1. Sampling: Generate N stochastic responses for a given prompt.
2. Clustering: Group responses by 'Bi-Directional Entailment' (Meaning).
3. Calculation: Compute Shannon Entropy over the clusters.

Reference:
- Report: Implementing AI Agent's "Sensors"
- Metric: SemanticHealthMetric (from memory.py)
"""

import math
import logging
import asyncio
from typing import List, Dict, Tuple, Protocol
# Import strict schema from the Studio Memory
from studio.memory import SemanticHealthMetric

logger = logging.getLogger("studio.utils.entropy_math")

# --- Configuration ---
DEFAULT_SAMPLE_SIZE = 5
ENTROPY_THRESHOLD = 7.0  # If SE > 7.0, uncertainty is too high (Tunneling/Confabulation)
# Note: Threshold depends on N. For N=5, max entropy is log2(5) ~= 2.32.

# --- SECTION 1: The Abstraction (LLM Client) ---

class LLMJudge(Protocol):
    """
    Protocol for the 'Flash Judge'.
    We need an LLM to determine if two strings mean the same thing.
    """
    async def generate_samples(self, prompt: str, n: int, temperature: float = 0.7) -> List[str]:
        """Generate N stochastic completions."""
        ...

    async def check_entailment(self, text_a: str, text_b: str, context: str) -> bool:
        """
        Bi-Directional Entailment Check.
        Returns True if Text A implies Text B AND Text B implies Text A (Semantic Equivalence).
        """
        ...

# --- SECTION 2: The Core Logic (Semantic Entropy) ---

class SemanticEntropyCalculator:
    """
    The Mathematical Sensor.
    Calculates the 'Uncertainty of Meaning' for a given agent task.
    """

    def __init__(self, llm_client: LLMJudge):
        self.llm = llm_client

    async def measure_uncertainty(self, prompt: str, context_intent: str) -> SemanticHealthMetric:
        """
        The Main Public API.
        Executes the full pipeline: Sample -> Cluster -> Calculate.
        """
        logger.info(f"Measuring Semantic Entropy for intent: '{context_intent}'")

        # Step 1: Sampling
        # We generate 5 variations of the answer to see if the agent is consistent.
        samples = await self.llm.generate_samples(prompt, n=DEFAULT_SAMPLE_SIZE)
        if not samples:
            logger.error("Failed to generate samples. Returning high uncertainty.")
            return self._build_metric(0.0, 0, {}, is_tunneling=True)

        # Step 2: Clustering (The Semantic Check)
        clusters = await self._cluster_responses(samples, context_intent)

        # Step 3: Calculation (Shannon Entropy)
        entropy_score, distribution = self._compute_shannon_entropy(clusters, len(samples))

        # Step 4: Diagnosis
        is_tunneling = entropy_score > ENTROPY_THRESHOLD

        if is_tunneling:
            logger.warning(f"Cognitive Tunneling Detected! SE={entropy_score:.2f} > {ENTROPY_THRESHOLD}")

        return self._build_metric(entropy_score, len(samples), distribution, is_tunneling)

    async def _cluster_responses(self, samples: List[str], intent: str) -> List[List[str]]:
        """
        Groups responses into semantic clusters.
        Logic: A greedy clustering algorithm using the LLM as a comparator.
        """
        clusters: List[List[str]] = []

        for sample in samples:
            matched_cluster = False

            # Compare current sample against the representative (first item) of existing clusters
            for cluster in clusters:
                representative = cluster[0]

                # The "Flash Judge" Check
                # Does Sample == Representative (in meaning)?
                is_equivalent = await self.llm.check_entailment(sample, representative, intent)

                if is_equivalent:
                    cluster.append(sample)
                    matched_cluster = True
                    break

            # If no match, start a new semantic cluster
            if not matched_cluster:
                clusters.append([sample])

        return clusters

    def _compute_shannon_entropy(self, clusters: List[List[str]], total_samples: int) -> Tuple[float, Dict[str, float]]:
        """
        Computes H(x) = -sum(p(x) * log(p(x)))
        """
        if total_samples == 0:
            return 0.0, {}

        entropy = 0.0
        distribution = {}

        for i, cluster in enumerate(clusters):
            count = len(cluster)
            probability = count / total_samples

            # Shannon Entropy Formula
            entropy -= probability * math.log2(probability)

            # Log the distribution for debugging (e.g., "Meaning A": 0.6, "Meaning B": 0.4)
            # We use the first 50 chars of the representative as the key
            key = f"Cluster_{i}: {cluster[0][:50]}..."
            distribution[key] = probability

        return entropy, distribution

    def _build_metric(self, score: float, n: int, dist: Dict, is_tunneling: bool) -> SemanticHealthMetric:
        """Helper to construct the strict Pydantic object."""
        return SemanticHealthMetric(
            entropy_score=round(score, 4),
            threshold=ENTROPY_THRESHOLD,
            sample_size=n,
            is_tunneling=is_tunneling,
            cluster_distribution=dist
        )

# --- SECTION 3: Concrete Implementation (Gemini Flash) ---

class VertexFlashJudge:
    """
    Concrete implementation of LLMJudge using Vertex AI (Gemini 1.5 Flash).
    Optimized for speed and cost.
    """
    def __init__(self, vertex_model):
        self.model = vertex_model # e.g., GenerativeModel("gemini-2.5-flash")

    async def generate_samples(self, prompt: str, n: int, temperature: float = 0.7) -> List[str]:
        # Note: In production, use asyncio.gather for parallel calls
        # or the 'candidate_count' parameter if supported.
        tasks = []
        for _ in range(n):
            tasks.append(self.model.generate_content_async(
                prompt,
                generation_config={"temperature": temperature}
            ))

        responses = await asyncio.gather(*tasks)
        return [resp.text for resp in responses]

    async def check_entailment(self, text_a: str, text_b: str, context: str) -> bool:
        """
        Uses a specialized NLI prompt to check meaning.
        """
        nli_prompt = f"""
        You are a Semantic Logic Judge.
        Context/Intent: {context}

        Statement A: "{text_a}"
        Statement B: "{text_b}"

        Task: Do these two statements mean EXACTLY the same thing regarding the intent?
        Ignore minor phrasing differences. Focus on the core logic and facts.

        Answer strictly: TRUE or FALSE.
        """

        response = await self.model.generate_content_async(
            nli_prompt,
            generation_config={"temperature": 0.0} # Deterministic
        )

        clean_resp = response.text.strip().upper()
        return "TRUE" in clean_resp
