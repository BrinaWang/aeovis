# Gap Detection: Types, Thresholds, and Priority Scoring

Exact rules ported from the aeovis platform (`aeo_eval/gaps/`). Apply them as written — do not invent different thresholds.

## Gap Taxonomy (six types)

| Type | Meaning |
|---|---|
| **visibility** | Striim's mention rate on a topic is below threshold, or a competitor's is more than 2x Striim's |
| **citation** | Competitor pages are cited on a topic while Striim pages are not |
| **content** | No Striim page exists that answers the evaluated questions (root-cause of visibility/citation gaps) |
| **technical** | Striim pages exist but AI crawlers can't access or extract them (robots.txt, 403s, JS-rendered content, noindex) |
| **third-party authority** | Striim is absent from the off-site sources (listicles, comparisons, Reddit, G2) the engines cite |
| **agent-experience** | Missing agent-context artifacts (llms.txt, structured data) that help AI systems parse the site |

The platform automates visibility and citation detection; the other four are diagnosed qualitatively from evidence.

## Visibility Gap Rules

Flag a visibility gap for a topic when **either**:

1. Striim's mention rate is below the topic-priority threshold:
   - High-priority topic: mention rate < **15%**
   - Medium-priority topic: < **5%**
   - Low-priority topic: < **2%**
2. The top competitor's mention rate is more than **2x** Striim's (when both are > 0).

Topic priority = the highest priority among the topic's questions (see `data/questions.json`); default Medium.

**Minimum sample:** skip topics with fewer than 3 responses — too few to flag.

## Citation Gap Rules

Flag a citation gap for a topic when the topic has **≥ 3 competitor-owned citations and zero Striim-owned citations** in the evaluated answers. Priority and confidence are "high" when competitor citations > 5, else "medium".

## Gap Priority Scoring

```
gap_ratio = (competitor_visibility − striim_visibility) / max(striim_visibility, 0.01)
```

- gap_ratio > 3.0 → **high**
- gap_ratio > 1.5 → **medium**
- otherwise → **low**

## Confidence Scoring

Based on number of responses behind the metric:

- ≥ 10 responses → **high**
- 5–9 → **medium**
- < 5 → **low**

Always report confidence with the gap. A 0% visibility figure from one or two answers is a real signal of *direction* but low-confidence in *magnitude* — say so explicitly (see the gold example in recommendations.md, which does exactly this).

## Metrics Definitions (from `aeo_eval/metrics/calculator.py`)

Computed over all evaluated responses in a run:

- **mention_rate** — share of responses where Striim is mentioned at all
- **recommendation_rate** — share where Striim is affirmatively recommended
- **top3_rate** — share where Striim appears in the first three brands listed
- **avg_position** — Striim's average position among brands listed
- **citation_rate** — share of responses citing at least one striim.com URL
- **competitor_mention_rates** — per-competitor mention counts / total responses (share of voice)

A brand is "mentioned" when it appears in the answer text; position = order of first appearance among brands.
