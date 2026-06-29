const fs = require('fs');
const path = require('path');
const express = require('express');
const axios = require('axios');
const qrcode = require('qrcode-terminal');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');

const PORT = process.env.WA_PORT || 3001;
const BRIDGE_API_TOKEN = process.env.BRIDGE_API_TOKEN || '';
const BRIDGE_WEBHOOK_URL = process.env.BRIDGE_WEBHOOK_URL || 'http://bot:8000/webhooks/whatsapp';
const SESSION_PATH = process.env.WA_SESSION_PATH || '/app/session';
const MEDIA_TMP_DIR = process.env.WA_MEDIA_TMP_DIR || '/tmp';
const MAX_MEDIA_BYTES = parseInt(process.env.WA_MAX_MEDIA_BYTES || '20971520', 10); // 20 MB default

fs.mkdirSync(SESSION_PATH, { recursive: true });
fs.mkdirSync(MEDIA_TMP_DIR, { recursive: true });

const app = express();
app.use(express.json({ limit: '25mb' }));

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  puppeteer: {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  }
});

function authHeaders() {
  const headers = {};
  if (BRIDGE_API_TOKEN) {
    headers['Authorization'] = `Bearer ${BRIDGE_API_TOKEN}`;
  }
  return headers;
}

async function postInboundToBridge(payload) {
  try {
    await axios.post(BRIDGE_WEBHOOK_URL, payload, {
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders()
      },
      timeout: 30000
    });
    console.log('[WA] Forwarded inbound message to bridge');
  } catch (err) {
    console.error('[WA] Failed to post inbound message to bridge:', err.message);
  }
}

client.on('qr', (qr) => {
  console.log('[WA] Scan this QR code with WhatsApp to authenticate:');
  qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
  console.log('[WA] WhatsApp client is ready');
});

client.on('authenticated', () => {
  console.log('[WA] Authenticated successfully');
});

client.on('auth_failure', (msg) => {
  console.error('[WA] Authentication failed:', msg);
});

client.on('disconnected', (reason) => {
  console.warn('[WA] Client disconnected:', reason);
});

client.on('message', async (message) => {
  try {
    const chat = await message.getChat();
    const contact = await message.getContact();
    const displayName = contact.pushname || contact.name || contact.number || 'unknown';
    const platformUserId = contact.id && contact.id._serialized ? contact.id._serialized : contact.number;
    const payload = {
      platform: 'WA',
      platform_user_id: platformUserId,
      display_name: displayName,
      text: message.body || '',
      attachments: []
    };

    if (message.hasMedia) {
      try {
        const media = await message.downloadMedia();
        if (media && media.data) {
          const buffer = Buffer.from(media.data, 'base64');
          if (buffer.length <= MAX_MEDIA_BYTES) {
            payload.attachments.push({
              filename: media.filename || `wa_${message.id.id}`,
              mime_type: media.mimetype,
              base64: media.data
            });
          } else {
            const ext = (media.mimetype || 'application/octet-stream').split('/')[1] || 'bin';
            const filePath = path.join(MEDIA_TMP_DIR, `wa_${message.id.id}.${ext}`);
            fs.writeFileSync(filePath, buffer);
            payload.attachments.push({
              filename: media.filename || path.basename(filePath),
              mime_type: media.mimetype,
              path: filePath
            });
          }
        }
      } catch (err) {
        console.error('[WA] Failed to download inbound media:', err.message);
      }
    }

    await postInboundToBridge(payload);
  } catch (err) {
    console.error('[WA] Error handling inbound message:', err.message);
  }
});

app.get('/health', (req, res) => {
  res.json({ ok: true });
});

app.post('/send', async (req, res) => {
  const { platform_user_id, text, attachments = [] } = req.body || {};
  if (!platform_user_id) {
    return res.status(400).json({ error: 'platform_user_id is required' });
  }

  try {
    const target = platform_user_id;

    if (attachments.length > 0) {
      for (let i = 0; i < attachments.length; i++) {
        const att = attachments[i];
        const caption = i === 0 ? (text || '') : undefined;

        if (att.base64) {
          const media = new MessageMedia(att.mime_type || 'application/octet-stream', att.base64, att.filename || 'file');
          await client.sendMessage(target, media, { caption });
        } else if (att.path) {
          const fileBuffer = fs.readFileSync(att.path);
          const base64 = fileBuffer.toString('base64');
          const media = new MessageMedia(att.mime_type || 'application/octet-stream', base64, att.filename || path.basename(att.path));
          await client.sendMessage(target, media, { caption });
        }
      }
    } else if (text) {
      await client.sendMessage(target, text);
    }

    return res.json({ ok: true });
  } catch (err) {
    console.error('[WA] Failed to send outbound message:', err.message);
    return res.status(500).json({ error: err.message });
  }
});

client.initialize().catch((err) => {
  console.error('[WA] Failed to initialize client:', err.message);
  process.exit(1);
});

app.listen(PORT, () => {
  console.log(`[WA] HTTP bridge listening on port ${PORT}`);
});
