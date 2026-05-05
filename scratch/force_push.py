import sys
sys.path.append('.')
import server
import asyncio

async def push():
    print("Connecting to MT5...")
    server.connect_mt5()
    print("Fetching history...")
    hist = server.history_endpoint(days=30)
    print("Pushing history to Firebase...")
    ref_hist = server.fdb.reference('history_30d')
    ref_hist.set(hist.get('history', []))
    print("Fetching live dashboard...")
    r_v2 = server.regime_v2()
    r_di = server.di_regime()
    perf = server.get_performance()
    print("Pushing live dashboard to Firebase...")
    ref = server.fdb.reference('dashboard')
    ref.set({
        'regime': r_v2,
        'di_regime': r_di,
        'performance': perf,
    })
    print('All pushed successfully!')

if __name__ == "__main__":
    asyncio.run(push())
