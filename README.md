# Rampart

**Open Policy Agent for LLM Applications.**

Rampart sits between your application and any LLM provider — Bedrock, Snowflake Cortex, Azure OpenAI — and enforces configurable safety policies on every request and every response. One `pip install`. One YAML file. Policy owned by your governance team, not your developers.

```
Your App → [Rampart: Input Guards] → LLM Provider → [Rampart: Output Guards] → Your App
```

---

## Why Rampart?

After dozens of enterprise GenAI engagements, the same problem appears every time: every team implements guardrails differently. One team uses LangChain callbacks. Another writes custom middleware. A third skips it entirely. No two projects handle PII the same way. No audit trail. No central policy.

Rampart solves this the same way Open Policy Agent solved it for infrastructure: **separate the policy from the code that enforces it.**

Governance teams write policy. Developers call one method. Rampart handles everything in between.

```python
from rampart import Rampart

client = Rampart(
    policy_registry="file://./policies/banking.yaml",
    provider="bedrock",
    app_id="customer-chatbot"
)

response = client.invoke(
    model_id="anthropic.claude-sonnet-4-6",
    messages=[{"role": "user", "content": user_input}],
    profile="customer_support"
)
```

That is the entire integration. The policy file does the rest.

---

## What Rampart Does

### Input guards — before the LLM sees the message

- **PII detection** — detect and block or redact credit cards, Aadhaar, PAN, phone numbers, emails, and more. Powered by Microsoft Presidio. No LLM required.
- **Prompt injection detection** — catch attempts to override system prompts or hijack model behaviour. Powered by LLM Guard classifiers. No LLM required.
- *(More built-in guards coming in v0.2)*

### Output guards — before your application sees the response

- **PII leakage detection** — catch PII the LLM may have surfaced in its response
- *(More built-in guards coming in v0.2)*

### Custom guards — bring your own

Any guard your use case needs that is not built in. Implement one interface. Reference it in your policy YAML. Done.

```python
from rampart import BaseGuard, GuardResult, Action

class CompetitorMentionGuard(BaseGuard):
    def scan(self, text: str, context: dict) -> GuardResult:
        competitors = self.config.get("competitors", [])
        found = [c for c in competitors if c.lower() in text.lower()]
        if found:
            return GuardResult(
                passed=False,
                action=Action.WARN,
                detail=f"Competitor names detected: {found}"
            )
        return GuardResult(passed=True, action=Action.ALLOW, detail="Clean")
```

```yaml
# Reference it in your policy — no code changes to Rampart required
- guard: CompetitorMentionGuard
  module: myapp.guards.competitor
  action: warn
  config:
    competitors: [RivalBank, CompetitorApp]
```

---

## Policy as Code

Every guard behaviour is declared in a versioned YAML policy file. No guard logic lives in application code.

```yaml
# policies/banking.yaml
version: "1.0.0"
description: "Banking application guardrail policy"

profiles:

  customer_support:
    input:
      - guard: PiiGuard
        module: rampart.guards.pii
        engine: classifier
        action: block
        config:
          entities: [CREDIT_CARD, AADHAAR, PAN, PHONE_NUMBER, EMAIL_ADDRESS]

      - guard: PromptInjectionGuard
        module: rampart.guards.prompt_injection
        engine: classifier
        action: block
        config:
          threshold: 0.8

    output:
      - guard: PiiGuard
        module: rampart.guards.pii
        engine: classifier
        action: redact
        config:
          entities: [CREDIT_CARD, AADHAAR, PAN]

  internal_analyst:
    input:
      - guard: PromptInjectionGuard
        module: rampart.guards.prompt_injection
        engine: classifier
        action: block
        config:
          threshold: 0.9
      # No PiiGuard — analysts work with real customer data

  kyc_onboarding:
    input:
      - guard: PiiGuard
        module: rampart.guards.pii
        engine: classifier
        action: block
        config:
          entities: [CREDIT_CARD]
          # PAN and AADHAAR not listed — required for KYC, permitted
```

The developer selects a profile per call:

```python
# Same client. Same policy file. Three completely different behaviours.
client.invoke(..., profile="customer_support")
client.invoke(..., profile="internal_analyst")
client.invoke(..., profile="kyc_onboarding")
```

When your governance team updates the policy YAML, all running applications pick up the change automatically — no application deployments needed.

---

## Guard Actions

Every guard declares one of four actions. The action is in the policy YAML, not the application code.

