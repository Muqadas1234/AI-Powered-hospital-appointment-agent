# Vapi Phase 2 Setup

## 1) Expose backend to internet

Vapi tools require a public HTTPS URL.

Example with ngrok:

```bash
ngrok http 8000
```

Use the HTTPS URL (example `https://abc123.ngrok-free.app`) in all tool URLs.

## 2) Update tool URLs

In `vapi/tools.json`, replace:

- `http://127.0.0.1:8000`

with your public backend URL.

## 3) Create assistant in Vapi

- Model: OpenAI (recommended GPT-4.1 family)
- Voice: any conversational voice
- System prompt: paste from `vapi/assistant_prompt.txt`
- Tools: add each tool from `vapi/tools.json`
- Webhook URL: `https://<your-url>/api/v1/vapi/webhook`

## 4) Frontend setup

In `frontend/.env`:

- `VITE_VAPI_PUBLIC_KEY=<your-public-key>`
- `VITE_VAPI_ASSISTANT_ID=<assistant-id>`

Then run:

```bash
npm run dev
```

## 5) Test call flow

Try:
- "What are your timings?"
- "Book a dentist appointment tomorrow morning"

The backend should:
- fetch providers and slots
- check conflicts
- book appointment
- attempt calendar sync
