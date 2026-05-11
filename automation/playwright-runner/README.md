# playwright-runner

Node.js Playwright service for browser automation tasks.

## API

`POST /run`

```json
{
  "url": "https://example.com",
  "actions": [
    { "type": "click_selector", "selector": "button#start" },
    { "type": "type_selector", "selector": "input[name=q]", "text": "kryos" },
    { "type": "screenshot" },
    { "type": "extract_text", "selector": "h1" }
  ]
}
```

Action types: `navigate`, `click_selector`, `type_selector`, `screenshot`, `extract_text`.
