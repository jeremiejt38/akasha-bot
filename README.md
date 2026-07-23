# Multiplaform Bridge Inbox - Discord unified inbox bot

![Version](https://img.shields.io/badge/version-0.41.6-blue)

Bot Discord Python servant de bridge de messagerie unifiée.

This bot centralizes inbound messages from several platforms (Telegram, WhatsApp, Instagram, Facebook Messenger, Snapchat, TikTok) into a single Discord server, creating one channel per user and per platform.

## What it does
- Ensures a Discord category named `INBOX` exists.
- Creates/reuses per-user channels using a platform marker (e.g. `tl-jean`, `wa-jean`).
- Forwards inbound messages from platforms to Discord (text + media where supported).
- Forwards admin replies in Discord back to the correct platform user.

## Supported platforms
- **Telegram**: text + media via `python-telegram-bot` v20.
- **WhatsApp**: separate Node bridge using `whatsapp-web.js`, with a low-power/energy-saving mode enabled by default.
- **Instagram**: Meta Messaging Graph API (webhook + reply).
- **Facebook Messenger**: Meta Messaging Graph API (webhook + reply).
- **Snapchat / TikTok**: HTTP bridge skeleton expecting a separate automation service at `SNAPCHAT_SERVICE_URL` / `TIKTOK_SERVICE_URL` (no official public DM API).

## Quick start
1. Copy `.env.example` to `.env` and fill in the required values.
2. Build and run with Docker Compose:
   ```bash
   docker compose up --build
   ```

## Development with Lando
The project can also be run with Lando. It starts a Python `bot` service (code mounted from the host) and a `whatsapp` service built from the existing `node_whatsapp/Dockerfile` (the WhatsApp code is baked into the image, so run `lando rebuild` after editing it).

1. Copy `.env.example` to `.env` and fill it in.
2. Start the environment:
   ```bash
   lando start
   ```
3. The webhook server is exposed at `https://bot.akasha.ing` (Lando proxy forwards to the bot's internal port `8000`).
4. Useful commands:
   ```bash
   lando check      # Python syntax check inside the bot container
   lando python     # run Python inside the bot container
   lando pip        # run pip inside the bot container
   lando rebuild    # rebuild services after changing WhatsApp code or Dockerfile
   ```

For plain Docker Compose usage, the project still provides a `docker-compose.yml` and a `docker-compose.override.yml` that loads `.env` into the containers.

## Production deployment with Traefik

For deployment behind an existing Traefik reverse proxy (e.g. on the Akasha server):

1. Ensure a Docker network named `plex-backend` exists:
   ```bash
   docker network create plex-backend
   ```
2. Copy `.env.example` to `.env` and fill it in. Keep the Docker service defaults:
   - `WHATSAPP_SERVICE_URL=http://whatsapp:3001`
   - `BRIDGE_WEBHOOK_URL=http://bot:8000/webhooks/whatsapp`
3. Adjust the Traefik labels in `docker-compose.yml` if your cert resolver is not named `letsencrypt`.
4. Start the stack:
   ```bash
   docker compose up -d --build
   ```

The bot will be available at `https://bot.akasha.ing` and Meta webhooks should point to `https://bot.akasha.ing/webhooks/meta`.

## Auto-responder configuration

The auto-responder Q&A is stored in `config/auto_responses.json` instead of Python code. This makes it easy to add or edit answers without touching the codebase.

Format of an entry:

```json
{
  "patterns": ["mot", "phrase équivalente"],
  "answer": "Réponse statique"
}
```

Or with user-data templating:

```json
{
  "patterns": ["mon compte expire quand"],
  "template": "Ton compte est actif jusqu'au {wizarr_invite_expires:%d/%m/%Y}.",
  "fallback": "Je n'ai pas trouvé d'invitation liée à ton compte.",
  "needs_user": true
}
```

Special markers:

```json
{
  "patterns": ["problème connexion"],
  "marker": "connection_check"
}
```

Change the path with `AUTO_RESPONDER_DATA_PATH` in `.env`.

## Tests / checks
Run syntax checks directly on the host (no Lando needed):

```bash
python3 -m py_compile main.py discord_bot.py database.py webhook_server.py integrations/*.py platforms/*.py tests/*.py
node --check node_whatsapp/index.js
```

Run the small pytest suite:

```bash
pytest tests -q
```

## Subscriber commands

Available slash commands for members:

- **`/account`** — Displays linked account info: email, Plex username, Wizarr invitation expiration date, trust score, and quick links to Plex, Jellyfin and Seerr.
- **`/request <title>`** — Searches Overseerr and creates a media request after confirmation.
- **`/renew`** — Requests a subscription renewal. Stores the request and notifies the admin.
- **`/support <sujet> <description>`** — Opens a support ticket that is sent to the admin by DM.
- **`/feedback <message>`** — Sends anonymous feedback to the admin.
- **`/faq`** — Displays frequently asked questions from the auto-responder knowledge base.
- **`/link <email>`** — Links your Discord account to your Seerr account directly (alternative to the onboarding modal).
- **`/status`** — Shows the health status of Akasha services (Plex, Jellyfin, Seerr, Wizarr, website).

## Admin commands

- **`/dashboard`** — Opens an interactive admin dashboard (admin only) with buttons to switch between:
  - **Vue globale** — total subscribers, upcoming expirations, average trust score
  - **Abonnés** — paginated list with email, signup date, expiration, accumulated months, trust score
  - **Expirations** — members expiring within 7 days
  - **Demandes** — pending Overseerr requests
  - **Trust bas** — members with low trust score
  - **Stats** — overall statistics
  - **Renouvellements** — pending renewal requests from `/renew`
- **`/reload`** — Reloads the auto-responder configuration from `config/auto_responses.json` without restarting the bot (admin only).
- **`/note <@membre> <texte>`** — Adds a private admin note on a subscriber (admin only). Notes are visible in the `/dashboard` subscriber list.
- **`/sync [@membre]`** — Synchronizes one subscriber or all subscribers with Overseerr: updates Discord ID, username, Plex username and (re)assigns the member role (admin only).
- **`/export`** — Exports the subscriber list as a CSV file (admin only). Includes Discord ID, username, email, Plex username, signup date, expiration, accumulated months, trust score, admin notes and renewal status.
- **`/invitations [statut]`** — Lists Wizarr invitations filtered by status (`all`, `unused`, `used`, `expired`) and lets you revoke them with a button (admin only).
- **`/logs [limite]`** — Shows recent audited actions: invitations, renewals, syncs, notes, role revocations, etc. (admin only).
- **`/poll <question> <option1> <option2> [option3] [option4]`** — Creates a simple poll with up to 4 options. Users vote by clicking buttons and results update live (admin only).
- **`/services`** — Shows the status and version of monitored Akasha services (Plex, Jellyfin, Overseerr, Wizarr, website) (admin only).
- **`/stats`** — Shows advanced subscriber statistics: total, active, expired, pending renewals, expiring within 7/30 days, new this month, average trust score (admin only).

## Discord community onboarding

For community-enabled Discord servers, the bot can automate member onboarding:

1. When a user joins the guild (`on_member_join`) or finishes Discord's native onboarding (`on_member_update` with `completed_onboarding`), the bot sends them a DM.
2. The bot first checks its local database and Overseerr for a linked Discord ID.
3. If the account is already known, the bot assigns the configured member role (`Abonné` by default) and sends a welcome confirmation DM.
4. If not, the bot sends a DM with a **"Lier mon compte Seerr"** button that opens an email modal.
5. The email is verified against Overseerr:
   - **Found**: the Discord ID is synced to Overseerr, the user is stored locally, the member role is assigned, and a confirmation DM is sent.
   - **Not found**: the user is offered a link to create an account on Seerr (`https://s.akasha.ing`) and can retry.

Configure with:

```env
BOT_NAME=Akasha
ONBOARDING_DM_ENABLED=true
MEMBER_ROLE_NAME=Abonné
CREATE_MEMBER_ROLE=true
SEERR_SIGNUP_URL=https://s.akasha.ing
SUPPORT_DM_ENABLED=true
```

`BOT_NAME` is used in DMs, embeds and notifications so the bot is identified consistently across the server.

## Support DMs

When a member DMs the bot and the auto-responder does not match a known answer, the bot forwards the message to an admin channel/DM so a human can reply. The conversation still creates an INBOX channel like any other platform.

## Automatic expiration alerts

The bot runs a daily background task that checks Wizarr invitation expiration dates and alerts the admin (and optionally the subscriber) when a membership is about to expire or has already expired.

Configure with:

```env
EXPIRATION_WARNING_DAYS=7
EXPIRATION_ALERT_HOUR=9
EXPIRATION_NOTIFY_SUBSCRIBERS=true
```

- `EXPIRATION_WARNING_DAYS` — number of days before expiration to trigger an alert
- `EXPIRATION_ALERT_HOUR` — UTC hour at which the daily check runs
- `EXPIRATION_NOTIFY_SUBSCRIBERS` — also DM affected subscribers if `true`
- `REVOKE_ROLE_ON_EXPIRATION` — automatically remove the member role from expired subscribers if `true`

## Media webhook notifications

You can configure Plex and Jellyfin to send webhook events to the bot when a new item is added. The bot will post a Discord embed to the configured channel.

Configure the following environment variables:

```env
PLEX_WEBHOOK_CHANNEL_ID=123456789012345678
JELLYFIN_WEBHOOK_CHANNEL_ID=123456789012345678
```

Then point your server webhooks to:

- Plex: `https://bot.akasha.ing/webhooks/plex`
- Jellyfin: `https://bot.akasha.ing/webhooks/jellyfin`

Supported events:

- **Plex**: `library.new`, `media.scrobble`
- **Jellyfin**: `ItemAdded`, `PlaybackStart`
- **Overseerr**: `MEDIA_REQUESTED`, `MEDIA_APPROVED`, `MEDIA_AVAILABLE`, `MEDIA_REJECTED`, etc.

Configure the Overseerr notification channel:

```env
OVERSEERR_WEBHOOK_CHANNEL_ID=123456789012345678
```

Then point the Overseerr webhook to `https://bot.akasha.ing/webhooks/overseerr`. The bot will post an embed in the configured channel for every Overseerr notification, and DM the requesting user when a requested media becomes available (`MEDIA_AVAILABLE`).

## Admin notifications

All admin notifications (expiration alerts, auto-sync errors, support tickets, feedback, renewal requests) are sent to the configured admin log channel if `ADMIN_LOG_CHANNEL_ID` is set. If not, they fall back to a DM to the admin (`ADMIN_DISCORD_ID`).

```env
ADMIN_LOG_CHANNEL_ID=123456789012345678
```

## Critical alerts

Critical alerts (service outages, failed auto-sync, etc.) are sent to a dedicated channel via `CRITICAL_LOG_CHANNEL_ID`. Unlike the admin log channel, critical logs are reserved for serious issues that require immediate attention and do not fall back to DM.

```env
CRITICAL_LOG_CHANNEL_ID=123456789012345678
SERVICE_HEALTH_CHECK_INTERVAL_MINUTES=5
```

## Automatic synchronization

The bot runs a background sync job every `AUTO_SYNC_INTERVAL_HOURS` hours (default 24). It synchronizes all known subscribers with Overseerr (updates Discord ID, usernames, Plex username) and reassigns the member role if missing. The admin is notified by DM if any sync fails.

Configure with:

```env
AUTO_SYNC_INTERVAL_HOURS=24
```

## Debug mode
Set `DEBUG=true` in `.env` to enable verbose logging. In debug mode, the bot prints:

- startup configuration and enabled platforms
- every incoming webhook and its platform
- Discord admin replies being forwarded back to platforms
- channel resolution and creation
- full tracebacks for errors

## WhatsApp low-power mode
The WhatsApp bridge now runs Chromium with energy-saving flags (GPU disabled, no audio, no extensions, background networking disabled, etc.) and caps the Node.js heap. You can slow it down further with `WA_MESSAGE_PROCESS_DELAY_MS` or skip media downloads with `WA_SKIP_MEDIA`. See `.env.example` and `node_whatsapp/README.md` for details.

## Meta (Instagram & Facebook Messenger)

Configure the Meta webhook endpoint once for both platforms.

1. Create a Facebook App and enable **Messenger** and/or **Instagram** products.
2. Generate a **Page Access Token** (`META_PAGE_ACCESS_TOKEN`) for the linked Facebook Page.
3. Set `META_VERIFY_TOKEN` to a secret value used by Meta to verify the webhook URL.
4. Configure the webhook in the Meta Developer portal:
   - Callback URL: `https://bot.akasha.ing/webhooks/meta`
   - Verify token: the value of `META_VERIFY_TOKEN`
   - Subscribe to `messages` and `messaging_postbacks` events.
5. For Instagram, set `INSTAGRAM_BUSINESS_ACCOUNT_ID` to the Instagram Business Account ID linked to the page.
6. For Facebook Messenger, set `FACEBOOK_PAGE_ID` to the page ID.

Inbound messages are routed automatically based on the webhook payload (`object: instagram` or `object: page`).

## Security
Do NOT commit real credentials. Use `.env` and a proper secrets manager for production.

## Changelog

### v0.41.x ← *actuel*

- **feat: synchronisation automatique des invitations Wizarr consommées et cycle d’accès membre V1**
- **feat: traçabilité des échecs de livraison INBOX et sauvegarde SQLite vérifiée**
- **feat: profil Akasha multi-plateforme et respect des préférences DM Seerr**
- **security: vérification des signatures de webhooks Meta**
- **fix: stabilité des canaux Telegram, activation des réponses automatiques et masquage des jetons dans les logs**
- **fix: envoi du QR WhatsApp via le service Docker interne**
- **fix: appairage WhatsApp avec QR image PNG en DM Discord**

### v0.40.x

- **feat: essais et invitations INBOX avec prolongation Wizarr et liaison des identités externes**

### v0.39.x

- **feat: tableau Administration/services avec suivi Docker Unraid, IP, ports, uptime et alertes après 2 minutes**
- **fix: tableau services condensé et vérification des mises à jour par digest de registre**
- **fix: permissions centralisées et synchronisées pour toute la catégorie Administration**

### v0.38.x

- **feat: statistiques Tautulli par e-mail dans mon-compte et toggles DM directs**

### v0.37.x

- **feat: salon mon-compte avec statistiques personnelles, expiration et préférences DM**
- **fix: format uniforme des dates membre et signalements en JJ/MM/AA**
- **fix: replace le panneau mon-compte en dernier message après chaque interaction**

### v0.36.x

- **feat: signalements Discord unifiés avec sources Plex, Seerr et Discord**
- **feat: réponses et statuts synchronisés avec les issues Seerr et les commentaires Plex**
- **feat: panneau administrateur avec filtres, fermeture et réouverture des signalements**
- **feat: parcours membre paginé pour médias, saisons et épisodes**
- **feat: notifications DM pour nouveaux signalements, réponses et changements de statut**
- **fix: affiche explicitement la description originale dans les signalements membre et administrateur**
- **fix: tableau administrateur non éphémère et import de l'historique Plex/Seerr, y compris fermé**
- **fix: rapproche les issues Seerr par l'identifiant créateur lorsque les IDs Discord ne sont pas inclus**
- **fix: migre les anciennes tables utilisateurs pour permettre la liaison Seerr/Discord**
- **feat: migrations SQLite versionnées et idempotentes pour les mises à jour de schéma**
- **fix: tableau administrateur persistant, trié chronologiquement et filtre actif mis en évidence**

### v0.35.x

- **feat: onboarding géré par Akasha-bot avec salon de vérification, rôles temporaires et modal de liaison Seerr**
- **feat: rôles Essai, Abonné et Expiré synchronisés depuis les invitations Wizarr**
- **feat: salon privé d'expiration avec procédure de renouvellement**
- **fix: détection des comptes Discord déjà liés dans Seerr**
- **chore: déploiements Unraid incrémentaux et contexte Docker optimisé**

### v0.34.x

- **feat**: canal de logs critiques `CRITICAL_LOG_CHANNEL_ID` pour les alertes importantes
- **feat**: surveillance automatique des services avec alertes critiques si un service passe hors ligne
- **fix**: suppression du doublon d'enregistrement de la commande `/link`
- **fix**: correction de la syntaxe du healthcheck docker-compose
- **chore**: ajout des labels d'icône Unraid pour les conteneurs
- **ci: workflow GitHub Actions pour publier l'image Docker sur GHCR**
- **ci: workflow GitHub Actions pour publier l'image WhatsApp bridge sur GHCR**
- **fix: amélioration des logs de l'auto-responder et ajout du lien du channel dans les notifications admin**

### v0.33.x

- **feat**: commande `/link <email>` pour lier son compte Seerr sans passer par le modal
- **feat**: amélioration du message de bienvenue avec la liste des commandes disponibles
- **feat**: statut Discord affichant la version du bot récupérée dans `pyproject.toml`

### v0.32.x

- **feat**: commande admin `/stats` avec statistiques avancées des abonnés

### v0.31.x

- **feat**: canal de log admin `ADMIN_LOG_CHANNEL_ID` pour centraliser les notifications admin
- **feat**: commande admin `/services` pour surveiller l'état et les versions des services Akasha

### v0.30.x

- **feat**: commande admin `/poll` pour créer des sondages interactifs avec jusqu'à 4 options

### v0.29.x

- **feat**: endpoint webhook Overseerr (`/webhooks/overseerr`) pour les notifications de demandes et médias disponibles
- **feat**: notification DM automatique à l'abonné quand son média demandé est disponible

### v0.28.x

- **feat**: commande abonné `/feedback <message>` pour envoyer un feedback anonyme à l'admin

### v0.27.x

- **feat**: endpoints webhook Plex (`/webhooks/plex`) et Jellyfin (`/webhooks/jellyfin`) pour les notifications de nouveau média
- **feat**: envoi d'embeds Discord dans les channels configurés lors d'ajout de média

### v0.26.x

- **feat**: table `audit_logs` et commande admin `/logs [limite]` pour consulter l'historique
- **feat**: traçage des actions clés : invitations, renouvellements, sync, notes, révocations

### v0.25.x

- **feat**: commande admin `/invitations [statut]` pour lister et révoquer les invitations Wizarr

### v0.24.x

- **feat**: commande abonné `/faq` pour afficher les questions fréquentes de l'auto-responder

### v0.23.x

- **feat**: commande abonné `/support <sujet> <description>` pour ouvrir un ticket support auprès de l'admin

### v0.22.x

- **feat**: commande admin `/export` pour exporter la liste des abonnés en CSV

### v0.21.x

- **feat**: révocation automatique du rôle membre à l'expiration de l'abonnement
- **feat**: variable `REVOKE_ROLE_ON_EXPIRATION` pour activer/désactiver la révocation

### v0.20.x

- **feat**: synchronisation automatique avec Overseerr en arrière-plan toutes les X heures
- **feat**: notification admin en cas d'échec du sync automatique

### v0.19.x

- **feat**: commande abonné `/renew` pour demander le renouvellement de l'abonnement
- **feat**: notification admin et vue "Renouvellements" dans le `/dashboard`

### v0.18.x

- **feat**: commande admin `/sync` pour synchroniser un ou tous les abonnés avec Overseerr
- **feat**: service `SyncService` qui met à jour les infos utilisateurs, le Discord ID et réattribue le rôle membre

### v0.17.x

- **feat**: commande admin `/note` pour ajouter des notes privées sur les abonnés
- **feat**: affichage des notes admin dans la liste des abonnés du `/dashboard`

### v0.16.x

- **feat**: alertes automatiques d'expiration des abonnements — tâche quotidienne qui notifie l'admin et optionnellement les abonnés

### v0.15.x

- **feat**: commande admin `/reload` pour recharger `config/auto_responses.json` sans redémarrer le bot

### v0.14.x

- **feat**: tableau de bord admin interactif `/dashboard` avec vue globale, liste abonnés, expirations, demandes, trust score et statistiques
- **feat**: ajout des champs `created_at` et `months_subscribed` dans la base users
- **feat**: suivi automatique des mois cumulés lors de la création d'invitation

### v0.13.x

- **feat**: commandes abonnés `/account`, `/request <titre>` et `/status`
- **feat**: méthodes Overseerr `search_media` et `request_media`
- **test**: tests unitaires pour le client Overseerr

### v0.12.x

- **feat**: onboarding automatique Discord — détection nouveaux membres, vérification compte Seerr, attribution du rôle `Abonné`, modal email et DM de confirmation
- **feat**: support DM avec notification admin quand l'auto-respondant n'a pas de réponse
- **feat**: configuration `BOT_NAME=Akasha` utilisée dans tous les messages du bot
- **feat**: auto-responder externalisé dans `config/auto_responses.json` avec templating et reload à chaud
- **docs**: ajout des liens Plex (`p.akasha.ing`) et Jellyfin (`j.akasha.ing`) dans les messages

## Roadmap

### Pré-v1.0.0

- [x] Onboarding automatique Discord avec rôle membre
- [x] Auto-responder externalisé et éditable sans code
- [x] Liaison Overseerr/Seerr via `/link`
- [x] Gestion des invitations Wizarr via `/invite`
- [x] Inbox unifiée multi-plateformes
- [ ] Commande admin de reload de l'auto-responder sans redémarrage
- [ ] Statistiques d'utilisation des réponses auto-respondant
- [ ] Support multi-guildes

### Post-v1.0.0

- [ ] Panneau web de configuration
- [ ] Logs et monitoring avancés
