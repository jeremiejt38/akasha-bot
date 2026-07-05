# WhatsApp bridge scaffold (whatsapp-web.js)

This directory contains a prototype WhatsApp bridge service built with `whatsapp-web.js`.
It is intended to be run as a separate container/service and communicate with the Python bot bridge.

## What this scaffold does
- Starts a WhatsApp Web client using `whatsapp-web.js`
- Prints a QR code in logs/terminal for first-time authentication
- Persists the WhatsApp session under `WA_SESSION_PATH`
- Exposes an HTTP `/send` endpoint to send outbound messages from the Python bridge
- Forwards inbound WhatsApp messages to the Python bridge via `BRIDGE_WEBHOOK_URL`
- Supports basic media forwarding using either inline base64 or temp files for larger media

## Environment variables
- `WA_PORT` (default: `3001`): HTTP port for this service
- `WA_SESSION_PATH` (default: `/app/session`): where the authenticated session is stored
- `WA_MEDIA_TMP_DIR` (default: `/tmp`): temp dir for larger media files
- `WA_MAX_MEDIA_BYTES` (default: `20971520` = 20MB): media over this size is written to disk before forwarding
- `BRIDGE_WEBHOOK_URL` (default: `http://bot:8000/webhooks/whatsapp`): Python bridge webhook endpoint for inbound WA messages
- `BRIDGE_API_TOKEN` (optional): bearer token used to authenticate requests to the Python bridge
- `WA_LOW_POWER` (default: `true`): enables energy-saving browser flags (set to `false` to disable)
- `WA_SKIP_MEDIA` (default: `false`): when `true`, inbound media is not downloaded/forwarded (text only)
- `WA_MESSAGE_PROCESS_DELAY_MS` (default: `0`): artificial delay before forwarding each inbound message, trading speed for lower CPU load
- `WA_JS_HEAP_MB` (default: `512`): Node.js max heap size in megabytes
- `WA_PUPPETEER_ARGS` (optional): override the default Chromium args with a comma-separated list (advanced)

## Low-power mode
By default the bridge runs Chromium with a set of flags that disable GPU, smooth scrolling, background networking, extensions, audio, and other non-essential features to reduce CPU and memory usage. This makes the WhatsApp bridge slower to refresh and forward messages, but keeps it lighter.

## QR code authentication flow
1. Start the `node_whatsapp` service.
2. Watch the logs: the service will print a QR code in ASCII form.
3. On your phone, open WhatsApp > Linked Devices > Link a Device.
4. Scan the QR code shown in logs.
5. Once authenticated, the session is persisted in `WA_SESSION_PATH`.
6. On restart, the QR should not be required again unless the session becomes invalid.

## Suggested docker-compose service snippet
```yaml
whatsapp:
  build: ./node_whatsapp
  container_name: bridge-whatsapp
  environment:
    WA_PORT: 3001
    WA_SESSION_PATH: /app/session
    WA_MEDIA_TMP_DIR: /tmp
    WA_MAX_MEDIA_BYTES: 20971520
    BRIDGE_WEBHOOK_URL: http://bot:8000/webhooks/whatsapp
    BRIDGE_API_TOKEN: change-me-if-you-secure-the-webhook
  volumes:
    - ./node_whatsapp/session:/app/session
    - ./data/tmp:/tmp
  restart: unless-stopped
```

## Test plan (step-by-step)
1. Build and start the service:
   - `docker compose up --build whatsapp`
2. Scan the QR code from logs.
3. Send a text message from your phone to the linked WhatsApp account.
4. Verify the Python bridge receives a webhook call and creates/reuses a Discord channel `[WA]...`.
5. Reply in Discord as admin and verify the message is delivered via `POST /send` to the WhatsApp service.
6. Send a small image/video and confirm it reaches Discord.
7. Send a larger file and confirm it is staged to disk (`WA_MEDIA_TMP_DIR`) instead of staying fully in memory.
8. Restart the container and confirm the session persists without rescanning the QR.

## Important notes
- `whatsapp-web.js` is not an official WhatsApp Business API. Use it for prototypes/testing at your own risk.
- Automation through WhatsApp Web may violate WhatsApp terms and can result in account restrictions or bans.
- For production/business-critical use, prefer the official WhatsApp Business API when possible.
- This scaffold expects a Python bridge webhook endpoint to exist; that endpoint still needs to be implemented in the Python bot service.
