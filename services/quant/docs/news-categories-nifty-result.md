# News categories vs the NIFTY 50 index: result

Protocol commit: `2a074372e576f0d5615138bdb731ac2624870340` (amendment that unfetched GDELT days are not zeros). That commit is an ancestor of this result. No train table was written before it.

Status: **BLOCKED**. Train was not scored. A train freeze was not created. Validate was not opened. `validation_runs` is 0.

## Why there is no result table

A category day counts only when every query in that category has an observed volume. One successful timeline's interior gaps are zeros. Days outside every successful file are missing, and missing is not zero and not a control day.

The cache on 2026-10-23 has volume and tone for the first geopolitics query from 2017-01-01 through 2026-10-22. The India-Pakistan volume query runs from 2017-01-01 through 2026-01-13 (3,300 observed days through 2026-10-22). The India-China query and the other nine categories have no volume file. Because each category still has at least one empty query, every category is missing all 3,583 days from 2017-01-01 through 2026-10-23.

`plan` reported 435 remaining volume windows. A single probe the same day, India-China `timelinevolraw` for 2017-01-01 through 2017-01-15, one attempt, returned HTTP 429. That window was not stored as zero articles.

No next-session return, absolute move, VIX change, realised volatility, effect size, confidence interval, or p-value is reported. The Holm family (10 categories by 12 outcomes) was not evaluated. Nothing passed and nothing failed.

## What this does not say

This is not evidence that news has no effect on the NIFTY 50. The preregistered pass rule was never applied. GDELT's global coverage, article volume as a stand-in for importance, query wording, and overlapping event windows remain limitations for any later run that does finish the cache.

Index and VIX cross-checks were not executed for this run, because scoring did not start. Resume with `python -m quant_agents.research.news_categories plan`, then one `train` process, after GDELT accepts requests again.
