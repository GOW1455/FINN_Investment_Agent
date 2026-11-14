# FINN

A mobile-first investment agent for a public-markets investor. It answers three questions:

1. **What changed?** (Push) Filings and unusual price moves across the portfolio, ranked so the few that matter come first.
2. **What does the company say, and is it true?** (Pull) Research on any NSE company from primary sources, argued out by four agents.
3. **Who do I know who can explain it?** (Network) The investor's own contacts, surfaced inside Push and Pull at the moment they are useful.

Built for the ENAM Founding AI Engineer build challenge.

## Contents
- [Features at a glance](#features-at-a-glance)
- [Today tab (Push)](#today-tab-push)
- [Research tab (Pull)](#research-tab-pull)
- [Ask FINN](#ask-finn)
- [Network tab](#network-tab)
- [Across the app](#across-the-app)
- [Run it](#run-it)
- [Settings](#settings)
- [Project layout](#project-layout)
- [API](#api)
- [What is stored, and when](#what-is-stored-and-when)
- [Architecture decisions](#architecture-decisions)
- [Data honesty](#data-honesty)
- [Known limits](#known-limits)
- [Deliberately left out](#deliberately-left-out)
- [Where next](#where-next)
- [References](#references)

## Features at a glance

| Part | Feature | Uses a model? |
|---|---|---|
| **Today** | Digest of filings for 18 holdings, in a time window you choose | Only for filings the rules cannot label |
| | Ranking into material, notable and routine, with the reasons shown | No |
| | A slider per filing type to set how much it matters | No |
| | Market-reaction bonus for filings the stock moved on | No |
| | Duplicate filings folded into one card | No |
| | Unusual price and volume alerts with your own thresholds | No |
| | Results card: Revenue, EBITDA, PBT, PAT with QoQ and YoY | To read the PDF; the maths is code |
| | Management-change card with background and network overlap | To read the PDF; the matching is code |
| | Brief for other material filings | Yes |
| | "A reason to reconnect" nudges | No |
| **Research** | Four-agent debate on any NSE company | Yes |
| | Promised vs delivered scorecard | Yes, with date and citation checks in code |
| | Bull and bear case, divergences, questions for management | Yes |
| | Fact sheet of about 40 computed numbers | No |
| | Model picker, and the model named on every report | n/a |
| | Saved reports that reopen instantly | No |
| **Ask FINN** | Questions about one filing or one report, framed by your focus | Yes |
| **Network** | Who should I call, for any company | No |
| | Second-degree links to people named in filings | No |
| | Expertise search by theme | No |
| | Contact dossier | No |
| | Add and remove your own contacts | No |

## Today tab (Push)

The Today tab shows what changed across the portfolio and what deserves attention.

### Time window
- Four fixed windows: **24h** (the default), **3 days**, **7 days**, **30 days**.
- **Custom:** any window from 1 hour to 90 days, entered as a number of hours or days. **Reset** clears the entry and returns to 24h.
- A link can open a chosen window, for example `/?hours=168`.

### The digest
- Every NSE announcement for the 18 holdings in the chosen window.
- Each filing is sorted into one of ENAM's 17 categories (results, M&A, management change, litigation and so on).
- **Material** filings show as cards, **notable** ones as single lines under "Worth a glance", and **routine** ones collapse into a count that can be expanded.
- The same event filed several times on one day (board outcome, results, press release) is folded into one card marked "+N related filings".
- The headline counts what needs attention, for example "5 things need you", and states how many filings were set aside.

### How a filing is ranked
A filing's score from 0 to 100 has three parts. Opening a filing shows them under "Why this ranks N of 100".
1. **A starting score for its category.** The defaults are in `backend/finn/push/priority.json`.
2. **Judgment adjustments** from the same file. A CEO, CFO or MD change counts for more than an independent director rotating. Repaying debt counts for less than raising it. A tax demand counts for less than other litigation.
3. **A market-reaction bonus.** If the stock moved unusually on the first trading session that could see the filing, it ranks higher. "Unusual" uses the investor's own alert thresholds.

A score of 70 or more is material, 40 or more is notable, and the rest is routine.

### Settings (the sliders icon)
- **Unusual moves:** the volume multiple, the daily price move, and how many trading days to compare against.
- **How much each kind of filing matters:** one slider per category, showing which tier that score lands in. "Reset all" restores the defaults.
- Settings are saved in the browser.

### Alerts
- A stock is flagged when its latest daily volume is above N times its recent average, or its daily move is beyond ±X%.
- Tapping an alert shows the close, the change, the volume multiple, why it was flagged, that company's filings in the window, and a button to research it.

### Filing cards
- **Results:** Revenue, EBITDA, PBT and PAT for the quarter with QoQ and YoY. In the feed these come from the standardised quarterly table. Opening the filing reads the results PDF itself when a model is available. Percentages and EBITDA are always computed in code. If the table does not yet hold the reported quarter, the card says so instead of showing an older quarter.
- **Management change:** who joined or left, their role, and their background as the filing itself states it. Then who in the network worked or studied with them, graded strong, medium or weak.
- **Other material filings:** a short brief from the PDF: what happened, up to three hard facts, and one question it raises.
- **Every material filing:** up to three contacts who can explain it, with the reason for each.
- **Ask FINN** on each card opens the question box for that filing.
- **Open the filing** links to the original PDF.

### A reason to reconnect
When a holding files something material, FINN looks for a contact who works or worked there and has not been spoken to for 75 days or more.

## Research tab (Pull)

Research on any NSE symbol, from the company's own documents only: reported financials, the last four earnings-call transcripts, and the annual report. No news, no broker notes and no model memory of the company.

### The debate
| Agent | Reads | Produces |
|---|---|---|
| Desk (code, no model) | Screener.in tables and document links | About 40 numbered facts: growth rates, margins, leverage, cash conversion, quarterly trends |
| Numbers Analyst | The fact sheet | Findings on snapshot, trajectory, balance sheet and cash quality |
| Guidance Analyst | Each transcript, one call per transcript | What management explicitly promised, with the exact quote and page, plus tone and what analysts pressed on |
| Skeptic | Promises, the fact sheet, the Numbers Analyst's findings | A verdict on each testable promise, divergences, and one challenge to each analyst |
| Both analysts | The Skeptic's challenge | A rebuttal, conceding or holding |
| Moderator | Everything above | Headline, narrative vs numbers, three bull points, three bear points, three questions for management |

The screen shows each step as it finishes. A new company takes one to two minutes.

### What the report contains
- The headline and four key ratios.
- **Promised vs delivered:** each promise, the exact quote, when it was said, and a verdict of delivered, partly, missed or too early.
- Bull case and bear case.
- Where story and numbers part ways.
- Who in the network can pressure-test it.
- Questions worth asking management.
- The business and its segments, from the annual report (when annual-report reading is on).
- Trajectory, balance sheet, cash quality and snapshot findings.
- Management's tone on each call.
- The debate itself, including challenges and rebuttals.
- An audit line: how many claims were kept, how many were dropped, the sources, the time taken and the model used.

These cover all eight outputs in the brief: business snapshot, financial snapshot, trajectory, balance sheet, cash quality, narrative vs numbers, guidance, and bull vs bear.

### How it stays grounded
1. **Every point must cite evidence.** A point is kept only if it names a real evidence id, such as `N7` (a fact) or `C2:14` (call 2, page 14).
2. **Every quote is checked against the page.** If the quoted words are on another page, the page is corrected. If they are nowhere, the promise is discarded.
3. **Dates are enforced in code.** A promise can only be scored against quarters reported after that call. If none exist, it is marked "too early" whatever the model said.
4. **"No data" is not a verdict.** A row where the Skeptic had nothing to test against is dropped, not marked missed.
5. **Everything dropped is counted** and shown in the audit line.
6. **All arithmetic is code.** The agents receive finished numbers and never calculate.

### Model picker
- "Model for new research" lists the models that have a key configured.
- The chosen model runs every step of a new debate.
- Each report names the model that produced it. Saved reports keep their original model; "Run the debate again" replaces a report using the current choice.

### Saved reports
23 companies are saved in the repo and open instantly: the 18 holdings, four companies outside the portfolio (KPITTECH, LAURUSLABS, CAMS, ASTRAL) and WIPRO.

## Ask FINN

A question box inside every filing and every research report.

- **Context you choose.** A question inside a filing is answered from that filing's pages. A question inside a report is answered from that company's fact sheet, management's quoted promises, the scorecard, and the six earnings-call pages that share the most words with the question.
- **"What I'm working on".** A short note you write once. It is sent with every question, so answers are framed for your research angle. It is saved in the browser.
- **Cited answers.** Each point carries citation chips. Tapping one shows the number or quote and a link to that page of the PDF. A point without a valid citation is not shown.
- **Honest gaps.** If the sources do not answer, it says "Not in these sources", states what is missing, and suggests one or two contacts who might know.
- **Follow-ups.** It remembers the last three questions in that filing or report and proposes two follow-up questions.
- **Model.** A picker in the box; each answer names the model that replied.

## Network tab

The investor's contacts as an intelligence layer. Every answer here is plain code, so it can be explained and is never invented by a model.

### Who should I call
For any NSE company, contacts are ranked by their best connection to it:

| Connection | Starting score |
|---|---|
| Works there now, or used to | 100 |
| Works or worked at a competitor | 60 |
| Has matching sector expertise only | 38 for the specific industry, 26 for the broad sector |

The score is then adjusted for how recently they left, how long they stayed, whether they have seen the company from two sides, and how close the investor is to them. Each result says why they matter and what they would know.

A company's names, competitors and industry are fetched from screener.in. Nothing about company relationships is written by hand, so this works for any NSE symbol.

### Second-degree reach
For a person named in a filing, such as a new director, FINN finds contacts who overlapped with them at an employer or a school. Overlapping years count as "worked together"; the same employer at different times is a weaker link.

### Ask box
- A company name or symbol returns "who should I call".
- A contact's name returns their profile.
- Anything else is treated as a theme, such as "specialty chemicals" or "rural lending", and returns contacts with that expertise.

### Contacts
- **Roster** of all contacts, sortable by going cold, closest, or A to Z, with the holdings each one covers.
- **Dossier:** career, education, expertise, notes, what you share with them, and when you last spoke.
- **Add a contact:** name, how you know them, closeness, last contact, any number of jobs and schools, expertise and notes. Only the name is required. The contact is used in every network answer straight away.
- **Remove:** contacts you added can be removed from their profile. The starting contacts cannot.

### Where the network appears outside its tab
- The contact chip on filing cards, and "Who can explain this" inside a filing.
- "In your network" on management-change cards.
- "A reason to reconnect" in the Today tab.
- "Who you know who can pressure-test this" in research reports.
- "Someone who might know" when Ask FINN cannot answer.

## Across the app

- **Mobile-first.** A single column up to 560px wide, bottom tab bar, and bottom sheets for detail.
- **Installable.** A web app manifest lets it be added to a phone's home screen.
- **Light and dark.** Follows the device setting.
- **Links into the app:** `/?tab=research&symbol=KPITTECH`, `/?tab=network&person=p05`, `/?hours=168`.
- **State survives tab switches.** A running debate keeps going while you look at another tab.
- **Graceful without a model key.** The digest, alerts, ranking, network and the research fact sheet all work; only the model steps are missing.

## Run it

Requirements: Python 3.12 or newer with [uv](https://docs.astral.sh/uv/), and Node 20 or newer.

```bash
# 1. Backend settings
cd backend
cat > .env <<'EOF'
GEMINI_API_KEY=your-key-here
FINN_FAST_MODEL=gemini/gemini-3.5-flash-lite
FINN_FALLBACK_MODEL=gemini/gemini-3.1-flash-lite,gemini/gemini-flash-lite-latest
EOF
uv sync

# 2. Build the frontend
cd ../frontend
npm install
npm run build

# 3. Start the app
cd ../backend
uv run python -m uvicorn finn.api:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. A free Gemini key comes from https://aistudio.google.com.

For frontend development with live reload, run `npm run dev` in `frontend/` (http://localhost:5173, which passes `/api` to port 8000).

```bash
cd backend
uv run python -m pytest                          # offline tests
FINN_LIVE_TESTS=1 uv run python -m pytest        # plus an end-to-end research run on real documents
uv run python scripts/precompute.py --no-research  # refresh the saved data snapshot
uv run python scripts/precompute.py              # also research every demo company
```

### Deploy
`Dockerfile` builds the frontend and serves it with the API as one service. `render.yaml` deploys that on Render's free tier. Set `GEMINI_API_KEY` in the service's Environment tab.

## Settings

### Environment variables (`backend/.env`, or the host's environment)
| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY` | none | Keys for the providers you want to use |
| `FINN_FAST_MODEL` | `gemini/gemini-3.5-flash-lite` | The model for every step by default |
| `FINN_STRONG_MODEL` | same as the fast model | If set, only the Skeptic and Moderator use this model |
| `FINN_FALLBACK_MODEL` | none | One or more models, comma-separated, tried in order when a model is overloaded, timing out or retired |
| `FINN_MODEL_CHOICES` | a short list | Models offered in the in-app picker; only those with a key are shown |
| `FINN_OFFLINE` | `0` | `1` serves filings, prices and fundamentals from the saved snapshot, with the clock frozen at its newest filing |
| `FINN_READ_ANNUAL_REPORT` | `1` | `0` skips the annual-report step, which needs a local embedding model of about 130 MB |

Any [LiteLLM](https://docs.litellm.ai/docs/providers) model string works.

### Ranking (`backend/finn/push/priority.json`)
- `base`: the starting score for each of the 17 categories.
- `adjustments`: rules that add or subtract points when a filing's text matches a pattern, each with a plain-language reason.
- `tiers`: the cut-offs for material and notable.
- `market_reaction_points`: the bonus for a filing the stock moved on.

### The portfolio (`backend/finn/config.py`)
`PORTFOLIO` maps each NSE symbol to a display name. `RESEARCH_DEMO` lists the companies outside the portfolio shown in the Research tab.

## Project layout

```
backend/
  finn/
    api.py              HTTP endpoints; also serves the built frontend
    config.py           paths, the portfolio, model settings
    llm.py              every model call: routing, fallback, disk cache, usage log
    store.py            JSON file cache with expiry and snapshot fallback
    rag.py              page-cited retrieval over one document (local embeddings, MMR)
    ask.py              Ask FINN: context building, prompt, citation check
    sources/
      nse.py            corporate announcements from NSE
      prices.py         end-of-day prices, unusual moves, reaction to a filing
      screener.py       financial tables, document links, peers, industry
      docs.py           download a PDF once and keep its text page by page
    push/
      classify.py       categories, scoring with reasons, tiers
      priority.json     the ranking settings
      enrich.py         results numbers, people in management-change filings
      digest.py         the feed, alerts, and the detail card for one filing
    pull/
      facts.py          the numbered fact sheet (all arithmetic)
      research.py       the four-agent debate and its validators
    network/
      people.json       the starting network (synthetic)
      graph.py          name matching, who to call, overlaps, expertise, contacts
  scripts/precompute.py refresh the snapshot and research the demo companies
  tests/                offline unit tests and one live end-to-end test
  data/                 see "What is stored, and when"
frontend/src/
  main.jsx              tabs and deep links
  Today.jsx             the Push screen, filing sheet, settings sheet
  Research.jsx          the Pull screen, live debate, report
  Network.jsx           the Network screen
  Ask.jsx               the question box
  AddContact.jsx        the add-contact form
  ui.jsx                shared pieces: sheets, person rows, fetch helpers
  styles.css            all styling, light and dark
Dockerfile, render.yaml single-service deployment
```

## API

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Model settings, whether keys are present, usage since start |
| `GET /api/models` | Models the investor can choose |
| `GET /api/portfolio` | Holdings, demo companies, which are researched |
| `GET /api/push/digest` | The feed. Parameters: `hours`, `volume_multiple`, `price_move_pct`, `lookback_days`, `weights` |
| `GET /api/push/settings` | Ranking defaults for the sliders |
| `GET /api/push/item/{symbol}/{id}` | The detail card for one filing |
| `GET /api/pull/{symbol}` | A saved report |
| `GET /api/pull/{symbol}/stream` | Run or replay research as server-sent events. Parameters: `refresh`, `model` |
| `POST /api/ask` | A question about one filing or one report |
| `GET /api/network/people` | All contacts |
| `POST /api/network/people` | Add a contact |
| `GET /api/network/person/{id}` | One contact's dossier |
| `DELETE /api/network/person/{id}` | Remove a contact you added |
| `GET /api/network/company/{symbol}` | Who to call on a company |
| `GET /api/network/ask?q=` | The Network tab's ask box |

## What is stored, and when

Everything is plain JSON files under `backend/data/`. There is no database.

| Folder | Contents | Written | Kept for | In the repo |
|---|---|---|---|---|
| `cache/` | Fetched filings, prices and screener.in pages | On each fetch | 30 minutes, 6 hours and 12 hours respectively | No |
| `cache/llm/` | Every model answer, named by a fingerprint of the prompt and model | After each model call | Until deleted | No |
| `docs/` | Page-by-page text of downloaded PDFs, and annual-report search indexes | The first time a document is needed | Until deleted | No |
| `pull/` | Finished research reports | At the end of a research run | Until re-run | Yes |
| `snapshot/` | A backup copy of filings, prices and screener.in pages | Only by `scripts/precompute.py` | Until the next run | Yes |
| `network/` | Contacts added in the app | When a contact is added or removed | Until removed | No |

Browser storage holds the alert settings, category weights, the chosen model and the "What I'm working on" note.

## Architecture decisions

```
 NSE filings API ─┐
 Yahoo Finance ───┤   fetch + cache          ┌─ push/    classify → score → fold → enrich
 screener.in ─────┼─► sources/  ──► store ──►├─ pull/    fact sheet → 4 agents → validators
 exchange PDFs ───┤   (JSON files, expiry,   ├─ ask      chosen context → model → citation check
 network profiles ┘    committed fallback)   └─ network/ name matching and graph queries
                                                      │
                                   FastAPI (JSON + server-sent events) ──► React PWA
```

### Data pipelines
- **Prices:** yfinance end-of-day bars, about 90 days per symbol.
- **Filings:** the NSE corporate-announcements API, 120 days per symbol.
- **Fundamentals:** the screener.in company page, parsed for standardised tables, links to annual reports and transcripts, the peers list and the industry classification.
- **Documents:** PDFs are downloaded once and stored as page-by-page text, which is what makes page citations possible.
- **Linking names:** company names are reduced to their distinguishing words, so "HDFC Bank Ltd." matches "HDFC Bank" but not "HDFC Life", and a shortened name such as "Dr Reddy's Labs" matches its full form. A person in a filing is matched to the network by name, then by overlapping employers and schools.
- **Resilience:** a failed fetch falls back to the last cached copy, then to the committed snapshot.

### Use of models and agents
- **One door.** Every model call goes through `finn/llm.py`, which caches each answer on disk, logs token usage, and falls back down a list of models when one is overloaded, timing out or retired.
- **Default.** Every step runs on one free model, `gemini-3.5-flash-lite`, with two other free Gemini models as fallbacks. The investor can pick another model in the app.
- **Two tiers in the code.** Reading steps use the fast tier; the Skeptic and Moderator use the strong tier. Setting `FINN_STRONG_MODEL` sends only those two steps to a stronger model.
- **Where a model is used:** labelling the few filings rules cannot place, transcribing results tables, reading management-change filings, briefing a filing, the research debate, and Ask FINN.
- **Where no model is used:** all arithmetic, alert thresholds, ranking, folding duplicates, name matching, every network answer, choosing transcript pages for a question, and every citation and date check.
- **Agents.** The research agents take real turns: analysts work in parallel, the Skeptic challenges them, they rebut, the Moderator closes. They do not call tools on their own; the code hands each one its evidence.
- **Embeddings.** Annual reports are searched with a local model (`bge-small` via fastembed), stored per document with page numbers.

### Security and privacy
- **The network is the sensitive asset.** All network reasoning is code, so no contact details are sent to a model. Ask FINN sends filing or report text and, when it cannot answer, looks up contacts in code afterwards.
- **In this prototype** the network is one file on the server and there are no accounts. Anyone who can open the app can see contacts and add or remove added ones.
- **Contacts you add** are stored in `backend/data/network/`, which is excluded from the repo.
- **API keys** are read from the environment and never committed.
- **For a real deployment:** sign-in; one encrypted store per investor with row-level isolation; contacts imported only from sources the investor owns (address book, CRM, their own profile export); profile data limited to professional history; a retention period with deletion on request; an audit log of reads; no graph shared across investors.
- **Outside people,** such as an incoming CFO, are described only from what the filing itself discloses.

### Cloud
- **Now:** one container on Render's free tier, with FastAPI serving the built app. Live fetching from NSE, Yahoo Finance and screener.in works from there. Annual-report reading is switched off on that host to stay within its memory.
- **Limits of the free tier:** it sleeps when idle, and files written after deployment (new research, added contacts) are lost on restart.
- **At scale:** scheduled ingest workers, a database with vector search, object storage for PDFs, and push notifications from a queue.

## Data honesty
- **The starting network is synthetic.** Every contact in `backend/finn/network/people.json` is invented. Employers and schools are real so the network overlaps the portfolio. For real use, the investor's own contacts would be imported and enriched from a licensed provider or consented profile exports, within each platform's terms.
- **Filings, prices, financial tables, transcripts and annual reports are real** and fetched live.
- **Financial tables come via screener.in.** They are the company's reported figures, standardised by a third party.
- **Company relationships are fetched, not written.** Competitors are a company's peers on screener.in; its registered name and industry come from the same page. Customer and supplier links are not modelled, because no public source gives them reliably.
- **Still chosen by hand:** the 18 holdings and their display names, the starting contacts and their expertise tags, and the default ranking scores.

## Known limits
- **Verdict quality depends on the model.** With the free model doing the reasoning, fewer promises are found and verdicts are weaker than with a stronger model.
- **Only company-wide numbers can test a promise.** Promises about a segment or an order book are left out.
- **ITC and Trent have no promised-vs-delivered section,** because no transcripts were read for them.
- **Sector matching compares words,** not meaning. "Banking" matches the label "Non Banking Financial Company", and "IT services" does not match "Computers - Software & Consulting".
- **Ask FINN picks transcript pages by shared words,** so a question phrased very differently from the transcript may miss the right page.
- **Classification rules can mislabel** an unusual filing.
- **The market-reaction bonus is a coincidence in time, not a cause.** Every filing a company makes on a results day receives it.
- **Subsidiaries are separate companies.** A contact from Reliance Retail is not linked to Reliance Industries.
- **Push is computed on request.** Nothing is sent to the phone.

## Deliberately left out
- Real push notifications. A scheduler and web push would deliver the alerts that are now computed on request.
- Accounts and authentication.
- BSE as a second source. Its API refused non-browser requests in testing, and NSE covers the portfolio.
- A voice interface, and a graph drawing of the network. A list ranked by reason proved more useful on a phone than a node map.
- The back half of annual reports: notes, related-party transactions, auditor's remarks.
- Editing a contact. Remove and add again instead.

## Where next
- Size-relative materiality: read the rupee amount from a filing and weigh it against the company's revenue or market value.
- Learn the investor's ranking from which cards they open and skip.
- Match expertise to industries by meaning, with one saved model judgment per industry.
- Auditor qualifications, contingent liabilities and related-party transactions as a fifth agent.
- Track guidance over more than four quarters and score management's credibility over time.
- True second-degree paths from contacts' own connections, with consent.
- Evaluate the debate against a hand-labelled set of promised-vs-delivered cases.
