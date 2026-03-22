# Joplin phone bridge

Small FastAPI backend so your **phone** can update **Joplin** notes via **OpenAI**, without talking to Joplin Desktop directly.

## Architecture

1. **Phone** → HTTPS → **this backend** (run on your always-on machine or behind a reverse proxy).
2. **Backend** → **OpenAI Responses API** (structured JSON edit proposal).
3. **Backend** → **Joplin Desktop Web Clipper / Data API** on the same always-on machine (default `http://127.0.0.1:41184`).
4. **Joplin Desktop** syncs to your **self-hosted Joplin Server** as usual.

This app does **not** talk to Joplin Server’s API. It only talks to the **Desktop Data API** exposed by Joplin while it is running with Web Clipper / Data API enabled.

## Setup

```bash
cd /path/to/joplin_connector
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your keys (see below). Values are read from the **project root** (the directory that contains `app/`), not from your shell’s current working directory.

### Joplin Desktop

On the machine where Joplin runs:

1. Open **Options → Web Clipper**.
2. Enable the **Web Clipper service** / **Data API** and copy the **token**.
3. Ensure the port matches `JOPLIN_BASE_URL` (often `41184`).

Create a notebook for new notes and copy its **folder id** (e.g. from Joplin’s Data API or dev tools). Set `JOPLIN_DEFAULT_PARENT_ID` if you want `POST /notes/create` without sending `parent_id` each time.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `OPENAI_MODEL` | No | Default `gpt-4o` |
| `JOPLIN_BASE_URL` | No | Default `http://127.0.0.1:41184` |
| `JOPLIN_TOKEN` | Yes | Data API token from Joplin |
| `JOPLIN_DEFAULT_PARENT_ID` | No | Notebook id for `/notes/create` when `parent_id` is omitted |

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000/docs` for interactive OpenAPI.

**Production hint:** Put the app behind TLS (Caddy, nginx, Traefik) and add authentication; this MVP does not include API keys for clients.

## Error responses

HTTP 4xx/5xx responses use a single JSON shape (validation errors included):

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "No note with title 'Shopping'"
  }
}
```

Common `code` values: `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `BAD_GATEWAY`. Successful responses are **not** wrapped (they return the resource body directly, e.g. `JoplinNote` or `PreviewEditResponse`).

## Request / response examples

Replace `YOUR_NOTEBOOK_ID` with a real Joplin folder id. Field limits: `note_title` ≤ 500 chars, `instruction` ≤ 8000, markdown bodies ≤ 1,000,000 chars.

### `GET /health`

**Response `200`**

```json
{
  "status": "ok",
  "joplin": "JoplinClipperServer"
}
```

If Joplin is down, `status` may be `degraded` and `joplin` set to `unavailable`.

### `GET /notes/by-title/{title}`

**Response `200`**

```json
{
  "id": "abc123…",
  "parent_id": "notebook-id",
  "title": "Reading List",
  "body": "# Reading List\n\n## Queue\n- Saturn Run\n"
}
```

### `POST /notes/create`

**Request**

```json
{
  "note_title": "Reading List",
  "markdown": "# Reading List\n\n## Queue\n",
  "parent_id": "YOUR_NOTEBOOK_ID"
}
```

**Response `201`:** same shape as `JoplinNote` above.

If `parent_id` is omitted, set `JOPLIN_DEFAULT_PARENT_ID` in `.env` or the API returns `422` with `VALIDATION_ERROR`.

### `POST /notes/preview-edit`

**Request**

```json
{
  "note_title": "Reading List",
  "instruction": "Add The Gone World to my Reading List queue and clean up formatting"
}
```

**Response `200`**

```json
{
  "title": "Reading List",
  "current_markdown": "# Reading List\n…",
  "updated_markdown": "# Reading List\n…",
  "summary": "Added The Gone World to Queue and normalized list formatting.",
  "changed": true
}
```

The backend first tries to parse the model’s JSON strictly (including stripping optional ` ``` ` fences and scanning for a balanced `{...}` object). If that still fails, it performs **one** follow-up OpenAI request asking for clean JSON only.

### `POST /notes/apply-edit`

**Request** (use `updated_markdown` from the preview; escape quotes for your shell as needed)

```json
{
  "note_title": "Reading List",
  "updated_markdown": "# Reading List\n\n## Queue\n- The Gone World\n"
}
```

**Response `200`**

```json
{
  "note_id": "abc123…",
  "title": "Reading List",
  "updated": true
}
```

`apply-edit` updates the **note body** only. If the preview proposes a new **title**, it is not applied automatically; rename in Joplin if needed.

## Test with curl

### Health

```bash
curl -s http://127.0.0.1:8000/health
```

### Get note by title

Use one URL path segment (encode spaces as `%20`). Titles that contain `/` cannot be represented as a single path segment; avoid them or use another way to identify the note.

```bash
curl -s "http://127.0.0.1:8000/notes/by-title/Reading%20List"
```

### Create note

```bash
curl -s -X POST http://127.0.0.1:8000/notes/create \
  -H "Content-Type: application/json" \
  -d '{"note_title":"Reading List","markdown":"# Reading List\n\n## Queue\n","parent_id":"YOUR_NOTEBOOK_ID"}'
```

### Preview edit (OpenAI)

```bash
curl -s -X POST http://127.0.0.1:8000/notes/preview-edit \
  -H "Content-Type: application/json" \
  -d '{"note_title":"Reading List","instruction":"Add The Gone World to my Reading List queue and clean up formatting"}'
```

### Apply edit (writes body to Joplin)

```bash
curl -s -X POST http://127.0.0.1:8000/notes/apply-edit \
  -H "Content-Type: application/json" \
  -d '{"note_title":"Reading List","updated_markdown":"# Reading List\n\n## Queue\n- The Gone World\n"}'
```

## API summary

| Method | Path | Purpose |
|--------|------|--------|
| GET | `/health` | Liveness; pings Joplin |
| GET | `/notes/by-title/{title}` | Load note (markdown in `body`) |
| POST | `/notes/create` | Create note (`note_title`, `markdown`, optional `parent_id`) |
| POST | `/notes/preview-edit` | Joplin + OpenAI → preview JSON |
| POST | `/notes/apply-edit` | Write `updated_markdown` to the note |

## License

Use and modify as you like for personal use.
