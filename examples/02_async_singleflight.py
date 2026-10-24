"""Example 2: Thundering Herd / Cache Stampede Protection with SingleFlight."""

import asyncio
from cacheforge import AsyncSingleFlight, acached

flight = AsyncSingleFlight[str, dict]()
calls = 0

async def fetch_expensive_market_rates(symbol: str) -> dict:
    global calls
    calls += 1
    print(f"  [DB/API] Executing heavy query for '{symbol}' (Execution #{calls})...")
    await asyncio.sleep(0.1)  # Simulate slow external API / database
    return {"symbol": symbol, "price": 42500.50}

@acached(stampede_protect=True, ttl=60.0)
async def get_market_data(symbol: str) -> dict:
    return await fetch_expensive_market_rates(symbol)

async def client_request(client_id: int, symbol: str):
    res = await get_market_data(symbol)
    print(f"Client #{client_id} received: {res['symbol']} @ ${res['price']}")

async def main():
    print("=== Simulating 10 concurrent requests for cold cache key ===")
    tasks = [client_request(i + 1, "BTC/USD") for i in range(10)]
    await asyncio.gather(*tasks)

    print(f"\nTotal heavy query executions: {calls} (Expected: exactly 1)")
    print(f"Cache metrics: {get_market_data.cache_info()['metrics']}")

if __name__ == "__main__":
    asyncio.run(main())
