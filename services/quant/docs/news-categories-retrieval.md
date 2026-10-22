# GDELT retrieval for the news-category study

The protocol is `services/quant/docs/news-categories-nifty-protocol.md`. Do not score train or validate until that file is committed and every category has volume for every day from 2017-01-01 through the study date.

## Cache

Raw responses stay in `services/quant/.cache/news-categories/`. That directory is gitignored. A file is reused only when its URL matches the frozen query. The file name is the SHA-256 of the URL.

A date omitted between the first and last point of one successful file is volume 0. A date that is not inside any successful file is missing. Missing is not 0.

`coverage.json` records ranges a live response answered. It does not replace the files.

## Plan, then resume

From the repository root, with the quant package on `PYTHONPATH`:

```bash
python -m quant_agents.research.news_categories plan
```

`plan` prints the remaining `timelinevolraw` windows. It does not call GDELT.

```bash
python -m quant_agents.research.news_categories train
```

`train` fetches only those gaps, one request at a time, with a pause after each success. A cached URL is not requested again. HTTP 429 uses `Retry-After` when the header is a number of seconds, otherwise the fixed pauses. A window that still returns 429 is split. A short volume window that still returns 429 is not stored as zero. If any category is still missing days after the fetch loop, train writes the blocked result and exits. It does not score and it does not open validate.

Tone is fetched after volume. A tone failure does not delete volume and is not part of the pass rule.

## Rate limit

Keep a single client. Do not run two trains at once. On a continued 429, stop and leave the cache in place. The next `plan` shows what is left.
