# 🩺 Tricorder — Closed-Loop Critical-Findings Agent

> **AI can spot a broken neck in seconds. Then the finding sits in a queue while the patient sits in the ER.**
> Tricorder closes that loop — **detection → doctor → documented acknowledgment** — automatically.

**🌐 Live demo:** https://tricorder.edgeone.cool
**🎬 Video demo:** https://youtube.com/shorts/Pr-9I0Mb9xU
**🧑‍⚕️ Built for:** Agent Forge Mini Hackathon · Tencent EdgeOne Makers × AI Builders (SF, AI Engineer World Fair)

---

## The problem — detection isn't the failure point, *communication* is

When a CT scan reveals a life-threatening finding like a **cervical-spine (broken neck) fracture**, AI can flag it in seconds. But the deadly gap is what happens *next*:

| T+0 sec | The gap | T+??? |
|---|---|---|
| CT reveals a cervical-spine fracture | **Minutes → hours of phone tag** | ER physician finally sees the result |

- A missed or delayed critical result can mean **paralysis or death** — the patient may be mobilized with an unstable neck.
- The **ACR (American College of Radiology) requires** critical findings to be *communicated **and** acknowledged*, with a **documented trail**.
- Today that trail is phone tag and sticky notes — a **known, documented source of patient harm and malpractice**.

**Tricorder automates that closed loop and writes the paper trail regulators already demand.**

---

## What it does — one agent, five steps

```
CT study ─▶ ① DETECT ─▶ ② TRANSLATE ─▶ ③ SHOW ─▶ ④ PAGE ─▶ ⑤ CLOSE ✓
```

| Step | What happens |
|---|---|
| **① Detect** | Scan hits the radiologist worklist → fracture model runs per vertebra **C1–C7** → probability + the exact **flagged axial slice**. |
| **② Translate** | The **EdgeOne AI Gateway** LLM turns raw model output into a plain-English critical impression a busy ER doc reads in 3 seconds: *"Type II odontoid fracture at C2, 87% confidence, axial slice 142. Recommend immobilization + neurosurgery consult."* |
| **③ Show** | The flagged CT slice is displayed with a **labeled box** on the fractured vertebra. |
| **④ Page** | Looks up the **ordering ER physician** and **texts** them the finding (real SMS via Twilio, or in-app phone panel) with a **tap-to-acknowledge** link. |
| **⑤ Close** | Doctor taps **ACK** → hits a **webhook** → dashboard flips to *"✓ acknowledged in 2s"* → a **timestamped ACR-compliance audit trail** is written to the memory store. |

**And when the study is clean?** It stays silent. Negative screens **don't page** — specificity, not alert fatigue.

---

## Try the live demo (30 seconds)

**🎬 Watch it in action:** https://youtube.com/shorts/Pr-9I0Mb9xU

1. Open **https://tricorder.edgeone.cool**
2. Click **Robert Delgado (CT-4471)** → **▶ Run Tricorder**
3. Watch the pipeline → 🚨 **CRITICAL · Type II odontoid fracture at C2, 87%, slice 142** with the CT overlay + C1–C7 probability bars
4. The **ER phone panel** (right) receives the text → tap **Reply "ACK"** → dashboard flips to **✓ Loop closed** with turnaround time
5. Try **James Okoro (CT-2290)** → correctly screens **negative, no page**

---

## Built on Tencent EdgeOne Makers — the whole loop on one platform

| Sponsor feature | How Tricorder uses it |
|---|---|
| **Agent runtime** | Orchestrates the detect → translate → page → close loop |
| **Serverless cloud functions** | Python endpoints — `/analyze` · `/ack` · `/cases` |
| **AI Gateway** | `@makers/deepseek-v4-flash` writes the plain-English critical impression |
| **Memory store** | Durable, timestamped ACR-compliance audit trail (page → ack) |
| **Pages hosting** | React/Vite radiologist dashboard, globally accelerated |
| **EdgeOne CLI** | One-command deploy → live URL |

### Honest engineering (the model seam)

The RSNA 2022 cervical-fracture models are **multi-GB GPU ensembles** — they don't belong in a serverless runtime. So detection sits behind a **one-env-var seam** (`MODEL_ENDPOINT`):

