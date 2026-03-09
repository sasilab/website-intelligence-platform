# Website Intelligence Platform

An AI-powered platform that automatically extracts, manages, and serves website navigation intelligence to AI agents. Built specifically for B2B SaaS companies with multi-tenant, role-based access requirements.

## Overview

The Website Intelligence Platform solves the critical problem of keeping AI agents informed about website structure, navigation, and functionality. It automatically crawls websites, uses LLMs to extract meaningful information, and stores it in a searchable memory that agents can query in real-time.

### Key Features

- **Dual Crawling Engines**: Static (BeautifulSoup) and Dynamic (Playwright) crawlers for all website types
- **LLM-Powered Summarization**: Converts raw HTML into structured, meaningful information
- **Vector Search**: Semantic search capabilities for finding relevant navigation information
- **Multi-Tenant Support**: Client-specific configurations with role-based access control
- **Change Detection**: Incremental crawling with automatic detection of website changes
- **CI/CD Integration**: Webhook support for automatic updates on deployments
- **Feature Management**: Enable/disable features per client with custom labeling
- **Real-time API**: REST API for agents to query navigation memory

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  TRIGGER LAYER                       │
│  Scheduler | Webhook (CI/CD) | Manual | URL Monitor  │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│                  CRAWLER ENGINE                      │
│     Playwright + BS4 | Auth Sessions | Rate Limiter  │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│               CHANGE DETECTION                       │
│        Diff Engine | Hash Comparison | Sitemap Diff  │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│             KNOWLEDGE EXTRACTION                     │
│   LLM Summarizer | Nav Parser | Action Extractor     │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│               MEMORY STORE                           │
│   Structured JSON + Vector DB + Version History      │
└──────────────────────┬──────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────┐
│              DELIVERY LAYER                          │
│        REST API | MCP | Webhooks | SDK               │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.8+
- Node.js 14+
- MongoDB
- Redis (optional)
- ChromaDB or Pinecone (for vector storage)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourcompany/website-intelligence-platform.git
cd website-intelligence-platform
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Node.js dependencies:
```bash
npm install
```

4. Install Playwright browsers:
```bash
playwright install
```

5. Copy environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

### Running the Platform

1. Start MongoDB:
```bash
mongod --dbpath /path/to/data
```

2. Start ChromaDB (if using):
```bash
chroma run --host localhost --port 8000
```

3. Start the API server:
```bash
python -m uvicorn src.api.main:app --reload --port 8000
```

4. Start the crawler scheduler (optional):
```bash
python scripts/start_scheduler.py
```

## Usage Examples

### 1. Register a New Client

```python
import requests

client_data = {
    "client_id": "suntech_energy",
    "name": "SunTech Energy",
    "industry_segment": "large_utility",
    "plan": "enterprise",
    "region": "EU",
    "base_url": "https://app.solarplatform.com",
    "auth": {
        "method": "session_token",
        "token_ref": "vault://clients/suntech/token"
    },
    "asset_types": ["solar_pv", "battery_storage"],
    "plant_count": 12,
    "roles": ["admin", "operator", "viewer"]
}

response = requests.post(
    "http://localhost:8000/api/clients",
    json=client_data,
    headers={"X-API-Key": "your-api-key"}
)
print(response.json())
```

### 2. Trigger a Crawl

```python
# Trigger full crawl for a client
response = requests.post(
    "http://localhost:8000/api/crawl/trigger",
    params={
        "crawl_type": "full",
        "client_id": "suntech_energy"
    },
    headers={"X-API-Key": "your-api-key"}
)
```

### 3. Query the Memory

```python
# AI agent queries how to navigate to alarms
query_data = {
    "query": "How do I see the faults for Plant 3?",
    "client_id": "suntech_energy",
    "role_id": "operator",
    "limit": 5
}

response = requests.post(
    "http://localhost:8000/api/query",
    json=query_data,
    headers={"X-API-Key": "your-api-key"}
)

results = response.json()
for result in results["results"]:
    print(f"Score: {result['score']}")
    print(f"Answer: {result['text']}")
    print("---")
```

### 4. Update Client Configuration

```python
# Enable a new feature for a client
response = requests.put(
    "http://localhost:8000/api/clients/suntech_energy/config",
    json={
        "feature_configs": [
            {
                "feature_id": "yield_forecasting",
                "enabled": True,
                "label_override": "Production Forecast"
            }
        ]
    },
    headers={"X-API-Key": "your-api-key"}
)
```

### 5. Webhook Integration

Configure your CI/CD pipeline to send webhooks on deployment:

