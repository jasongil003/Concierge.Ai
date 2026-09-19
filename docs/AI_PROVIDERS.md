# AI Provider and Routing Design

Concierge.Ai is provider-independent. A hotel can use local AI only, a public AI API, a private compatible endpoint, or a hybrid/automatic policy.

## Supported modes

| Mode | Behavior |
| --- | --- |
| `local` | Ollama/local model only |
| `gemini` | Google Gemini only |
| `openai` | OpenAI only |
| `compatible` | Any OpenAI-compatible endpoint such as vLLM, LM Studio, OpenRouter, or a private gateway |
| `hybrid` | Prefer local for routine work and escalate complex/live requests to configured remote providers |
| `auto` | Dynamically route based on request complexity and live-data requirements |

## Guest-facing switch

Guests do not choose vendors.

They see:

- **Fast** - minimum reasoning, optimized for latency
- **Auto** - recommended default; automatically escalates when needed
- **Advanced** - stronger reasoning for complex planning or troubleshooting

A property administrator can disable the switch and force a policy.

## Recommended commercial default

```text
FAQ / cache
    |
    +--> direct answer

Simple conversational request
    |
    +--> local Qwen3 8B or low-cost public model

Complex planning / recommendation
    |
    +--> Gemini 3.8 Flash / GPT-5.6 Terra / configured advanced provider

Live restaurant or place request
    |
    +--> Google Places
            |
            v
        verified place data
            |
            v
        selected AI model
```

The LLM must not invent restaurants, ratings, opening hours, prices, or addresses. Live recommendations should be grounded in a places provider or a hotel-curated local database.

## Environment examples

### Local only

```env
AI_PROVIDER_MODE=local
OLLAMA_MODEL=qwen3:8b
```

### Gemini

```env
AI_PROVIDER_MODE=gemini
GEMINI_API_KEY=...
GEMINI_FAST_MODEL=gemini-3.5-flash-lite
GEMINI_ADVANCED_MODEL=gemini-3.8-flash
```

### OpenAI

```env
AI_PROVIDER_MODE=openai
OPENAI_API_KEY=...
OPENAI_FAST_MODEL=gpt-5.6-luna
OPENAI_ADVANCED_MODEL=gpt-5.6-terra
```

### OpenAI-compatible/private server

```env
AI_PROVIDER_MODE=compatible
COMPATIBLE_API_BASE_URL=http://10.30.20.60:8000
COMPATIBLE_FAST_MODEL=my-fast-model
COMPATIBLE_ADVANCED_MODEL=my-advanced-model
```

### Hybrid

```env
AI_PROVIDER_MODE=hybrid
OLLAMA_MODEL=qwen3:8b
GEMINI_API_KEY=...
```

## Nearby recommendations

Set the hotel coordinates and configure Google Places:

```env
GOOGLE_PLACES_API_KEY=...
PLACES_RADIUS_METERS=5000
PLACES_MAX_RESULTS=6
```

When a guest asks for nearby dining, cafes, pharmacies, shopping, or attractions, Concierge.Ai can fetch current nearby results and supply those verified results to the AI.

The hotel coordinates should come from property configuration, not from the guest's precise device location unless the guest explicitly opts into a location-aware feature.
