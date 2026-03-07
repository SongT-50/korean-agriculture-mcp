# Korean Agriculture Market MCP Server

**MCP server for Korean agricultural wholesale market auction data.**

Real-time auction prices from 32+ public wholesale markets across South Korea, powered by [data.go.kr](https://data.go.kr) Open API.

## Tools (6)

| Tool | Description |
|------|-------------|
| `get_realtime_auction` | Real-time auction data (63,000+ daily records nationwide) |
| `search_product_price` | Search prices by product keyword with market-level summaries |
| `compare_market_prices` | Compare prices across markets for a product |
| `get_price_trend` | Price trends over recent N days |
| `get_market_list` | List of all wholesale markets and category codes |
| `get_auction_summary` | Daily auction statistics by product and market |

## Data Coverage

- **32 wholesale markets** across South Korea (Seoul, Busan, Daegu, Daejeon, Gwangju, etc.)
- **22 product categories**: fruits, vegetables, mushrooms, grains, livestock, seafood, etc.
- **63,000+ auction records per day**
- Fields: auction time, market, corporation, product, variety, unit price, quantity, packaging, origin

## Quick Start

```bash
# Clone
git clone https://github.com/higheun/korean-agriculture-mcp.git
cd korean-agriculture-mcp

# Setup
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt  # Windows
# .venv/bin/pip install -r requirements.txt    # Linux/Mac

# Configure API key
cp .env.example .env
# Edit .env with your data.go.kr API key

# Run (stdio mode for Claude Desktop)
python server.py

# Run (SSE mode for remote access)
MCP_TRANSPORT=sse PORT=8000 python server.py
```

## API Key

Get a free API key from [data.go.kr](https://www.data.go.kr/data/15141808/openapi.do):

1. Sign up at data.go.kr
2. Search for "전국 공영도매시장 실시간 경매정보"
3. Apply for API usage (instant approval)
4. Copy the API key to `.env`

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "korean-agriculture": {
      "command": "python",
      "args": ["path/to/korean-agriculture-mcp/server.py"],
      "env": {
        "DATA_GO_KR_API_KEY": "your_api_key"
      }
    }
  }
}
```

## Example Queries

- "Show me today's apple auction prices at Seoul Garak market"
- "Compare strawberry prices across all markets"
- "What's the price trend for Napa cabbage over the past week?"
- "Give me an auction summary for Daejeon Noeun market"

## Data Source

- [data.go.kr - Korean Agricultural Products Wholesale Market Real-time Auction Info](https://www.data.go.kr/data/15141808/openapi.do)
- API: `https://apis.data.go.kr/B552845/katRealTime2/trades2`

## License

MIT
