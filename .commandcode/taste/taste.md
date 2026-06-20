# llm
- Use deepseek/deepseek-v4-flash as primary LLM via CommandCode CLI (cmd -p). Fallback to nvidia/llama-3.1-nemotron-70b-instruct:free via OpenRouter. Confidence: 0.75

# architecture
- Use dependency injection (DI) and design patterns throughout the project. Confidence: 0.75
- Scraping URLs must be easily addable/removable — the project should scale without code changes. Confidence: 0.65

# docker
- DB container (db-1) should not expose external ports — internal Docker network only. Confidence: 0.65
- Use uvicorn directly as CMD in Dockerfile for Railway deployments, not custom entry-point scripts like grantpulse-api. Confidence: 0.70

# database
- Use SQLite instead of PostgreSQL — simpler deployment, single container, zero config, fits Railway free tier. Confidence: 0.70

# cli
- Use CommandCode CLI (cmd -p) with CMD_API_KEY for LLM queries. Confidence: 0.60

# database
- Use SQLite instead of PostgreSQL — simpler deployment, single container, zero config, fits Railway free tier. Confidence: 0.70
- Use auto-increment integer IDs for primary keys, not UUIDs — simpler, faster, more readable for single-instance apps. Confidence: 0.80

# testing
- Run Docker-based integration tests with fresh state (docker compose down -v && docker compose up --build + health checks) before considering changes complete — don't deploy first and discover errors later. Confidence: 0.80

