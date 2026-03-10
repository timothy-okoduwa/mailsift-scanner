# MailSift Scanner API

FastAPI + Playwright scanner that checks domains for webmail/mail login pages.

## Endpoints

- `GET /health` — health check
- `POST /scan` — scan emails

### POST /scan

```json
{
  "emails": ["user@example.com", "user@domain.com"],
  "mode": "webmail"
}
```

Mode options: `"webmail"`, `"mail"`, `"both"`

### Response

```json
{
  "results": [
    {
      "email": "user@example.com",
      "hasWebmail": true,
      "webmailUrl": "https://webmail.example.com/",
      "hasMail": false,
      "mailUrl": null
    }
  ]
}
```

## Deploy on Render

1. Push this folder to a GitHub repo
2. Go to render.com → New Web Service → connect repo
3. Render auto-detects render.yaml and configures everything
4. Copy the deployed URL into your Next.js SCANNER_API_URL env var
