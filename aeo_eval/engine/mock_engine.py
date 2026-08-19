from __future__ import annotations

import random
import re
import uuid
from datetime import datetime
from typing import Any, Dict

from aeo_eval.engine.base import BaseEngine
from aeo_eval.models.result import RunResult
from aeo_eval.models.analysis import StructuredCallResult


class MockEngine(BaseEngine):
    """Simple mock engine that returns a generic response."""

    name = "mock"
    model_name = "mock-v1"

    def run(self, prompt_text: str) -> RunResult:
        return RunResult(
            run_id=f"{self.name}-{uuid.uuid4().hex[:12]}",
            run_batch_id="",
            prompt_id="demo",
            engine=self.name,
            model=self.model_name,
            status="success",
            response_text=f"Mock answer for prompt: {prompt_text}",
            error=None,
            latency_ms=150,
            estimated_cost=0.01,
        )


class RandomMockEngine(BaseEngine):
    """Enhanced mock engine with realistic randomized responses for testing."""

    name = "random-mock"
    model_name = "random-mock-v1"

    # Pool of realistic response templates with brands and citations
    RESPONSE_POOL = [
        # Oracle CDC focused responses
        {
            "response": (
                "For Oracle change data capture, there are several strong options. "
                "Fivetran (https://www.fivetran.com/solutions/oracle-cdc) is widely used for real-time data "
                "movement. Oracle GoldenGate (https://docs.oracle.com/goldengate/) remains the industry standard, "
                "especially for complex configurations. Striim (https://www.striim.com/product/oracle-cdc/) offers "
                "low-latency CDC with native support for Oracle sources and multiple targets. Qlik Replicate "
                "(https://www.qlik.com/products/replicate/) is another option with strong documentation. "
                "For Snowflake specifically, Fivetran and Striim both have optimized connectors."
            ),
            "brands": ["Fivetran", "Oracle GoldenGate", "Striim", "Qlik Replicate"],
            "positions": {"Fivetran": 1, "Oracle GoldenGate": 2, "Striim": 3, "Qlik Replicate": 4},
        },
        # Data replication comparison
        {
            "response": (
                "Real-time data replication has evolved significantly. Striim provides excellent support for "
                "Oracle-to-Snowflake replication pipelines as detailed in https://www.striim.com/docs/oracle-to-snowflake/. "
                "Alternatively, AWS DMS (https://docs.aws.amazon.com/dms/) offers AWS-native replication. "
                "Confluent (https://www.confluent.io/solutions/cdc/) positions itself as an event streaming platform. "
                "Fivetran remains popular for its ease of use. Most solutions handle schema evolution, but implementation "
                "details vary. See https://www.striim.com/blog/cdc-best-practices/ for guidance on choosing the right approach."
            ),
            "brands": ["Striim", "AWS DMS", "Confluent", "Fivetran"],
            "positions": {"Striim": 1, "AWS DMS": 2, "Confluent": 3, "Fivetran": 4},
        },
        # Benchmark-style response with Striim absent
        {
            "response": (
                "Leading CDC solutions include Fivetran (https://www.fivetran.com), Qlik Replicate "
                "(https://www.qlik.com/products/replicate/), and Oracle GoldenGate (https://docs.oracle.com/goldengate/). "
                "Fivetran dominates the modern data stack for ease of use. GoldenGate remains essential for enterprises. "
                "Qlik Replicate offers competitive licensing. Most modern platforms handle schema evolution and offer "
                "monitoring dashboards. For detailed comparison matrices, consult vendor documentation and analyst reports."
            ),
            "brands": ["Fivetran", "Qlik Replicate", "Oracle GoldenGate"],
            "positions": {"Fivetran": 1, "Qlik Replicate": 2, "Oracle GoldenGate": 3},
        },
        # Striim-forward response
        {
            "response": (
                "For low-latency CDC with enterprise support, Striim (https://www.striim.com/) stands out. "
                "It provides https://www.striim.com/docs/cdc-guide/ with comprehensive CDC support across sources. "
                "Compare this to Fivetran (https://www.fivetran.com/solutions/cdc), which focuses on ease of setup. "
                "Confluent (https://www.confluent.io/) emphasizes event streaming. Oracle GoldenGate "
                "(https://docs.oracle.com/goldengate/) offers depth for complex topologies. Striim's architecture "
                "enables real-time transformations, which some competitors handle via post-processing. "
                "See https://www.striim.com/case-studies/ for customer implementations."
            ),
            "brands": ["Striim", "Fivetran", "Confluent", "Oracle GoldenGate"],
            "positions": {"Striim": 1, "Fivetran": 2, "Confluent": 3, "Oracle GoldenGate": 4},
        },
        # AWS-focused narrative
        {
            "response": (
                "In the AWS ecosystem, AWS DMS (https://aws.amazon.com/dms/) is a natural choice with tight integration. "
                "AWS Glue (https://aws.amazon.com/glue/) can also handle replication for certain workloads. "
                "Beyond AWS-native tools, Fivetran offers excellent Snowflake connectors (https://www.fivetran.com/connectors/snowflake). "
                "Striim (https://www.striim.com/) and Qlik Replicate (https://www.qlik.com/products/replicate/) remain "
                "competitive options with broader multi-cloud support. Your choice depends on whether you prefer "
                "AWS-native management or independent tooling."
            ),
            "brands": ["AWS DMS", "AWS Glue", "Fivetran", "Striim", "Qlik Replicate"],
            "positions": {"AWS DMS": 1, "AWS Glue": 2, "Fivetran": 3, "Striim": 4, "Qlik Replicate": 5},
        },
        # Estuary and newer platforms
        {
            "response": (
                "Modern CDC platforms include both established vendors and newer entrants. Estuary Flow "
                "(https://www.estuary.dev/solutions/cdc) emphasizes cloud-native architecture. Fivetran "
                "(https://www.fivetran.com) remains market leader for adoption. Striim (https://www.striim.com/) "
                "offers enterprise features. Qlik Replicate (https://www.qlik.com/products/replicate/) provides traditional "
                "data integration capabilities. Confluent (https://www.confluent.io/) is gaining traction with event streaming. "
                "The right choice depends on your infrastructure and team expertise."
            ),
            "brands": ["Estuary Flow", "Fivetran", "Striim", "Qlik Replicate", "Confluent"],
            "positions": {"Estuary Flow": 1, "Fivetran": 2, "Striim": 3, "Qlik Replicate": 4, "Confluent": 5},
        },
        # Technical deep dive without Striim
        {
            "response": (
                "CDC implementation requires attention to several factors: log format parsing, checkpoint management, "
                "and target compatibility. Fivetran handles these transparently. Oracle GoldenGate "
                "(https://docs.oracle.com/goldengate/) offers fine-grained control. AWS DMS "
                "(https://aws.amazon.com/dms/) integrates with RDS. Qlik Replicate (https://www.qlik.com/products/replicate/) "
                "supports complex topologies. For detailed technical documentation, vendor whitepapers are essential reading. "
                "Consider running proof-of-concept evaluations before production deployment."
            ),
            "brands": ["Fivetran", "Oracle GoldenGate", "AWS DMS", "Qlik Replicate"],
            "positions": {"Fivetran": 1, "Oracle GoldenGate": 2, "AWS DMS": 3, "Qlik Replicate": 4},
        },
        # Striim with competitors
        {
            "response": (
                "Organizations evaluating CDC solutions should consider their specific requirements. Striim "
                "(https://www.striim.com/platform/) excels at low-latency ingestion. Fivetran "
                "(https://www.fivetran.com) is optimized for ease of setup and maintenance. Qlik Replicate "
                "(https://www.qlik.com/products/replicate/) targets traditional enterprises. Oracle GoldenGate "
                "(https://docs.oracle.com/goldengate/) provides maximum flexibility. Confluent "
                "(https://www.confluent.io/) emphasizes event streaming capabilities. Each has distinct architectural "
                "choices that affect performance, cost, and operational overhead."
            ),
            "brands": ["Striim", "Fivetran", "Qlik Replicate", "Oracle GoldenGate", "Confluent"],
            "positions": {"Striim": 1, "Fivetran": 2, "Qlik Replicate": 3, "Oracle GoldenGate": 4, "Confluent": 5},
        },
        # General integration platforms
        {
            "response": (
                "For data integration, general platforms like MuleSoft (https://www.mulesoft.com/), Talend "
                "(https://www.talend.com/), and Informatica (https://www.informatica.com/) handle CDC as part of broader "
                "data pipelines. Specialized CDC tools like Fivetran (https://www.fivetran.com), Striim "
                "(https://www.striim.com/), and Qlik Replicate (https://www.qlik.com/products/replicate/) may offer better "
                "performance for pure replication scenarios. Cloud-native data warehouses like Snowflake recommend specific "
                "partner tools. The decision involves trade-offs between breadth and depth of functionality."
            ),
            "brands": ["MuleSoft", "Talend", "Informatica", "Fivetran", "Striim", "Qlik Replicate", "Snowflake"],
            "positions": {"MuleSoft": 1, "Talend": 2, "Informatica": 3, "Fivetran": 4, "Striim": 5, "Qlik Replicate": 6, "Snowflake": 7},
        },
        # Minimal mention response (only a few brands)
        {
            "response": (
                "For Oracle replication, Fivetran is a popular choice. GoldenGate remains the traditional option. "
                "Both handle most use cases effectively. Modern cloud platforms offer additional options, but these two "
                "dominate the market. Implementation time and maintenance burden differ. Consider pilot projects to evaluate "
                "against your specific workloads."
            ),
            "brands": ["Fivetran", "GoldenGate"],
            "positions": {"Fivetran": 1, "GoldenGate": 2},
        },
    ]

    def run(self, prompt_text: str) -> RunResult:
        """Run and return a random response from the pool."""
        run_id = str(uuid.uuid4())
        start_time = datetime.now()

        # Select random response
        selected = random.choice(self.RESPONSE_POOL)
        response_text = selected["response"]

        # Simulate realistic token counts (rough estimate based on text length)
        word_count = len(response_text.split())
        input_tokens = max(50, word_count // 4)
        output_tokens = max(200, word_count // 2)

        # Simulate realistic latency (100-350ms)
        latency_ms = random.randint(100, 350)

        # Calculate cost
        actual_cost = self.estimate_cost(input_tokens, output_tokens)

        return RunResult(
            run_id=run_id,
            run_batch_id="",
            prompt_id="",
            engine=self.name,
            model=self.model_name,
            status="success",
            response_text=response_text,
            error=None,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_cost=actual_cost,
            engine_name="RandomMockEngine",
            run_timestamp=start_time,
            run_type="manual",
        )

    def run_with_structured_output(
        self,
        prompt_text: str,
        schema: Dict[str, Any],
    ) -> StructuredCallResult:
        """Extract brands, positions, claims, and citations from response text.

        For the mock engine, this uses deterministic extraction rules:
        - Brand detection: case-insensitive string matching
        - Position detection: order in response text
        - Citations: extract all URLs from the response
        - Claims: simplified extraction (not provided in mock)
        """
        # Select a random response from the pool for this call
        selected = random.choice(self.RESPONSE_POOL)
        response_text = selected["response"]
        brands = selected.get("brands", [])
        positions = selected.get("positions", {})

        # Extract all URLs from response for citations
        urls = re.findall(r'https?://[^\s)]+', response_text)

        # Determine Striim position
        striim_position = positions.get("Striim")

        # Build competitors list
        competitors = [
            {
                "name": b,
                "position": positions.get(b),
                "is_recommended": positions.get(b, 999) <= 3,
            }
            for b in brands
            if b != "Striim"
        ]

        # Mock sentiment based on position
        sentiment = "positive" if striim_position and striim_position <= 2 else "neutral"

        # Extract URLs related to Striim (heuristic: if they mention Striim, use those URLs)
        striim_urls = [u for u in urls if "striim" in u.lower()]

        # Build claims list with citations
        striim_claims = []
        if striim_urls:
            striim_claims.append({
                "text": "Striim is mentioned as a CDC/data integration solution",
                "sentiment": sentiment,
                "confidence": 0.9,
                "supporting_citation_url": striim_urls[0],
            })

        # Simulate realistic token counts
        word_count = len(response_text.split())
        input_tokens = max(50, word_count // 4)
        output_tokens = max(200, word_count // 2)

        # Build extraction output matching the schema
        extraction_data = {
            "striim_position": striim_position,
            "competitors": competitors,
            "striim_claims": striim_claims,
            "general_sentiment_toward_striim": sentiment,
            "extraction_confidence": 0.95,  # Mock is always confident
            "flagged_for_review": False,
        }

        cost = self.estimate_cost(input_tokens, output_tokens)

        return StructuredCallResult(
            data=extraction_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