| Action | What happens |
|---|---|
| `block` | Request rejected. `PolicyViolationError` raised. Caller receives an error. |
| `redact` | Offending content masked. Request continues with cleaned text. |
| `warn` | Issue logged in audit trail. Request continues unchanged. |
| `allow` | Guard runs, findings recorded, no action taken. Use when you want visibility without enforcement. |

---

## Hybrid Engine Mode

Every guard supports three execution modes. Set it per guard in the policy YAML.

```yaml
- guard: PromptInjectionGuard
  engine: classifier   # local ML model only — fast, free, no external calls

- guard: PromptInjectionGuard
  engine: llm          # LLM judge only — higher accuracy, adds latency

- guard: PromptInjectionGuard
  engine: hybrid       # classifier first, LLM only for uncertain cases
  config:
    threshold: 0.8
    uncertainty_band: [0.4, 0.8]
    llm:
      provider: bedrock
      model_id: anthropic.claude-haiku-4-5-20251001
```

Hybrid mode runs the local classifier first. If the confidence score is clearly high or clearly low, it decides immediately. Only ambiguous cases go to the LLM judge. This keeps average latency low while maintaining accuracy on edge cases.

---

## Policy Registry

Rampart loads policy from wherever you store it. The URI scheme selects the registry automatically.

```python
# Local file — for development and single-server deployments
Rampart(policy_registry="file://./policies/banking.yaml")

# HTTP/S URL — for multi-server deployments
# All servers share one policy. Updates propagate automatically via polling.
Rampart(policy_registry="https://policies.internal.yourbank.com/banking.yaml")

# Git registry — coming in v0.2
# Full audit trail of who changed what and when, via git history
Rampart(policy_registry="git+https://github.com/yourorg/rampart-policies.git")
```

For HTTP registries, Rampart polls the URL every 5 minutes by default and reloads the policy if it has changed — without restarting the application.

```python
Rampart(
    policy_registry="https://policies.internal.yourbank.com/banking.yaml",
    reload_interval=300    # seconds, set to 0 to disable polling
)
```

---

## Audit Log

Every request and response is logged with full policy evaluation detail. This is not optional — it is core.

```json
{
  "request_id":       "3f7a2b1c-...",
  "timestamp":        "2026-06-03T10:24:51Z",
  "app_id":           "customer-chatbot",
  "policy_version":   "1.0.0",
  "profile":          "customer_support",
  "provider":         "bedrock",
  "model_id":         "anthropic.claude-sonnet-4-6",
  "direction":        "input",
  "guard_results": [
    {
      "guard":        "PiiGuard",
      "engine":       "classifier",
      "passed":       false,
      "action":       "block",
      "confidence":   0.97,
      "detail":       "PII detected: [CREDIT_CARD, AADHAAR]",
      "latency_ms":   14
    }
  ],
  "final_decision":   "blocked",
  "total_latency_ms": 14
}
```

Audit logs go to stdout by default, ready to pipe into CloudWatch, Splunk, or any SIEM.

---

## Installation

```bash
# Core package
pip install rampart

# With AWS Bedrock support
pip install rampart[bedrock]

# With Snowflake Cortex support
pip install rampart[cortex]

# With both
pip install rampart[bedrock,cortex]
```

> **Note on first run:** Rampart's built-in guards use local ML models (Microsoft Presidio and LLM Guard). These models — approximately 300MB total — are downloaded automatically on first use and cached locally. No data is sent to any external service during this download or during scanning.

**Requires Python 3.10+**

---

## Error Handling

```python
from rampart import Rampart
from rampart.exceptions import PolicyViolationError, RampartError

client = Rampart(
    policy_registry="file://./policies/banking.yaml",
    provider="bedrock",
    app_id="my-app"
)

try:
    response = client.invoke(
        model_id="anthropic.claude-sonnet-4-6",
        messages=[{"role": "user", "content": user_input}],
        profile="customer_support"
    )

    print(response.text)          # the LLM response
    print(response.request_id)    # UUID — correlate with audit log
    print(response.warnings)      # list of WARN-level findings

except PolicyViolationError as e:
    # A guard with action: block fired
    print(e.request_id)           # for audit log correlation
    print(e.direction)            # "input" or "output"
    print(e.violations)           # list of GuardResult objects

except RampartError as e:
    # Policy load failure, provider error, registry unreachable
    print(e)
```

---

## Architecture

