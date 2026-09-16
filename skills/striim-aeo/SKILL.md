---
name: striim-aeo
description: Use when analyzing or improving Striim's visibility in AI-generated answers (AEO / answer engine optimization) — how Striim appears vs. competitors in ChatGPT, Claude, Perplexity, or Gemini answers; finding visibility or citation gaps; or writing AEO recommendations, content briefs, or measurement plans for Striim.
---

# Striim AEO Analysis

Portable version of Striim's aeovis evaluation platform. The curated question panel, gap thresholds, and recommendation contract are **fixed inputs in this skill's files** — never invent your own questions, competitor list, thresholds, or recommendation format.

This is an analyst-mode approximation of the real platform (which runs 240 evals/run with multi-provider APIs, cost tracking, and SQLite persistence). Label results accordingly: web-searched answers are "live samples"; answers from your own knowledge are "directional estimates".

## Workflow

1. **Load the fixed inputs** (all paths relative to this skill's directory):
   - `data/questions.json` — the 75-question buyer panel with topic, persona, intent, priority. Evaluate only these (all, one topic, or a sample; keep ≥3 per topic reported, since fewer can't flag a gap).
   - `data/brand.md` — configured competitor set, important Striim pages, crawler list.
   - `data/personas.json` — full persona profiles, for interpreting question intent.
2. **Answer each question as an answer engine would.** Use web search per question when available; otherwise answer from knowledge and say so. For each answer, extract: brands in order of first appearance, Striim mentioned (yes/no), Striim affirmatively recommended (yes/no), Striim's position, URLs cited.
3. **Compute metrics per topic and overall** using the definitions in `references/gap-detection.md`: mention_rate, recommendation_rate, top3_rate, avg_position, citation_rate, competitor share of voice.
4. **Detect gaps** by applying the thresholds in `references/gap-detection.md` exactly (15%/5%/2% by topic priority, 2x competitor multiplier, ≥3-competitor-citations rule). Score each gap's priority with the gap_ratio formula and its confidence by sample size, and report both.
5. **Generate recommendations** for the top gaps following `references/recommendations.md` — read `references/gold-example.md` first; it is a real approved recommendation and the quality bar. Per gap: diagnosis → one article recommendation with the full step-structured content brief → social recommendations only if asked. Diagnose using `references/methodology.md` (extractability vs. citability, the three measurement stages, E-E-A-T, recency).
6. **Report**: scorecard table (per-topic metrics with sample sizes), gaps with priority/confidence, recommendations, and a measurement plan that follows the panel/control discipline in `references/recommendations.md` — never a single before/after target.

## Output contract

A recommendation is complete only when it has: the exact article title and URL slug, the competitor page it displaces and why that page currently wins, one step per H2 naming the verbatim panel questions it answers, effort (Low/Medium/High) and owner (Content Team / Product Manager / Engineering) per step, a "done" test per step, priority 1–10 and effort 1–3 per the scoring rules, confidence carried from the gap, and a panel-based measurement plan. If a sentence would survive with the topic swapped out, rewrite it with the specifics.

## Common mistakes

- Substituting your own buyer questions or competitor set for the configured ones.
- Reporting a gap without sample size and confidence.
- Tiered generic advice ("build thought leadership", "improve E-E-A-T") in place of the step-structured contract.
- Declaring a numeric target ("3x visibility") without defining the metric and measurement method first.
