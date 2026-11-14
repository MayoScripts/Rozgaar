# Roadmap

rozgaar grows one reliable piece at a time. Something lands here only once it
works end-to-end, has tests, and holds no personal data.

## Now (0.1)

- Discovery from Greenhouse, Lever and Ashby public board APIs
- Free gates: role, seniority, years, age, location, phrases, companies
- Fit grading with a heuristic or LLM JD parser, cached
- Board discovery from a company name
- Local status tracking (`shortlisted`, `applied`, ...) and CSV export

## Next

- **More sources.** Workable and SmartRecruiters public APIs. Community
  new-grad feeds as a *discovery* source, resolving each link back to its
  ATS posting so it can be graded rather than left ungraded.
- **Scheduled runs and a digest.** Run daily and send a summary of new A/B
  postings.
- **Better grading.** Weight must-haves by emphasis, and calibrate the A/B
  thresholds against real outcomes.

## Later

- **Application assistance.** Tailored resume and cover-letter drafts
  grounded only in facts from the profile. Form-filling for friendly ATSs
  behind an always-on human review step.
- **A small local UI** over the same database.

## Non-goals

- Mass auto-applying. Quality over volume is the point.
- Logging into job sites or working around bot protection.
