import os
import re

fn = "server.py"
with open(fn, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update init_db
old_create = """            price_win_out REAL,
            pnl_brl REAL
        )
    ''')"""
new_create = """            price_win_out REAL,
            pnl_brl REAL,
            max_pts_favor REAL DEFAULT 0.0,
            be_active INTEGER DEFAULT 0
        )
    ''')
    try:
        c.execute("ALTER TABLE operations ADD COLUMN max_pts_favor REAL DEFAULT 0.0")
        c.execute("ALTER TABLE operations ADD COLUMN be_active INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass"""
code = code.replace(old_create, new_create)


# 2. Update get_signal
old_signal_1 = """    if z >= 2.0:
        return {"id": "compraWdo", "label": "COMPRA WDO · VENDE WIN",
                "sub": f"WIN sobrevalorizado vs WDO — spread revertendo para baixo",
                "wdo": "COMPRAR", "win": "VENDER", "qty_wdo": qty_wdo, "qty_win": qty_win, "color": "#00d4ff"}
    if z <= -2.0:
        return {"id": "compraWin", "label": "COMPRA WIN · VENDE WDO",
                "sub": f"WIN subvalorizado vs WDO — spread revertendo para cima",
                "wdo": "VENDER", "win": "COMPRAR", "qty_wdo": qty_wdo, "qty_win": qty_win, "color": "#00e87a"}"""

new_signal_1 = """    if z >= 2.1:
        return {"id": "compraWdo", "label": "VENDE WIN (OLS)",
                "sub": "Venda de Índice (V1 OLS)",
                "wdo": "IGNORAR", "win": "VENDER", "qty_wdo": 0, "qty_win": qty_win, "color": "#ff3860"}
    if z <= -2.0:
        return {"id": "compraWin", "label": "COMPRA WIN (KALMAN)",
                "sub": "Compra de Índice (V2 Kalman)",
                "wdo": "IGNORAR", "win": "COMPRAR", "qty_wdo": 0, "qty_win": qty_win, "color": "#00e87a"}"""
code = code.replace(old_signal_1, new_signal_1)

# 3. Fix /api/regime trade exit logic and /api/v2/regime trade exit logic
old_db_logic = """        c.execute("SELECT id, z_in, qty_wdo, qty_win, price_wdo_in, price_win_in FROM operations WHERE status='OPEN'")
        open_trade = c.fetchone()
        
        sig_data = get_signal(current_z, current_spread_sd, beta_ols)
        
        if open_trade:
            # Temos posição aberta, checa saídas
            trade_id, z_in, qty_wdo, qty_win, price_wdo_in, price_win_in = open_trade
            reason = None
            if abs(current_z) < 0.5:
                reason = "TARGET"
            elif abs(current_z) >= 4.5:
                reason = "STOP_Z"
            elif current_rho > -0.40:
                reason = "STOP_RHO"
                
            if reason:
                pnl_brl = 0.0
                if z_in > 0:
                    pnl_wdo = (current_price_b - price_wdo_in) * qty_wdo * 10.0
                    pnl_win = (price_win_in - current_price_a) * qty_win * 0.20
                else:
                    pnl_wdo = (price_wdo_in - current_price_b) * qty_wdo * 10.0
                    pnl_win = (current_price_a - price_win_in) * qty_win * 0.20
                pnl_brl = pnl_wdo + pnl_win

                c.execute("UPDATE operations SET status='CLOSED', timestamp_out=?, exit_reason=?, price_wdo_out=?, price_win_out=?, pnl_brl=? WHERE id=?", 
                          (datetime.now().isoformat(), reason, current_price_b, current_price_a, pnl_brl, trade_id))
                conn.commit()"""

new_db_logic = """        c.execute("SELECT id, z_in, qty_wdo, qty_win, price_wdo_in, price_win_in, max_pts_favor, be_active FROM operations WHERE status='OPEN'")
        open_trade = c.fetchone()
        
        sig_data = get_signal(current_z, current_spread_sd, beta_ols)
        
        if open_trade:
            # Temos posição aberta, checa saídas
            trade_id, z_in, qty_wdo, qty_win, price_wdo_in, price_win_in, max_pts_favor, be_active = open_trade
            reason = None
            is_buy_win = (z_in < 0)
            
            # Parametros assimetricos baseados no teste
            tp_pts = 500 if is_buy_win else 1400
            sl_pts = 350 if is_buy_win else 300
            be_act = 400 if is_buy_win else 800
            be_lock= 50 if is_buy_win else 200
            
            # Pontos a favor absolutos no índice WIN
            pts_favor = (current_price_a - price_win_in) if is_buy_win else (price_win_in - current_price_a)
            
            # Atualiza Trailing/BE Max Pts
            if pts_favor > max_pts_favor:
                max_pts_favor = pts_favor
                c.execute("UPDATE operations SET max_pts_favor=? WHERE id=?", (max_pts_favor, trade_id))
            
            # Ativação do BE
            if not be_active and max_pts_favor >= be_act:
                be_active = 1
                c.execute("UPDATE operations SET be_active=1 WHERE id=?", (trade_id,))
                
            # Verifica saídas operacionais (Preço)
            if pts_favor >= tp_pts:
                reason = "TARGET"
            elif be_active and pts_favor <= be_lock:
                reason = "BE_STOP"
            elif not be_active and pts_favor <= -sl_pts:
                reason = "STOP_LOSS"
                
            # Verifica saídas de segurança (Z-Score / Correlação)
            if reason is None:
                if abs(current_z) >= 5.0:
                    reason = "STOP_Z"
                elif current_rho > -0.40:
                    reason = "STOP_RHO"
                    
            if reason:
                pnl_brl = 0.0
                if z_in > 0:
                    pnl_wdo = (current_price_b - price_wdo_in) * qty_wdo * 10.0
                    pnl_win = (price_win_in - current_price_a) * qty_win * 0.20
                else:
                    pnl_wdo = (price_wdo_in - current_price_b) * qty_wdo * 10.0
                    pnl_win = (current_price_a - price_win_in) * qty_win * 0.20
                pnl_brl = pnl_wdo + pnl_win

                c.execute("UPDATE operations SET status='CLOSED', timestamp_out=?, exit_reason=?, price_wdo_out=?, price_win_out=?, pnl_brl=? WHERE id=?", 
                          (datetime.now().isoformat(), reason, current_price_b, current_price_a, pnl_brl, trade_id))
                conn.commit()"""

# For V2, beta_ols inside the get_signal call is beta_current
old_db_logic_v2 = old_db_logic.replace("beta_ols", "beta_current")
new_db_logic_v2 = new_db_logic.replace("beta_ols", "beta_current")

code = code.replace(old_db_logic, new_db_logic)
code = code.replace(old_db_logic_v2, new_db_logic_v2)


with open(fn, "w", encoding="utf-8") as f:
    f.write(code)

print("Server updated with new tracking targets.")