```
Your Application
        │
        │  client.invoke(messages, profile="customer_support")
        ▼
┌───────────────────────────────────────┐
│              Rampart                  │
│                                       │
│  Registry ──▶ PolicyLoader            │
│                    │                  │
│              ┌─────▼──────┐           │
│              │   Profile  │           │
│              └─────┬──────┘           │
│                    │                  │
│         ┌──────────▼──────────┐       │
│         │    Input Pipeline   │       │
│         │  PiiGuard           │       │
│         │  PromptInjection    │       │
│         │  [custom guards]    │       │
│         └──────────┬──────────┘       │
│                    │ clean text       │
└────────────────────┼──────────────────┘
                     │
        ┌────────────▼────────────┐
        │      LLM Provider       │
        │  Bedrock / Cortex /     │
        │  Azure OpenAI           │
        └────────────┬────────────┘
                     │
┌────────────────────┼──────────────────┐
│              Rampart                  │
│                    │ LLM response     │
│         ┌──────────▼──────────┐       │
│         │   Output Pipeline   │       │
│         │  PiiGuard           │       │
│         │  [custom guards]    │       │
│         └──────────┬──────────┘       │
│                    │                  │
│         Audit Log (structured JSON)   │
└────────────────────┼──────────────────┘
                     │
        RampartResponse to your application
```

---

## Writing a Custom Guard

1. Subclass `BaseGuard`
2. Implement `scan(text, context) -> GuardResult`
3. Reference it in your policy YAML by module path

```python
# myapp/guards/internal_topics.py

from rampart import BaseGuard, GuardResult, Action

class InternalTopicGuard(BaseGuard):
    """
    Blocks questions about internal systems, unreleased products,
    or confidential projects by keyword matching.
    """
    def scan(self, text: str, context: dict) -> GuardResult:
        blocked_topics = self.config.get("topics", [])
        text_lower = text.lower()

        found = [t for t in blocked_topics if t.lower() in text_lower]

        if found:
            return GuardResult(
                passed=False,
                action=Action(self.config.get("action", "block")),
                detail=f"Internal topic detected: {found}"
            )

        return GuardResult(
            passed=True,
            action=Action.ALLOW,
            detail="No restricted topics detected"
        )
```

```yaml
# In your policy YAML
- guard: InternalTopicGuard
  module: myapp.guards.internal_topics
  engine: classifier
  action: block
  config:
    topics:
      - Project Phoenix
      - Operation Delta
      - Q4 restructure
```

The `context` dict available inside `scan()` contains:

```python
{
    "user_id":         "hashed-user-id",
    "session_id":      "uuid",
    "app_id":          "customer-chatbot",
    "policy_version":  "1.0.0",
    "profile":         "customer_support",
    "provider":        "bedrock",
    "model_id":        "anthropic.claude-sonnet-4-6",
    "direction":       "input",    # or "output"
    "timestamp":       "2026-06-03T10:24:51Z"
}
```

Use context to write guards that behave differently based on who is asking, which application is calling, or whether you are on the input or output side.

---

## Supported Providers

| Provider | Install extra | Notes |
|---|---|---|
| AWS Bedrock | `pip install rampart[bedrock]` | Uses standard AWS credential chain |
| Snowflake Cortex | `pip install rampart[cortex]` | Requires Snowflake account config |
| Azure OpenAI | `pip install rampart[azure]` | Coming in v0.2 |
| OpenAI | `pip install rampart[openai]` | Coming in v0.2 |

---

## Roadmap

**v0.1 (current)**
- `PiiGuard` and `PromptInjectionGuard` built-in
- File and HTTP policy registries
- AWS Bedrock and Snowflake Cortex providers
- Classifier and hybrid engine modes
- Structured audit log

**v0.2**
- Git policy registry with change detection
- `ToxicityGuard`, `BadWordsGuard`, `SensitiveDataGuard`
- Azure OpenAI and OpenAI providers
- Async client (`AsyncRampart`)
- Policy version pinning and compatibility checks

**v0.3**
- FastAPI gateway mode (deploy Rampart as a shared service)
- Pip-installable thin client for the gateway mode
- Webhook-triggered policy reloads

---

## Contributing

Rampart is at its best when the guard library grows with the community. The easiest contribution is a new guard.

1. Fork the repo
2. Create `rampart/guards/your_guard.py` — subclass `BaseGuard`
3. Add a test in `tests/guards/test_your_guard.py`
4. Add an example policy snippet to `docs/guards/your_guard.md`
5. Open a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

Rampart stands on the shoulders of excellent open source work:

- [Microsoft Presidio](https://github.com/microsoft/presidio) — PII detection and anonymisation
- [LLM Guard](https://github.com/protectai/llm-guard) — input and output scanners
- [Open Policy Agent](https://www.openpolicyagent.org/) — the architectural inspiration

---

*Built for enterprise GenAI teams who need policy enforcement without policy complexity.*
