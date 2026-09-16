# Recommendation Contract

Exact rules ported from `aeo_eval/recommendations/generator.py`. Every recommendation you produce must follow this contract. Read `gold-example.md` before writing your first recommendation — it is a real approved output and sets the quality bar.

## Pipeline per gap

1. **Diagnose** the root cause first (1–2 sentence diagnosis + specific root causes tied to evidence). Consider: page organization, content depth, authority signals, technical accessibility, content recency. Distinguish *retrieval-eligibility* problems (no Striim page speaks the topic's vocabulary at all) from *head-to-head ranking* losses.
2. **One article recommendation** — the primary deliverable, with a full content brief as implementation steps.
3. **Up to three social-media recommendations** (Reddit, LinkedIn, Facebook) derived from the same diagnosis.

## Specificity Requirements (mandatory, verbatim from the platform)

- Ground every claim and step in the EVIDENCE: name the actual question, cited page, or extracted claim it addresses.
- Never write advice that could apply to any topic or any company. If a sentence would still make sense with the topic swapped out, rewrite it with the specifics.
- Every implementation step must be executable without further research: state exactly what to create or change, where it lives, and what "done" looks like.
- Do not use filler like "comprehensive guide", "best practices", "high-quality content", or "optimize for SEO" without immediately stating the concrete specifics.

## Article recommendation structure

Implementation steps in this order:

1. **First step:** exact working title, target URL slug (striim.com/blog/`slug` or striim.com/guides/`slug`), and which cited competitor page this article must displace — and what that page does that currently wins the citation.
2. **One step per major H2 section.** Each step names the exact H2 heading and lists, verbatim, the evaluated question(s) the section must answer in its first paragraph. Notes carry the key points, data, product specifics, and what "done" looks like.
3. **Finishing steps:** which schema markup to add (FAQPage / HowTo / Article — say which and for what content), which existing Striim pages should link to the new article, technical review, publish.
4. **Final step:** re-run the affected evaluation questions and compare visibility.

Every step needs **effort** (Low/Medium/High) and **owner** (Content Team / Product Manager / Engineering).

## Social-media recommendation structure (per platform)

All platforms return: recommended_action, implementation_steps (each names the exact community/group, the exact thread or post title, and what it must say — never "engage with the community"), content_outline (full draft titles + specific talking points tied to the evaluated questions), hashtags/communities, frequency, evidence_summary.

- **Reddit:** 3–5 relevant subreddits where the topic is discussed; thread titles are the actual evaluated questions (or close paraphrases); answers counter the specific claims competitors win on. E.g. r/dataengineering, r/DevOps.
- **LinkedIn:** thought-leadership posts/articles that directly answer the evaluated questions; angles counter the competitor claims in the evidence; name groups, hashtags, influencer engagement.
- **Facebook:** professional/technical groups, recurring series with named installments, discussion prompts drawn from the evaluated questions.

## Recommendation fields (all required)

| Field | Rule |
|---|---|
| type | `article` or `social_media` (+ platform) |
| problem | "Striim appears in only X% of answers for '{topic}', while {competitor} appears in Y%. Root cause: {diagnosis}" |
| evidence_summary | why this will work, citing specific questions lost and pages cited |
| recommended_action | one sentence naming the article title, target URL, and the competitor page it displaces |
| affected_pages | the Striim URLs involved |
| suggested_owner | article → Content Team; social → Marketing Team |
| priority | 1–10, see scoring below |
| estimated_effort | story points 1–3: article = 2, social = 1 |
| measurement_plan | "Re-run '{topic}' questions after implementation and compare visibility metrics" (article); engagement tracking (social) |
| confidence | carried over from the gap (high/medium/low) |
| status | starts `draft`; `pending_publish` only when confidence = high AND priority ≥ 8. Social recs never auto-publish. Workflow: draft → pending_approval → approved/rejected → implemented |
| implementation_steps | per the structures above |

## Priority scoring

From the gap's priority and Striim's visibility:

- gap priority **high**: priority = **8** if Striim visibility < 10%, else **6**
- gap priority **medium**: priority = **5**
- gap priority **low**: priority = **3**
- social-media recs: article priority − 2 (minimum 1)

## Measurement discipline (from the gold example)

Never declare success on one re-run. Register a fixed prompt panel, run it weekly across engines at consistent n, log per-engine query-failure rates, track the three stages separately (crawler hits → citation share → click-through), compare against a site-wide control, and define the numeric target concretely before starting (e.g. "named in ≥3 of 12 panel prompts in 2 consecutive weeks", not "3x visibility").
