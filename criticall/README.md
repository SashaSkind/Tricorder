# Tricorder

**Critical-findings agent for emergency radiology.** AI can spot a broken neck in seconds. Then the finding sits in a queue while the patient sits in the ER. Tricorder closes that loop — detection to doctor to documented acknowledgment — automatically.

**Live:** https://criticall.edgeone.cool

**Framework:** None (raw Python + React) · **Category:** Agent · **Language:** Python + TypeScript · **Built for:** Agent Forge Mini Hackathon on EdgeOne Makers

---

## The problem

**Detection isn't the failure point. Communication is.**

| T+0 sec | The gap — minutes to hours of phone tag | T+??? |
|---|---|---|
| CT reveals a cervical-spine fracture | | ER physician finally sees the result |

A missed or delayed critical result can mean paralysis or death — the patient may be mobilized with an unstable neck. The ACR (American College of Radiology) *requires* critical findings to be communicated and acknowledged, with a documented trail. Today that trail is phone tag and sticky notes: a known driver of patient harm and malpractice claims.

Detection has been solved for years. Getting the human on the other end to see it, in time, with a paper trail — has not.

---

## How Tricorder works

Finding → physician → **acknowledged**. One agent, five steps.

1. **DETECT** — Scan hits the worklist. Fracture model runs per vertebra C1–C7, returning probability + the exact flagged axial slice.
2. **TRANSLATE** — LLM impression via the EdgeOne AI Gateway: *"Type II odontoid fracture at C2, 87 %, slice 142. Immobilize + neurosurgery consult."* Read in 3 seconds.
3. **SHOW** — The flagged CT image, fracture boxed and labeled on the vertebra, appears on the radiologist dashboard.
4. **PAGE** — Looks up the ordering physician, sends SMS with a tap-to-acknowledge link.
5. **CLOSE** — ACK hits a webhook → dashboard flips green → timestamped ACR-compliance audit trail written to durable memory.

**Negative screens don't page.** Clean study? Stays silent. Specificity, not alert fatigue.

---

## Architecture

The whole loop runs on EdgeOne Makers:

| Layer | What it does |
|---|---|
| **Agent runtime** (`agents/`) | Orchestrates the detect → page → close loop |
| **Cloud functions** (`cloud-functions/`) | Serverless Python — `/analyze` · `/ack` · `/cases` |
| **AI Gateway** | `@makers/deepseek-v4-flash` generates the critical impression |
| **Memory store** | Durable, timestamped ACR-compliance audit trail |
| **Pages hosting** (`src/`) | React + Vite radiologist dashboard, globally accelerated |

### Cloud function endpoints

| Path | Purpose |
|---|---|
| `POST /analyze` | Ingests a study, runs detection, writes case + audit rows, pages ordering physician if critical |
| `POST /ack` | Physician tap-to-acknowledge webhook. Flips the case status and stamps the audit trail |
| `GET  /cases` | Radiologist dashboard feed — active + acknowledged critical cases |
| `POST /chat` | Radiologist assistant agent, SSE streaming with tool calls |

### Honest engineering

The RSNA cervical-fracture models are multi-GB GPU ensembles — they don't belong in a serverless runtime. **Detection sits behind a one-env-var seam**: today it's a same-schema stub with realistic per-vertebra output; in production the same call hits a GPU inference server. Everything else — LLM impression, paging, closed loop, audit trail — is 100 % real and live.

Switch the seam by setting `DETECT_BACKEND=gpu` and pointing `DETECT_INFERENCE_URL` at a GPU inference server that matches the stub's response schema. No other code changes.

---

## Local development

Prerequisites: Node.js ≥ 18, Python ≥ 3.10, EdgeOne CLI (`npm i -g edgeone`).

```bash
npm install
pip install -r requirements.txt
cp .env.example .env       # then fill in AI_GATEWAY_API_KEY / AI_GATEWAY_BASE_URL
edgeone makers dev
```

Local agent metrics + traces at `http://localhost:8080/agent-metrics`.

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `AI_GATEWAY_API_KEY` | Yes | Makers Models API key or any OpenAI-compatible provider key |
| `AI_GATEWAY_BASE_URL` | Yes | Gateway base URL. For Makers Models: `https://ai-gateway.edgeone.link/v1` |
| `AI_GATEWAY_MODEL` | No | Model ID. Defaults to `@makers/deepseek-v4-flash` (free, capped) |
| `DETECT_BACKEND` | No | `stub` (default) or `gpu`. Selects the detection seam |
| `DETECT_INFERENCE_URL` | If `DETECT_BACKEND=gpu` | GPU inference server URL |
| `SMS_PROVIDER_URL` | No | Where paging webhooks are sent. Defaults to a Makers-side echo endpoint |

Get an `AI_GATEWAY_API_KEY`: [Makers Console](https://edgeone.ai/makers/new?s_url=https://console.tencentcloud.com/edgeone/makers) → **Makers → Models → API Key**.

---

## Project structure

```text
criticall/
├── agents/
│   ├── chat/index.py            # POST /chat — SSE streaming radiologist assistant
│   ├── chat/stop.py             # POST /chat/stop — abort active run
│   ├── chat/_images.py          # CT slice rendering helpers
│   ├── chat/_stream.py          # SSE stream helpers
│   ├── _model.py                # LLM model config
│   ├── _session.py              # Conversation memory over context.store
│   ├── _tools.py                # EdgeOne tool registry (commands, files, browser, code)
│   └── _logger.py
├── cloud-functions/
│   ├── analyze/index.py         # POST /analyze — detect + impression + page
│   ├── ack/index.py             # POST /ack — tap-to-acknowledge webhook
│   ├── cases/index.py           # GET  /cases — dashboard feed
│   ├── history/index.py         # POST /history — conversation history
│   ├── _detect.py               # Per-vertebra detection seam (stub | gpu)
│   ├── _impression.py           # LLM critical-finding impression writer
│   ├── _sms.py                  # Physician lookup + SMS paging
│   ├── _audit.py                # ACR-compliance timestamped audit trail
│   ├── _cases.py                # Case store abstraction
│   └── _logger.py
├── src/                         # React + Vite radiologist dashboard
│   ├── App.tsx
│   ├── api.ts                   # /analyze, /ack, /cases wrappers
│   ├── components/
│   ├── i18n/
│   └── lib/
├── package.json
├── requirements.txt
└── .env.example
```

Files prefixed with `_` are private modules — not exposed as public routes.

---

## Why Tricorder wins

**Completeness** — Full end-to-end loop deployed and live: scan in, acknowledgment out, audit trail written.

**Innovation** — Everyone builds detection. Tricorder closes the *communication* loop — the step where patients are actually harmed.

**Real-life problem** — ACR-mandated critical-results communication is a documented driver of patient harm and malpractice.

**Sponsor usage** — Agent runtime · AI Gateway · cloud functions · memory · Pages — every EdgeOne Makers pillar, deployed one-click.

Every critical finding, acknowledged in seconds — with the paper trail regulators already demand.

---

## Deploy

[![Deploy to EdgeOne Makers](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://edgeone.ai/makers/new?template=python-starter-agent&from=within&fromAgent=1&agentLang=python)

Or manually:

```bash
edgeone deploy
```

One command, live URL.

---

## Resources

- [EdgeOne Makers Agents documentation](https://pages.edgeone.ai/document/agents)
- [Makers Quick Start](https://pages.edgeone.ai/document/agents-quick-start)
- [Makers Models](https://pages.edgeone.ai/document/models)
- ACR Practice Parameter for Communication of Diagnostic Imaging Findings (context for the problem this solves)

## License

MIT.
