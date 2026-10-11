# Wikipedia review with MiMo-V2.6-Pro

The import and candidate review scripts default to `xiaomi/mimo-v2.6-pro`
through `https://openrouter.ai/api/v1`. Set `OPENROUTER_API_KEY` in the process
environment. Credentials never belong in tracked configuration.

Install Pi's pinned Node dependencies with `npm ci`. The Python review script
uses Pi Agent Core to execute the model/tool loop and keeps database validation
in Python. `--agent-runtime compatible` retains the previous compatible API loop.

```powershell
python scripts/review_wikipedia_candidates.py
python scripts/review_wikipedia_candidates.py --execute --accept-cost `
  --output .build/wikipedia-glm-reviewed.db
```

All 12 candidate kinds are selected by default. The agent has read-only SQL,
local revision-pinned Wikipedia search, current English Wikipedia search, wider
web search through OpenRouter's web plugin with the same GLM model,
and a validated staging decision tool. Live search is supplementary; replacement
claims still require verbatim evidence from an attached local revision.
Atoms and molecules support keep, rewrite, duplicate and reject. Other kinds
currently support keep/reject because their replacement and identity checks
have not been implemented. Review decisions remain unverified.

The output is a resumable database copy. Successful decisions are skipped on
later runs against the same output; errors are retried. Use a fresh output path
to re-review previously successful decisions with a new model. Three consecutive
errors stop the run rather than consuming the entire queue after a service or
credential failure. A run with any errors is marked failed in its audit table.

On Windows, `scripts/start_wikipedia_review.ps1` can load a DPAPI-encrypted
credential from `.build/openrouter-key.dpapi` for the current Windows user, or
use an existing `OPENROUTER_API_KEY`. It runs the same resumable review job.
An expiring key does not impose a seven-day execution schedule. The Windows
launcher automatically resumes after temporary connection failures, waiting
60 seconds between attempts. Billing, authentication, and validation failures
still stop the job. Create `OUTPUT_PATH.stop` to cancel pending network retries.

Download the newest completed full English Wikipedia article dump and its
multistream index independently:

```powershell
python scripts/download_wikipedia_dump.py --output C:/datasets/wikipedia
# Resume the specific release after an interruption:
python scripts/download_wikipedia_dump.py --date 20260901
```

The downloader pins a dated upstream release, resumes `.part` files, validates
the published sizes, checks upstream MD5 when it is published, and records local
SHA-256 hashes. Its `download-status.json` states whether upstream checksums were
available. The dump contains current article text, not full revision history or
media. It is stored separately from the original chemistry archive so existing
import provenance stays reproducible. Add `--full-wikipedia` to require a
cross-check against an attached article in the checksum-verified full local dump:

```powershell
python scripts/review_wikipedia_candidates.py --execute --accept-cost `
  --output .build/wikipedia-glm-reviewed.db --full-wikipedia C:/datasets/wikipedia/20260901
```

The full-dump lookup indexes only the original archive's source page IDs and
reads one bounded compressed stream at a time. It retains the dump date, page ID,
revision ID, and source URL in review tool traces. Replacement evidence still
comes from the original attached revision, preserving import provenance.
