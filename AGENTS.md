# AGENTS.md

Source of truth: specs/. Code follows the specs.

Workflow for every change:
1. Restate the request and assumptions.
2. Update the relevant specification and acceptance-criteria ID.
3. Write a failing test and run it.
4. Implement the smallest code change.
5. Run pytest and QA.
6. Summarise the result.

Hard rules:
- Never edit, skip or delete a test merely to make it pass.
- Never loosen the data contract merely to make QA pass.
- Never drop bad data silently.
- Bronze rows = Silver rows + rejected rows + duplicates removed, always.
- Bronze is immutable source data.
- Silver is validated typed data plus rejects and load audit.
- Gold contains dimensions, facts and analytical marts.
- Keep one responsibility per file: generator, quality rules, local ingest, Glue jobs, SQL models, KPIs, analytics adapter and app.
- Counts and sums live in Gold marts.
- Ratios live only in kpis.py and are always sum-over-sum.
- Keep changes small.
- Data is synthetic: say so wherever numbers are shown.