```yaml
# Example GitHub Actions workflow
- name: Notify Website Intelligence Platform
  run: |
    curl -X POST https://your-platform.com/api/webhooks/deployment \
      -H "X-API-Key: ${{ secrets.WIP_API_KEY }}" \
      -H "Content-Type: application/json" \
      -d '{
        "event": "deployment",
        "environment": "production",
        "changes": ["pages/dashboard.tsx", "components/nav.tsx"],
        "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
        "triggered_by": "github-actions"
      }'
```

## API Reference

### Query Endpoints

#### POST /api/query
Query the website memory for navigation information.

Request:
```json
{
  "query": "How to navigate to settings",
  "client_id": "client_123",
  "role_id": "admin",
  "limit": 5,
  "filters": {}
}
```

Response:
```json
{
  "query": "How to navigate to settings",
  "results": [
    {
      "memory_id": "mem_abc123",
      "text": "To access Settings, click 'Settings' in the left sidebar...",
      "score": 0.95,
      "metadata": {
        "page_id": "page_settings",
        "url": "/settings"
      }
    }
  ],
  "total_results": 1,
  "execution_time_ms": 45.2
}
```

### Client Management Endpoints

- `GET /api/clients` - List all clients
- `GET /api/clients/{client_id}` - Get client details
- `POST /api/clients` - Create new client
- `PUT /api/clients/{client_id}/config` - Update client configuration

### Crawl Management Endpoints

- `POST /api/crawl/trigger` - Trigger a crawl
- `GET /api/crawl/status` - Get crawl status
- `GET /api/crawl/history` - Get crawl history

### Memory Management Endpoints

- `POST /api/memory/refresh/{client_id}` - Refresh client memory
- `DELETE /api/memory/{memory_id}` - Delete memory entry

## Configuration

### Environment Variables

Key environment variables in `.env`:

```env
# Database
MONGODB_URI=mongodb://localhost:27017/website_intelligence

# Vector Store
VECTOR_STORE_TYPE=chromadb
CHROMADB_HOST=localhost
CHROMADB_PORT=8000

# LLM Configuration
OPENAI_API_KEY=your_key
LLM_MODEL=gpt-4-turbo-preview

# Crawler Settings
MAX_CRAWL_DEPTH=5
CRAWL_TIMEOUT=30000
RATE_LIMIT_REQUESTS=10

# API Security
JWT_SECRET=your_secret
API_KEYS=key1,key2,key3
```

### Client Configuration

Each client can have customized:
- **Feature flags**: Enable/disable specific features
- **Label overrides**: Rename features for their UI
- **Role permissions**: Define what each role can access
- **Navigation structure**: Custom menu organization

## Advanced Features

### Multi-Layer Memory Architecture

The platform uses a three-layer memory architecture:

1. **Global Feature Memory**: Deep documentation of every feature
2. **Client Config Layer**: Per-client feature flags and customizations
3. **Role Layer**: Role-specific permissions and restrictions

This allows efficient scaling to hundreds of clients without duplicating data.

### Change Detection

The platform detects changes through:
- Content hash comparison
- Structural diff analysis
- Navigation change detection
- Component change tracking

Only changed content is re-processed, saving compute resources.

### Smart Summarization

LLM summarization is context-aware:
- Considers client's industry segment
- Adapts to asset types
- Respects role permissions
- Preserves custom labels

## Deployment

### Production Setup

1. Use a production MongoDB cluster
2. Set up Redis for caching
3. Configure a production vector database (Pinecone recommended)
4. Enable SSL/TLS
5. Set up monitoring (Prometheus/Grafana)
6. Configure backup strategies

### Docker Deployment

```dockerfile
# Dockerfile included in the repository
docker build -t website-intelligence-platform .
docker run -p 8000:8000 --env-file .env website-intelligence-platform
```

### Kubernetes Deployment

Helm charts are available in the `/k8s` directory:

```bash
helm install wip ./k8s/website-intelligence-platform
```

## Monitoring

The platform includes built-in monitoring:

- Prometheus metrics at `/metrics`
- Health checks at `/health`
- Crawl statistics at `/api/analytics/summary`

## Troubleshooting

### Common Issues

1. **Crawl timeouts**: Increase `CRAWL_TIMEOUT` in environment
2. **Memory overflow**: Reduce `BATCH_SIZE` for large sites
3. **LLM rate limits**: Implement retry logic with backoff
4. **Vector search slow**: Ensure proper indexing is configured

## Contributing

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

For issues and questions:
- Email: sasi@andrilium.com
