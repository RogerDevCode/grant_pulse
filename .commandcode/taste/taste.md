# llm
- Use deepseek/deepseek-v4-flash as primary LLM via CommandCode CLI (cmd -p). Fallback to nvidia/llama-3.1-nemotron-70b-instruct:free via OpenRouter. Confidence: 0.75

# architecture
- Use dependency injection (DI) and design patterns throughout the project. Confidence: 0.75
- Scraping URLs must be easily addable/removable — the project should scale without code changes. Confidence: 0.65

# cli
- Use CommandCode CLI (cmd -p) with CMD_API_KEY for LLM queries. Confidence: 0.60

