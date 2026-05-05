import urllib.request
import json
import sqlite3
import time

try:
    print("Fetching history from API...")
    req = urllib.request.urlopen('http://localhost:8080/api/history?days=30')
    data = json.loads(req.read())
    
    conn = sqlite3.connect('trades.db')
    c = conn.cursor()
    count = 0
    
    for e in data.get('history', []):
        try:
            # Fix date string formatting issue
            date_str = e['date']
            if isinstance(date_str, dict): # if it serialized weirdly?
                continue
            
            ts_str = f"{date_str} {e['bar_time']}"
            ts = int(time.mktime(time.strptime(ts_str, '%Y-%m-%d %H:%M')))
            
            c.execute('''
                INSERT OR IGNORE INTO bar_history 
                (timestamp, date_str, bar_time, win_price, z_wdo, z_di, spread_wdo, wdo_price, di_price, nwe_center, nwe_upper, nwe_lower, nwe_is_up) 
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0)
            ''', (
                ts, date_str, e['bar_time'], 
                e.get('win_price', 0), e.get('z', 0), e.get('z_di', 0), e.get('spread', 0)
            ))
            count += 1
        except Exception as ex:
            print(f"Error on entry {e}: {ex}")
            
    conn.commit()
    print(f"Inserted {count} rows into bar_history!")
    conn.close()
    
except Exception as e:
    print(f"Failed to fetch or process history: {e}")
