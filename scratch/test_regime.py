import asyncio
import traceback

async def test():
    try:
        import server
        res = await server.regime_v2()
        print("Success! Keys in response:", res.keys())
    except Exception as e:
        print("ERROR IN regime_v2!")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
