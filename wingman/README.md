# Wingman: iMessage dating wingman

Text it a screenshot of a chat or a dating profile, a name, or a question. It reads where things
stand (warm / lukewarm / cold), remembers each person, and sends back 3 suggested texts as separate
bubbles so each one copies cleanly, plus the date ask once it's time.

Separate app from the trading agent: own container, own SQLite (`/data/wingman.db`), no shared code.
Same pattern as the Telegram bot: webhook -> background thread -> Claude -> reply.

## Using it

| You send | It does |
|---|---|
| screenshot (+ optional "sarah from hinge") | reads the thread or profile, saves her, 3 options (+ the ask) |
| `sarah?` | next text for Sarah from what it remembers |
| "she left me on read 2 days, now what" | answers, gives options for the active person |
| `make #2 funnier` | rewrites from the last suggestions |
| `sent 2` / `sent: what I actually wrote` | logs what you sent, so it learns the thread and your style |
| `list` · `info sarah` · `use sarah` · `forget sarah` | roster / profile / switch / delete |
| `note sarah: works in PR, loves tequila` | adds a fact |
| `me: 34, Miami Beach, trader, go-to is Broken Shaker, I text short and dry` | about you; used for tone and real plans, never invented |

A screenshot with no name: it gives options, then asks "Who's this?"; reply with her name to
save it. A screenshot and the text right after it (within 4 s) are read together.

## Setup: pick a transport

### A. BlueBubbles (free, needs a Mac that stays on)

1. On the Mac, install BlueBubbles Server (bluebubbles.app), grant the permissions it asks for
   (Full Disk Access, Accessibility), and set a server password.
2. Which Apple ID sends the replies:
   - **Recommended: a separate Apple ID for the bot.** Make a second macOS user, sign that user into
     Messages with the new Apple ID, run BlueBubbles there (fast user switching keeps both
     sessions alive). Save that Apple ID in your phone as "Wingman" and text it.
   - **Or self-chat:** keep the Mac on your own Apple ID and text yourself. Set `BB_SELF_CHAT_GUID`
     to that chat's guid (`iMessage;-;<your number or email>`; BlueBubbles shows it in its chat list
     API). The bot only reads that one chat and ignores its own replies.
3. Give BlueBubbles a public URL: its built-in Cloudflare or ngrok option. A free trycloudflare
   URL changes when the Mac restarts, so use a fixed one (Cloudflare tunnel on your domain, or an
   ngrok static domain), otherwise `BB_URL` goes stale.
4. BlueBubbles > API & Webhooks > add webhook
   `https://wingman.motivationpro.tech/webhook?token=<WINGMAN_WEBHOOK_TOKEN>`, event **New Messages**.

### B. Sendblue (paid, no Mac)

Get a Sendblue number and API keys, set the receive webhook to the same URL as above, and set
`WINGMAN_TRANSPORT=sendblue`, `SB_API_KEY`, `SB_API_SECRET`, `SB_FROM_NUMBER`.
(The Sendblue payload fields are from their docs, so check the first message end to end.)

## Deploy (Coolify, same VPS)

New resource from `jakebasel/fractal-agent`, build pack Dockerfile, **Base Directory `/`,
Dockerfile Location `/wingman/Dockerfile`**, port 8080, persistent volume at `/data`,
domain e.g. `wingman.motivationpro.tech`. Set Watch Paths to `wingman/**` so trading-agent pushes
don't restart it (and add `!wingman/**` on the trading app so wingman pushes don't restart that).

Env:

| var | |
|---|---|
| `ANTHROPIC_API_KEY` | same key as the agent |
| `WINGMAN_WEBHOOK_TOKEN` | any long random string; goes in the webhook URL |
| `WINGMAN_OWNER` | your phone (`+1555...`) or Apple ID email. Leave empty at first: the bot replies with your handle to paste here |
| `WINGMAN_TRANSPORT` | `bluebubbles` (default) or `sendblue` |
| `BB_URL`, `BB_PASSWORD` | BlueBubbles server URL and password |
| `BB_SELF_CHAT_GUID` | only for self-chat mode |
| optional | `WINGMAN_MODEL` (claude-sonnet-5-5), `WINGMAN_EFFORT` (low), `WINGMAN_MAX_PER_DAY` (100), `WINGMAN_DEBOUNCE_S` (4), `WINGMAN_ABOUT_ME` |

Check: `curl https://wingman.motivationpro.tech/health` should show `key_set`, `owner_set` and `token_set` all true.

## Privacy

Screenshots go to the Claude API to be read and are not stored. What's read from them (the
messages, her name, notes) is stored in `/data/wingman.db` on the VPS. `forget <name>` deletes a
person and her whole thread.

## Tests

`python3 tests/test_wingman.py`: fake Claude, fake iMessage, no network.
