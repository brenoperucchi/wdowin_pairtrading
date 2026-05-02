import urllib.request, json

# WDO
r1 = urllib.request.urlopen('http://localhost:8080/api/v2/regime')
wdo = json.loads(r1.read())

# DI
r2 = urllib.request.urlopen('http://localhost:8080/api/di-regime')
di = json.loads(r2.read())

print("=== WIN x WDO (Kalman) ===")
print(f"  Z-Score atual: {wdo['current_z']}")
print(f"  Signal: {wdo['signal']['label']}")
print(f"  Johansen Gate: {wdo['johansen_gate']}")
zs = [h['z'] for h in wdo['history'][-10:]]
print(f"  Ultimo 10 z-scores: {zs}")
print()
print("=== WIN x DI (Johansen) ===")
print(f"  Z-Score atual: {di['current_z']}")
print(f"  Signal: {di['signal']['label']}")
print(f"  Johansen Gate: {di['johansen_gate']}")
zs_di = [h['z'] for h in di['history'][-10:]]
print(f"  Ultimo 10 z-scores: {zs_di}")
print()

print("=== THRESHOLDS ATUAIS ===")
print("  COMPRA/VENDA: z <= -1.8 / z >= 1.8")
print("  ATENCAO: z <= -1.5 / z >= 1.5")
print("  ANOMALIA: |z| >= 4.0")
print()

for name, data in [("WDO", wdo), ("DI", di)]:
    hist = data['history']
    total = len(hist)
    if total == 0:
        print(f"{name}: sem dados")
        continue
    buys = sum(1 for h in hist if h['z'] <= -1.8)
    sells = sum(1 for h in hist if h['z'] >= 1.8)
    att_buy = sum(1 for h in hist if -1.8 < h['z'] <= -1.5)
    att_sell = sum(1 for h in hist if 1.5 <= h['z'] < 1.8)
    neutral = sum(1 for h in hist if -1.5 < h['z'] < 1.5)
    anomalies = sum(1 for h in hist if abs(h['z']) >= 4.0)
    z_vals = [h['z'] for h in hist]
    print(f"{name} ({total} barras):")
    print(f"  COMPRA:   {buys} ({buys/total*100:.1f}%)")
    print(f"  VENDA:    {sells} ({sells/total*100:.1f}%)")
    print(f"  ATN BUY:  {att_buy} ({att_buy/total*100:.1f}%)")
    print(f"  ATN SELL: {att_sell} ({att_sell/total*100:.1f}%)")
    print(f"  NEUTRO:   {neutral} ({neutral/total*100:.1f}%)")
    print(f"  ANOMALIA: {anomalies} ({anomalies/total*100:.1f}%)")
    print(f"  Min Z: {min(z_vals):.3f}  Max Z: {max(z_vals):.3f}  Mean: {sum(z_vals)/len(z_vals):.3f}")
    print()
