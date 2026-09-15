# ERPNext AI

AI Assistant for ERPNext. Adds a chat button to query your ERP data using natural language.

## Installation

```bash
bench get-app https://github.com/jeecsh/erpnext_ai
bench --site your-site.com install-app erpnext_ai
bench build
bench restart
```

## Configuration

Edit `erpnext_ai/public/js/erpnext_ai.js` to change the AI backend URL:

```javascript
const AI_URL = "https://ai.nos-lab.com/chat";
```

## How it works

1. Injects a floating chat button into ERPNext
2. When user opens chat, automatically gets their API credentials
3. Credentials are passed to the AI backend via postMessage
4. AI queries ERPNext with user's permissions

## License

MIT
