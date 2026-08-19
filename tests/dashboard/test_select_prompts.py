"""Dashboard prompt selection: attribute access, filter-then-limit."""
from aeo_eval.dashboard.app import select_prompts
from aeo_eval.models.prompt import Prompt


def make_prompts():
    return [
        Prompt(id=f"p{i}", prompt="q", topic=topic, persona="x",
               intent="y", priority=priority)
        for i, (topic, priority) in enumerate([
            ("Oracle CDC", "high"),
            ("Oracle CDC", "medium"),
            ("Data Replication", "high"),
            ("Data Replication", "low"),
        ])
    ]


def test_topic_filter_uses_dataclass_attributes():
    selected = select_prompts(make_prompts(), topic="Oracle CDC")
    assert [p.id for p in selected] == ["p0", "p1"]


def test_priority_filter():
    selected = select_prompts(make_prompts(), priority="high")
    assert [p.id for p in selected] == ["p0", "p2"]


def test_limit_applies_after_filtering():
    selected = select_prompts(make_prompts(), topic="Data Replication", limit=1)
    assert [p.id for p in selected] == ["p2"]


def test_no_filters_returns_all():
    assert len(select_prompts(make_prompts())) == 4
