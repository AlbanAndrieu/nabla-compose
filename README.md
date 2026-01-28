# nabla-site-python-

Sample FastAPI Hello World project deployable to Vercel and Cloudflare Wrangler.

## Overview

This is a minimal FastAPI application with three endpoints:

- `/` - Returns a hello world message
- `/health` - Health check endpoint
- `/api/info` - API information endpoint

## Local Development

### Prerequisites

- Python 3.8 or higher
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

1. Install uv (if not already installed):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Init sample:

[fastapi-sample](https://github.com/vercel/vercel/blob/main/examples/fastapi/pyproject.toml)

[backend-fastapi](https://vercel.com/docs/frameworks/backend/fastapi)
[nextjs-fastapi-starter](https://vercel.com/templates/next.js/nextjs-fastapi-starter)
[medium-fastapi-application-on-vercel](https://medium.com/@masud.pervez27/building-and-deploying-my-first-fastapi-application-on-vercel-a-complete-journey-7b010345162c)

[runtimes-python](https://vercel.com/docs/functions/runtimes/python)

```bash
vc init fastapi
```

3. Install dependencies:

```bash
uv sync
```

## Running Locally

Start the development server on http://0.0.0.0:8000

```bash
python main.py
# using uv:
uv run main.py
```

When you make changes to your project, the server will automatically reload.

3. Run the development server:

```bash
uvicorn main:app --reload
```

4. Access the application:

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Alternative docs: http://localhost:8000/redoc

## Deployment

### Deploy to Vercel

1. Install Vercel CLI:

```bash
npm install -g vercel
```

2. Deploy:

```bash
vercel
```

3. For production deployment:

```bash
vercel --prod
```

The `vercel.json` configuration file handles the deployment settings automatically.

### Deploy to Cloudflare Workers (with Wrangler)

1. Install Wrangler CLI:

```bash
npm install -g wrangler
```

2. Login to Cloudflare:

```bash
wrangler login
```

3. Deploy:

```bash
uv run pywrangler dev
wrangler deploy
```

```
🎉  SUCCESS  Application created successfully!

💻 Continue Developing
Change directories: cd api
uv self update
Deploy: npm run deploy
```

The `wrangler.toml` configuration file handles the deployment settings automatically.

**Note:** Cloudflare Workers with Python support is currently in beta. You may need to use Cloudflare Pages with Python or adjust the configuration based on the latest Cloudflare documentation.

## Project Structure

```
.
├── main.py           # FastAPI application
├── pyproject.toml    # Python project configuration and dependencies (uv)
├── uv.lock          # Lock file for reproducible installs
├── vercel.json      # Vercel deployment configuration
├── wrangler.toml    # Cloudflare Wrangler configuration
└── README.md        # This file
```

## API Endpoints

### GET /

Returns a hello world message.

**Response:**

```json
{
  "message": "Hello World"
}
```

### GET /health

Health check endpoint.

**Response:**

```json
{
  "status": "healthy"
}
```

### GET /api/info

API information endpoint.

**Response:**

```json
{
  "name": "nabla-site-python",
  "version": "1.0.0",
  "description": "Sample FastAPI Hello World for Vercel and Cloudflare deployment"
}
```

### Initialize opencommit and oco

1. Install opencommit:

```bash
npm install -D opencommit
npm install -D @commitlint/cli @commitlint/config-conventional @commitlint/prompt-cli commitizen cz-emoji-conventional

git add .opencommit-commitlint
oco commitlint get

oco config set OCO_PROMPT_MODULE=@commitlint
```