- **Today:** a same-schema stub returns realistic per-vertebra output (identical shape to the real model).
- **Production:** the same call hits a **GPU inference server** (FastAPI + PyTorch hosting the RSNA ensemble).

Everything else — impression, paging, closed loop, audit trail, deploy — is **100% real and live**. Swapping stub → real model is a single environment variable; nothing downstream changes.

---

## Architecture

```
                        ┌──────────────────────────────────────────┐
   Radiologist          │            EdgeOne Makers                 │
   dashboard  ──POST──▶ │  /analyze  detect → impression → page     │
   (React/Vite,         │      │        │           │               │
    Pages hosting)      │      ▼        ▼           ▼               │
                        │  _detect   AI Gateway   _sms (Twilio)      │
                        │  (stub↔GPU  (LLM)       + tap-to-ACK link  │
                        │   seam)                                    │
                        │                                            │
   ER physician ◀──SMS──┤  /ack   webhook (tap link · reply ACK)     │
   phone         ──ACK─▶│      └─▶ _audit → memory store (trail)     │
                        └──────────────────────────────────────────┘
```

### Endpoints

| Route | Method | Purpose |
|---|---|---|
| `/cases` | POST | Worklist of incoming CT studies |
| `/analyze` | POST | Run detection → impression → page the ordering physician |
| `/ack` | POST (JSON) | In-app acknowledgment |
| `/ack` | GET `?study=&r=` | Tap-to-ACK magic link inside the SMS → HTML confirm page |
| `/ack` | POST (form) | Real Twilio inbound "reply ACK" webhook → TwiML |

---

## Project structure

```
criticall/                        # project folder (app is branded "Tricorder")
├── cloud-functions/
│   ├── _cases.py                 # sample c-spine studies (C1–C7 schema + ordering-MD metadata)
│   ├── _detect.py                # fracture-detection tool: stub ↔ GPU-endpoint seam
│   ├── _impression.py            # plain-English ER impression via AI Gateway (+ template fallback)
│   ├── _sms.py                   # real Twilio SMS (gated on env; falls back to in-app panel)
│   ├── _audit.py                 # closed-loop audit trail (memory store + in-process mirror)
│   ├── analyze/index.py          # POST /analyze
│   ├── ack/index.py              # /ack — JSON · tap-link GET · Twilio inbound POST
│   └── cases/index.py            # POST /cases
├── src/
│   ├── App.tsx                   # Tricorder dashboard: worklist → alert → CT overlay → phone → timeline
│   └── index.css                 # dark clinical design system
└── .env                          # AI Gateway + (optional) Twilio creds — gitignored
```

---

## Run locally

```bash
cd criticall
npm install
edgeone makers dev        # → http://localhost:8088
```

`edgeone makers dev` auto-provisions a local AI Gateway credential, so the LLM impression works out of the box.

## Deploy

```bash
cd criticall
edgeone makers deploy -n tricorder    # → https://tricorder.edgeone.cool
```

## Wire real SMS (optional — Twilio)

Set these (via `edgeone makers env set` or in `.env`) and re-run — no creds = in-app phone panel, so the demo never breaks:

| Var | Value |
|---|---|
| `TWILIO_ACCOUNT_SID` | from Twilio console |
| `TWILIO_AUTH_TOKEN` | from Twilio console |
| `TWILIO_FROM_NUMBER` | your Twilio number (E.164) |
| `DEMO_PAGER_NUMBER` | verified demo phone — forces every page to it |

For true "reply ACK": point your Twilio number's inbound webhook at `https://tricorder.edgeone.cool/ack`. The tap-to-ACK link works without it.

---

## Why it wins — four criteria, four checks

| Criterion | Tricorder |
|---|---|
| **Completeness** | Full end-to-end loop, **deployed and live** — scan in, acknowledgment out, audit trail written. |
| **Innovation** | Everyone builds detection. Tricorder closes the **communication loop** — the step where patients are actually harmed. |
| **Real-life problem** | **ACR-mandated** critical-results communication — a documented driver of patient harm and malpractice. |
| **Sponsor usage** | Agent runtime · AI Gateway · cloud functions · memory · Pages — **all on EdgeOne, deployed one-click.** |

---

*Every critical finding, acknowledged in seconds — with the paper trail regulators already demand.*

**▸ https://tricorder.edgeone.cool**
