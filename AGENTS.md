Build milestone by milestone (Section 14). Do not start milestone N+1 until every acceptance check of milestone N passes. Run the check commands and paste the output into docs/PROGRESS.md.
Validity is decided by deterministic Python, never by the LLM. The LLM only (a) drafts lessons from NCR text and (b) rewords plan steps that code has already built.
A lesson may never be written without measurement IDs. write_lesson() must raise if they are missing or unknown.
Never change the data contract (Section 5) or models.py after Milestone 1 without writing the reason in docs/DECISIONS.md.
Every function in Sections 6 and 7 must be importable and testable without a running API server, and without the LLM (use the disk cache, Section 7.6).
All data is synthetic. Store feature class and tolerance band only. Never store drawings, customer names or operator names.
When this document is silent, pick the simplest option and record it in docs/DECISIONS.md. Do not add features that are not listed here.
Anything marked VERIFY is a claim about an external service that must be tested, not assumed.