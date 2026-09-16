# AEO Methodology: Concepts, Methods, and Evidence

The knowledge base used to diagnose gaps and ground recommendations. Cite these methods when explaining *why* a recommendation will work.

## 1. The Shift: SEO vs. AEO

- SEO focuses on ranking position on a results page; AEO focuses on being the passage a model extracts/cites in its answer.
- Match the question instead of the keyword. Content structured to directly answer a specific question outperforms content structured around a keyword phrase.
- Retrieval is passage-level, not page-level. A paragraph or subsection should make sense without surrounding context.
- Ranking and citation are not the same. Pages strong in rank are not necessarily cited more often. Treat AEO and SEO as different methods.

## 2. Page Organization

- **Answer first.** The answer to a question belongs in the first 1–3 sentences of a section — models disproportionately use content that appears first under a heading.
- **Question-phrased headings.** Headings should read like what a person would ask an answer engine, not a stylized title.
- Balance professional/client-appealing content against AEO-optimized content; blog posts are a good way to keep them separate.
- **Content chunking.** Self-contained sections covering one subtopic each, not one long paragraph.
- **Specificity.** Concrete figures are cited more than vague claims ("62% of X" vs. "many X"). Numbers are worth posting.
- **Minimal structural overhead.** Plain HTML tables and a strict heading hierarchy — models tokenize raw text directly.
- **E-E-A-T signals.** Visible author credentials, clear publication dates, links to primary sources for cited statistics. Weak trust can block citation even when content ranks well.
- **Recency.** Pages posted and left alone are cited less than regularly updated pages. Revisit on a recurring basis.
- **Technical scaffolding.** Maintain llms.txt (brief background, guidance, links to detailed markdown — uncommon but emerging) and sitemap.xml (lists important pages). robots.txt is more commonly consulted than llms.txt.

## 3. Opportunity vs. Age (prioritizing existing-page fixes)

A quantitative approach for deciding which existing pages to fix first, scored against a prior 28-day window:

- **Recover:** clicks lost versus a previous period.
- **CTR gap:** actual vs. expected CTR (modeled from average search position). CTR gap × impression volume estimates recoverable clicks — the basis for prioritizing title/description rewrites. Example: 329,454 impressions at avg position 9.4 with 857 clicks (0.26% actual vs. ~2.5% expected CTR) ≈ 7,380 recoverable clicks.
- **Rank push:** estimated click gain from moving a page-two post to page one — justifies content-depth investment rather than a metadata tweak.

Guardrails:
- Exclude low-impression pages from fixes regardless of CTR gap — no edit corrects for absent search demand.
- Prioritize posts with a noticeable drop in absolute clicks regardless of queue position.

## 4. Off-Site Methods

On-page optimization only affects **extractability** (whether AI can pull an answer from a page it already trusts), not **citability** (whether AI treats the domain as legitimate). Trust comes from:

- **Third-party mention acquisition.** Being named in "best X" lists, comparison articles, social discussions, YouTube content, and review platforms (G2) moves AEO visibility faster than on-site content. Reddit is a notable share of Google AI Overview citations.
- **Paid placement on cited sources.** One system identified the second most-cited domain in a target industry via citation-source analysis, paid for sponsored articles and listicle inclusion — mentions went from zero to eight across 200 prompts in two weeks.
- **Entity consistency.** An identical description of "what the business is and does" across every platform reduces noise; organization schema makes brand identity unambiguous.
- **Avoid self-serving listicles.** Publishing "Best X" on your own domain and ranking yourself #1 is devalued by Google and can inadvertently promote named competitors.
- **Content distribution.** Repurpose source content into platform-native versions (LinkedIn, Instagram, YouTube) to reinforce cross-referencing authority signals.

## 5. Measuring Efficacy

The least mature part of the discipline. Key rules:

- **Three stages, not one metric:** (1) AI crawler accessibility — does a crawler access the page; (2) citability — is the page cited in generated answers; (3) follow-through — do people click the citation.
- **Site-wide baseline movement.** Capture site-wide performance over the same before/after range as a control; one page's before/after alone is insufficient.
- **Variance in AI queries.** Identical prompts produce different citations run-to-run. Use a repeated prompt panel measured consistently, never a single before/after measurement.
- **Query failures.** Some engines (Perplexity) silently reject a notable share of automated queries. An unreported error rate masquerades as a visibility change.
- **Attribution difficulty.** Most changes result from several concurrent tactics; single-tactic causality is hard to establish.
- **Leading vs. lagging indicators.** AI crawler bot traffic moves weeks-to-months before citation and traffic gains.

## 6. Visibility Targets

A target like "3x AI visibility" is not useful until the metric is defined:

- AI Overview appearances (trackable in Search Console): 3x on a small site in a few months is generally achievable.
- Citation frequency across answer engines: harder to track cleanly, less predictable timeline.
- Tripling from near-zero is easier than tripling an existing presence; tripling AI-specific traffic is easier than tripling total traffic via AEO.

Pin down the exact metric and measurement method before committing to a numeric target.
