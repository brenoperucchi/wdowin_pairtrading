import os
import re

PROJECT_ROOT = r"c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
WDO_CORE_PATH = os.path.join(PROJECT_ROOT, "mt5", "Include", "Jumba_WDO_GEX_NWE_Core.mqh")
WIN_CORE_PATH = os.path.join(PROJECT_ROOT, "mt5", "Include", "Jumba_GEX_NWE_Core.mqh")
FIX_PRF_PATH = os.path.join(PROJECT_ROOT, "mt5", "fix_18_wf_monitor_profile.py")


def patch_wdo_core():
    with open(WDO_CORE_PATH, "r", encoding="utf-8-sig") as f:
        txt = f.read()

    # 1. Add m_last_order_ms[17], m_last_sent_lots[17], m_last_net_sync_ms to class members
    old_members = """   datetime          m_last_m5_bar_time;
   bool              m_state_reconciled;"""
    new_members = """   datetime          m_last_m5_bar_time;
   bool              m_state_reconciled;
   ulong             m_last_order_ms[17];
   double            m_last_sent_lots[17];
   ulong             m_last_net_sync_ms;"""
    assert old_members in txt, "old_members not found in WDO core"
    txt = txt.replace(old_members, new_members, 1)

    # 2. Initialize in constructor
    old_ctor = """      m_last_m5_bar_time = 0;
      m_state_reconciled = false;"""
    new_ctor = """      m_last_m5_bar_time = 0;
      m_state_reconciled = false;
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }"""
    assert old_ctor in txt, "old_ctor not found in WDO core"
    txt = txt.replace(old_ctor, new_ctor, 1)

    # 3. Harden Init() - clamp lot_mult, force HEDGING on Hedging accounts or Single-Slot EAs, clear stale GlobalVariables
    old_init = """      m_base_magic = base_magic;
      m_lot_mult = MathMax(1.0, MathRound(lot_mult));
      m_max_daily_loss_brl = max_daily_loss_brl;
      m_draw_levels = true; // Sempre desenha as Walls visuais no grafico WDO
      m_show_hud = show_hud;
      m_exec_mode = exec_mode;

      long acc_margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(acc_margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         Print("[JUMBA WDO] Conta NETTING detectada na corretora. Alternando automaticamente para WDO_EXEC_NETTING_VIRTUAL_SYNC.");
         m_exec_mode = WDO_EXEC_NETTING_VIRTUAL_SYNC;
        }"""
    new_init = """      m_base_magic = base_magic;
      m_lot_mult = MathMin(10.0, MathMax(1.0, MathRound(lot_mult)));
      m_max_daily_loss_brl = max_daily_loss_brl;
      m_draw_levels = true; // Sempre desenha as Walls visuais no grafico WDO
      m_show_hud = show_hud;
      m_exec_mode = exec_mode;
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }"""
    assert old_init in txt, "old_init not found in WDO core"
    txt = txt.replace(old_init, new_init, 1)

    old_init_loop_end = """         m_slots[k].trades_today = 0;
         m_slots[k].trades_total = 0;
         m_slots[k].wins_total = 0;
        }

      SymbolSelect("WIN$N", true);"""
    new_init_loop_end = """         m_slots[k].trades_today = 0;
         m_slots[k].trades_total = 0;
         m_slots[k].wins_total = 0;
        }

      long acc_margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(acc_margin_mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || GetSingleActiveSlotId() > 0)
        {
         if(m_exec_mode != WDO_EXEC_HEDGING_DIRECT_MAGIC)
            Print("[JUMBA WDO] Trava de Seguranca: Forcando WDO_EXEC_HEDGING_DIRECT_MAGIC (Conta Hedging ou Robo Individual).");
         m_exec_mode = WDO_EXEC_HEDGING_DIRECT_MAGIC;
        }
      else if(acc_margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         Print("[JUMBA WDO] Conta NETTING detectada na corretora. Alternando automaticamente para WDO_EXEC_NETTING_VIRTUAL_SYNC.");
         m_exec_mode = WDO_EXEC_NETTING_VIRTUAL_SYNC;
        }

      if(!MQLInfoInteger(MQL_TESTER))
        {
         GlobalVariablesDeleteAll("JUMBA_WDO_LOTS_");
         GlobalVariablesDeleteAll("JUMBA_WDO_TIME_");
        }

      SymbolSelect("WIN$N", true);"""
    assert old_init_loop_end in txt, "old_init_loop_end not found in WDO core"
    txt = txt.replace(old_init_loop_end, new_init_loop_end, 1)

    # 4. Add GetMaxBaseLotsForSlot(int k) right after GetSingleActiveSlotId()
    old_single_fn = """   int               GetSingleActiveSlotId()
     {
      int cnt = 0, last_k = 0;
      for(int k=1; k<=16; k++)
        {
         if(m_slots[k].enabled)
           {
            cnt++;
            last_k = k;
           }
        }
      return (cnt == 1) ? last_k : 0;
     }"""
    new_single_fn = """   int               GetSingleActiveSlotId()
     {
      int cnt = 0, last_k = 0;
      for(int k=1; k<=16; k++)
        {
         if(m_slots[k].enabled)
           {
            cnt++;
            last_k = k;
           }
        }
      return (cnt == 1) ? last_k : 0;
     }

   int               GetMaxBaseLotsForSlot(int k)
     {
      if(k == 11 || k == 13)
         return 3; // SmartGrid 1+2 lotes
      if(k == 12)
         return 2; // Piramidacao 1+1 lotes
      return 1;    // Demais estrategias operam estritamente 1 lote base
     }"""
    assert old_single_fn in txt, "old_single_fn not found in WDO core"
    txt = txt.replace(old_single_fn, new_single_fn, 1)

    # 5. Clamp lots in LoadVirtualStateFromDisk() and ReconcileWithBrokerOnStartup()
    old_load_lots = """               m_slots[k].dir                  = (int)StringToInteger(p[1]);
               m_slots[k].lots                 = (int)StringToInteger(p[2]);"""
    new_load_lots = """               m_slots[k].dir                  = (int)StringToInteger(p[1]);
               m_slots[k].lots                 = (int)MathMin((long)GetMaxBaseLotsForSlot(k), MathMax(0, StringToInteger(p[2])));"""
    assert old_load_lots in txt, "old_load_lots not found in WDO core"
    txt = txt.replace(old_load_lots, new_load_lots, 1)

    old_rec_lots = """               int pos_dir = (actual_lots > 0.0) ? 1 : -1;
               int pos_lots = MathMax(1, (int)MathRound(MathAbs(actual_lots) / m_lot_mult));"""
    new_rec_lots = """               int pos_dir = (actual_lots > 0.0) ? 1 : -1;
               int pos_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(1, (int)MathRound(MathAbs(actual_lots) / m_lot_mult)));"""
    assert old_rec_lots in txt, "old_rec_lots not found in WDO core"
    txt = txt.replace(old_rec_lots, new_rec_lots, 1)

    # 6. Replace SyncRealPositionsWithVirtualSlots() with hardened version
    old_sync = """   void              SyncRealPositionsWithVirtualSlots()
     {
      if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            long slot_magic = m_base_magic + k;
            double target_signed = m_slots[k].dir * m_slots[k].lots * m_lot_mult;

            double actual_signed = 0.0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i))
                 {
                  if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                    {
                     if(m_pos.PositionType() == POSITION_TYPE_BUY)
                        actual_signed += m_pos.Volume();
                     else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                        actual_signed -= m_pos.Volume();
                    }
                 }
              }

            if(MathAbs(target_signed) < 0.01 && MathAbs(actual_signed) >= 0.01)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               continue;
              }

            double sl_srv = (m_slots[k].dir == -1 && m_slots[k].curr_sl > 0.0) ? Round05(m_slots[k].curr_sl + 0.5) : m_slots[k].curr_sl;
            double tp_srv = (m_slots[k].dir == -1 && m_slots[k].curr_tp > 0.0) ? Round05(m_slots[k].curr_tp + 0.5) : m_slots[k].curr_tp;

            if((target_signed > 0.0 && actual_signed < -0.01) || (target_signed < 0.0 && actual_signed > 0.01))
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               actual_signed = 0.0;
              }

            double diff = target_signed - actual_signed;
            if(MathAbs(diff) >= 0.99)
              {
               if(!MQLInfoInteger(MQL_TESTER))
                 {
                  if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
                    {
                     if(!m_slots[k].real_synced)
                        ResetSlotPosition(k);
                     continue;
                    }
                  double live_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  double live_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                  if(!m_slots[k].real_synced && live_bid > 0.0 && live_ask > 0.0)
                    {
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 2.5)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.1f vs Atual=%.1f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round05(live_ask) : Round05(live_bid);
                     m_slots[k].p1_entry = Round05(live_bid);
                     m_slots[k].avg_price = Round05(live_bid);
                     double sl_d = MathMax(7.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(7.0, m_slots[k].init_tp_pts);
                     if(m_slots[k].dir == 1)
                       {
                        m_slots[k].curr_sl = Round05(fill_ref - sl_d);
                        m_slots[k].curr_tp = Round05(fill_ref + tp_d);
                        sl_srv = m_slots[k].curr_sl;
                        tp_srv = m_slots[k].curr_tp;
                       }
                     else
                       {
                        m_slots[k].curr_sl = Round05(fill_ref + sl_d);
                        m_slots[k].curr_tp = Round05(fill_ref - tp_d);
                        sl_srv = Round05(m_slots[k].curr_sl + 0.5);
                        tp_srv = Round05(m_slots[k].curr_tp + 0.5);
                       }
                    }
                 }

               m_trade.SetExpertMagicNumber(slot_magic);
               double vol = MathRound(MathAbs(diff));
               bool ok = false;
               if(diff > 0.0)
                  ok = m_trade.Buy(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               else
                  ok = m_trade.Sell(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);

               if(ok)
                  m_slots[k].real_synced = true;
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                  ResetSlotPosition(k);
              }

            if(MathAbs(target_signed) >= 0.99)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                       {
                        double cur_sl = m_pos.StopLoss();
                        double cur_tp = m_pos.TakeProfit();
                        if(MathAbs(cur_sl - sl_srv) >= 0.4 || MathAbs(cur_tp - tp_srv) >= 0.4)
                          {
                           m_trade.SetExpertMagicNumber(slot_magic);
                           m_trade.PositionModify(m_pos.Ticket(), sl_srv, tp_srv);
                          }
                       }
                    }
                 }
              }
           }
        }
      else
        {
         double target_net = 0.0;
         if(MQLInfoInteger(MQL_TESTER))
           {
            for(int k=1; k<=16; k++)
              {
               if(m_slots[k].enabled && m_slots[k].dir != 0)
                  target_net += m_slots[k].dir * m_slots[k].lots * m_lot_mult;
              }
           }
         else
           {
            datetime now_loc = TimeLocal();
            for(int k=1; k<=16; k++)
              {
               string gv_lots = StringFormat("JUMBA_WDO_LOTS_%s_%d", _Symbol, k);
               string gv_time = StringFormat("JUMBA_WDO_TIME_%s_%d", _Symbol, k);
               if(m_slots[k].enabled)
                 {
                  double my_l = (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
                  GlobalVariableSet(gv_lots, my_l);
                  GlobalVariableSet(gv_time, (double)now_loc);
                  target_net += my_l;
                 }
               else if(GlobalVariableCheck(gv_time) && (now_loc - (datetime)GlobalVariableGet(gv_time)) <= 90)
                 {
                  target_net += GlobalVariableGet(gv_lots);
                 }
              }
           }
         target_net = MathRound(target_net);

         double actual_net = 0.0;
         for(int i=PositionsTotal()-1; i>=0; i--)
           {
            if(m_pos.SelectByIndex(i))
              {
               if(m_pos.Symbol() == _Symbol)
                 {
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_net += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_net -= m_pos.Volume();
                 }
              }
           }

         double diff = target_net - actual_net;
         if(MathAbs(diff) >= 0.99)
           {
            m_trade.SetExpertMagicNumber(m_base_magic);
            double vol = MathRound(MathAbs(diff));
            if(diff > 0.0)
               m_trade.Buy(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
            else
               m_trade.Sell(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
           }
        }
     }"""

    new_sync = """   void              SyncRealPositionsWithVirtualSlots()
     {
      // Trava Estrutural Absoluta: Conta HEDGING ou EA Individual SEMPRE opera em HEDGING_DIRECT_MAGIC!
      if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || GetSingleActiveSlotId() > 0)
         m_exec_mode = WDO_EXEC_HEDGING_DIRECT_MAGIC;

      if(m_exec_mode == WDO_EXEC_HEDGING_DIRECT_MAGIC)
        {
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            long slot_magic = m_base_magic + k;
            int max_base = GetMaxBaseLotsForSlot(k);
            if(m_slots[k].lots > max_base)
               m_slots[k].lots = max_base;
            if(m_slots[k].lots < 0)
               m_slots[k].lots = 0;

            double max_slot_vol = MathRound((double)max_base * m_lot_mult);
            double target_signed = MathRound((double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult);
            if(target_signed > max_slot_vol)  target_signed = max_slot_vol;
            if(target_signed < -max_slot_vol) target_signed = -max_slot_vol;

            double actual_signed = 0.0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i))
                 {
                  if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                    {
                     if(m_pos.PositionType() == POSITION_TYPE_BUY)
                        actual_signed += m_pos.Volume();
                     else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                        actual_signed -= m_pos.Volume();
                    }
                 }
              }

            ulong now_ms = GetTickCount64();
            if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0)
              {
               ulong elapsed = now_ms - m_last_order_ms[k];
               // Enquanto a ordem para este mesmo alvo estiver liquidando na B3 (ate 5s) ou < 1.5s entre ordens, aguarda!
               if(elapsed < 1500 || (elapsed < 5000 && MathAbs(target_signed - m_last_sent_lots[k]) < 0.01))
                  continue;
              }

            if(MathAbs(target_signed) < 0.01 && MathAbs(actual_signed) >= 0.01)
              {
               m_trade.SetExpertMagicNumber(slot_magic);
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = 0.0;
               continue;
              }

            double sl_srv = (m_slots[k].dir == -1 && m_slots[k].curr_sl > 0.0) ? Round05(m_slots[k].curr_sl + 0.5) : m_slots[k].curr_sl;
            double tp_srv = (m_slots[k].dir == -1 && m_slots[k].curr_tp > 0.0) ? Round05(m_slots[k].curr_tp + 0.5) : m_slots[k].curr_tp;

            if((target_signed > 0.0 && actual_signed < -0.01) || (target_signed < 0.0 && actual_signed > 0.01))
              {
               m_trade.SetExpertMagicNumber(slot_magic);
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                 }
               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = 0.0;
               continue;
              }

            double diff = target_signed - actual_signed;
            if(MathAbs(diff) >= 0.99)
              {
               // Circuit Breaker: Nunca adiciona lotes se ja atingiu o teto maximo do slot!
               if(MathAbs(actual_signed) >= max_slot_vol - 0.01 && MathAbs(target_signed) > MathAbs(actual_signed))
                  continue;

               if(!MQLInfoInteger(MQL_TESTER))
                 {
                  if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
                    {
                     if(!m_slots[k].real_synced)
                        ResetSlotPosition(k);
                     continue;
                    }
                  double live_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  double live_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                  if(!m_slots[k].real_synced && live_bid > 0.0 && live_ask > 0.0)
                    {
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 2.5)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.1f vs Atual=%.1f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round05(live_ask) : Round05(live_bid);
                     m_slots[k].p1_entry = Round05(live_bid);
                     m_slots[k].avg_price = Round05(live_bid);
                     double sl_d = MathMax(7.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(7.0, m_slots[k].init_tp_pts);
                     if(m_slots[k].dir == 1)
                       {
                        m_slots[k].curr_sl = Round05(fill_ref - sl_d);
                        m_slots[k].curr_tp = Round05(fill_ref + tp_d);
                        sl_srv = m_slots[k].curr_sl;
                        tp_srv = m_slots[k].curr_tp;
                       }
                     else
                       {
                        m_slots[k].curr_sl = Round05(fill_ref + sl_d);
                        m_slots[k].curr_tp = Round05(fill_ref - tp_d);
                        sl_srv = Round05(m_slots[k].curr_sl + 0.5);
                        tp_srv = Round05(m_slots[k].curr_tp + 0.5);
                       }
                    }
                 }

               DeletePendingOrdersForSlot(k);
               m_trade.SetExpertMagicNumber(slot_magic);
               double room = MathMax(0.0, max_slot_vol - MathAbs(actual_signed));
               double vol = MathRound(MathMin(MathAbs(diff), room));
               if(vol < 1.0 || vol > max_slot_vol)
                  continue;

               bool ok = false;
               if(diff > 0.0)
                  ok = m_trade.Buy(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               else
                  ok = m_trade.Sell(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);

               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = target_signed;

               if(ok)
                  m_slots[k].real_synced = true;
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                  ResetSlotPosition(k);
              }

            if(MathAbs(target_signed) >= 0.99 && MathAbs(actual_signed) >= 0.99)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i))
                    {
                     if(m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                       {
                        double cur_sl = m_pos.StopLoss();
                        double cur_tp = m_pos.TakeProfit();
                        if(MathAbs(cur_sl - sl_srv) >= 0.4 || MathAbs(cur_tp - tp_srv) >= 0.4)
                          {
                           m_trade.SetExpertMagicNumber(slot_magic);
                           m_trade.PositionModify(m_pos.Ticket(), sl_srv, tp_srv);
                          }
                       }
                    }
                 }
              }
           }
        }
      else
        {
         // Modo NETTING (apenas para Conta Netting + EA Portfolio Master unico no grafico)
         if(!MQLInfoInteger(MQL_TESTER) && (GetTickCount64() - m_last_net_sync_ms) < 4000)
            return;

         double target_net = 0.0;
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].enabled && m_slots[k].dir != 0)
              {
               int c_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(0, m_slots[k].lots));
               target_net += (double)(m_slots[k].dir * c_lots) * m_lot_mult;
              }
           }
         double max_port_net = 10.0 * m_lot_mult;
         if(target_net > max_port_net)  target_net = max_port_net;
         if(target_net < -max_port_net) target_net = -max_port_net;
         target_net = MathRound(target_net);

         double actual_net = 0.0;
         for(int i=PositionsTotal()-1; i>=0; i--)
           {
            if(m_pos.SelectByIndex(i))
              {
               if(m_pos.Symbol() == _Symbol)
                 {
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_net += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_net -= m_pos.Volume();
                 }
              }
           }

         double diff = target_net - actual_net;
         if(MathAbs(diff) >= 0.99)
           {
            m_trade.SetExpertMagicNumber(m_base_magic);
            double vol = MathRound(MathMin(MathAbs(diff), 3.0 * m_lot_mult));
            if(vol >= 1.0)
              {
               if(diff > 0.0)
                  m_trade.Buy(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
               else
                  m_trade.Sell(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_WDO_NET_SYNC");
               m_last_net_sync_ms = GetTickCount64();
              }
           }
        }
     }"""
    assert old_sync in txt, "old_sync not found in WDO core"
    txt = txt.replace(old_sync, new_sync, 1)

    # 7. In OnTickProcess(): guard SL_TP_SERVER with 5000ms in-flight check & remove duplicate SyncRealPositionsWithVirtualSlots()
    old_tick_sl = """            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
               string rsn = "SL_TP_SERVER";
               double exit_px = GetLastExitDealPrice(slot_magic, last_px, rsn);
               CloseVirtualSlot(k, exit_px, rsn);
              }"""
    new_tick_sl = """            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
               if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0 && (GetTickCount64() - m_last_order_ms[k]) < 5000)
                  continue;
               string rsn = "SL_TP_SERVER";
               double exit_px = GetLastExitDealPrice(slot_magic, last_px, rsn);
               CloseVirtualSlot(k, exit_px, rsn);
              }"""
    assert old_tick_sl in txt, "old_tick_sl not found in WDO core"
    txt = txt.replace(old_tick_sl, new_tick_sl, 1)

    old_dup_sync = """      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
         SyncRealPositionsWithVirtualSlots();
        }"""
    new_dup_sync = """      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
        }"""
    assert old_dup_sync in txt, "old_dup_sync not found in WDO core"
    txt = txt.replace(old_dup_sync, new_dup_sync, 1)

    with open(WDO_CORE_PATH, "w", encoding="utf-8-sig") as f:
        f.write(txt)
    print("[OK] Patched Jumba_WDO_GEX_NWE_Core.mqh")


def patch_win_core():
    with open(WIN_CORE_PATH, "r", encoding="utf-8-sig") as f:
        txt = f.read()

    # 1. Add m_last_order_ms[17], m_last_sent_lots[17], m_last_net_sync_ms to class members
    old_members = """   datetime          m_last_m5_bar_time;
   bool              m_state_reconciled;"""
    new_members = """   datetime          m_last_m5_bar_time;
   bool              m_state_reconciled;
   ulong             m_last_order_ms[17];
   double            m_last_sent_lots[17];
   ulong             m_last_net_sync_ms;"""
    assert old_members in txt, "old_members not found in WIN core"
    txt = txt.replace(old_members, new_members, 1)

    # 2. Initialize in constructor & Init
    old_ctor = """      m_last_m5_bar_time = 0;
      m_state_reconciled = false;"""
    new_ctor = """      m_last_m5_bar_time = 0;
      m_state_reconciled = false;
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }"""
    assert old_ctor in txt, "old_ctor not found in WIN core"
    txt = txt.replace(old_ctor, new_ctor, 1)

    old_init = """      m_base_magic = base_magic;
      m_single_id = 0;
      m_exec_mode = exec_mode;
      m_lot_mult = MathMax(1.0, MathRound(lot_mult));"""
    new_init = """      m_base_magic = base_magic;
      m_single_id = 0;
      m_exec_mode = exec_mode;
      m_lot_mult = MathMin(10.0, MathMax(1.0, MathRound(lot_mult)));
      m_last_net_sync_ms = 0;
      for(int k=0; k<=16; k++)
        {
         m_last_order_ms[k] = 0;
         m_last_sent_lots[k] = 0.0;
        }"""
    assert old_init in txt, "old_init not found in WIN core"
    txt = txt.replace(old_init, new_init, 1)

    # 3. In ConfigurePreset(): force EXEC_HEDGING_DIRECT_MAGIC on Hedging accounts or Single-Robot EAs, delete stale GlobalVariables
    old_cfg_end = """      m_slots[3].enabled  = false;
      m_slots[5].enabled  = false;
      m_slots[9].enabled  = false;
      m_slots[10].enabled = false;
      m_slots[11].enabled = false;

      m_state_reconciled = MQLInfoInteger(MQL_TESTER) ? true : false;"""
    new_cfg_end = """      m_slots[3].enabled  = false;
      m_slots[5].enabled  = false;
      m_slots[9].enabled  = false;
      m_slots[10].enabled = false;
      m_slots[11].enabled = false;

      long acc_margin_mode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(acc_margin_mode == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || m_single_id > 0 || GetSingleActiveSlotId() > 0)
        {
         if(m_exec_mode != EXEC_HEDGING_DIRECT_MAGIC)
            Print("[JUMBA WIN] Trava de Seguranca: Forcando EXEC_HEDGING_DIRECT_MAGIC (Conta Hedging ou Robo Individual).");
         m_exec_mode = EXEC_HEDGING_DIRECT_MAGIC;
        }
      else if(acc_margin_mode != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && m_exec_mode == EXEC_HEDGING_DIRECT_MAGIC)
        {
         Print("[JUMBA WIN] Conta NETTING detectada na corretora. Alternando automaticamente para EXEC_NETTING_VIRTUAL_SYNC.");
         m_exec_mode = EXEC_NETTING_VIRTUAL_SYNC;
        }

      if(!MQLInfoInteger(MQL_TESTER))
        {
         GlobalVariablesDeleteAll("JUMBA_LOTS_");
         GlobalVariablesDeleteAll("JUMBA_TIME_");
        }

      m_state_reconciled = MQLInfoInteger(MQL_TESTER) ? true : false;"""
    assert old_cfg_end in txt, "old_cfg_end not found in WIN core"
    txt = txt.replace(old_cfg_end, new_cfg_end, 1)

    # 4. Add GetSingleActiveSlotId() and GetMaxBaseLotsForSlot(int k) before StateFileName()
    old_state_fn = """   string            StateFileName()"""
    new_state_fn = """   int               GetSingleActiveSlotId()
     {
      if(m_single_id > 0)
         return m_single_id;
      int cnt = 0, last_k = 0;
      for(int k=1; k<=16; k++)
        {
         if(m_slots[k].enabled)
           {
            cnt++;
            last_k = k;
           }
        }
      return (cnt == 1) ? last_k : 0;
     }

   int               GetMaxBaseLotsForSlot(int k)
     {
      if(k >= 13 && k <= 16)
         return 3; // SmartGrid 1+2 lotes
      if(k == 11 || k == 12)
         return 2; // Piramidacao 1+1 lotes
      return 1;    // Demais estrategias operam estritamente 1 lote base
     }

   string            StateFileName()"""
    assert old_state_fn in txt, "old_state_fn not found in WIN core"
    txt = txt.replace(old_state_fn, new_state_fn, 1)

    # 5. Clamp lots in LoadVirtualStateFromDisk() and ReconcileWithBrokerOnStartup()
    old_win_load_lots = """               m_slots[k].dir                  = (int)StringToInteger(p[1]);
               m_slots[k].lots                 = (int)StringToInteger(p[2]);"""
    new_win_load_lots = """               m_slots[k].dir                  = (int)StringToInteger(p[1]);
               m_slots[k].lots                 = (int)MathMin((long)GetMaxBaseLotsForSlot(k), MathMax(0, StringToInteger(p[2])));"""
    assert old_win_load_lots in txt, "old_win_load_lots not found in WIN core"
    txt = txt.replace(old_win_load_lots, new_win_load_lots, 1)

    old_win_rec_lots = """               int pos_dir = (actual_lots > 0.0) ? 1 : -1;
               int pos_lots = MathMax(1, (int)MathRound(MathAbs(actual_lots) / m_lot_mult));"""
    new_win_rec_lots = """               int pos_dir = (actual_lots > 0.0) ? 1 : -1;
               int pos_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(1, (int)MathRound(MathAbs(actual_lots) / m_lot_mult)));"""
    assert old_win_rec_lots in txt, "old_win_rec_lots not found in WIN core"
    txt = txt.replace(old_win_rec_lots, new_win_rec_lots, 1)

    # 6. Replace SyncRealPositionsWithVirtualSlots() in WIN core
    old_win_sync = """   void              SyncRealPositionsWithVirtualSlots()
     {
      if(m_exec_mode == EXEC_NETTING_VIRTUAL_SYNC)
        {
         double target_net_lots = 0.0;
         if(MQLInfoInteger(MQL_TESTER))
           {
            for(int k=1; k<=16; k++)
              {
               if(m_slots[k].enabled)
                  target_net_lots += (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
              }
           }
         else
           {
            datetime now_loc = TimeLocal();
            for(int k=1; k<=16; k++)
              {
               string gv_lots = StringFormat("JUMBA_LOTS_%s_%d", _Symbol, k);
               string gv_time = StringFormat("JUMBA_TIME_%s_%d", _Symbol, k);
               if(m_slots[k].enabled)
                 {
                  double my_l = (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
                  GlobalVariableSet(gv_lots, my_l);
                  GlobalVariableSet(gv_time, (double)now_loc);
                  target_net_lots += my_l;
                 }
               else if(GlobalVariableCheck(gv_time) && (now_loc - (datetime)GlobalVariableGet(gv_time)) <= 90)
                 {
                  target_net_lots += GlobalVariableGet(gv_lots);
                 }
              }
           }
         target_net_lots = MathRound(target_net_lots);

         double actual_net_lots = 0.0;
         for(int i=PositionsTotal()-1; i>=0; i--)
           {
            if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol)
              {
               if(m_pos.PositionType() == POSITION_TYPE_BUY)
                  actual_net_lots += m_pos.Volume();
               else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                  actual_net_lots -= m_pos.Volume();
              }
           }

         double diff = target_net_lots - actual_net_lots;
         if(MathAbs(diff) >= 0.99)
           {
            m_trade.SetExpertMagicNumber(m_base_magic);
            if(diff > 0.0)
               m_trade.Buy(MathRound(diff), _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
            else
               m_trade.Sell(MathRound(-diff), _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
            SaveVirtualStateToDisk();
           }

         if(!MQLInfoInteger(MQL_TESTER) && MathAbs(target_net_lots) >= 0.99 && PositionSelect(_Symbol))
           {
            int net_dir = (target_net_lots > 0.0) ? 1 : -1;
            int open_cnt = 0;
            double worst_sl = 0.0;
            double best_tp  = 0.0;
            for(int k=1; k<=16; k++)
              {
               if(m_slots[k].enabled && m_slots[k].dir == net_dir && m_slots[k].curr_sl > 0.0)
                 {
                  open_cnt++;
                  if(net_dir == 1)
                    {
                     if(worst_sl == 0.0 || m_slots[k].curr_sl < worst_sl) worst_sl = m_slots[k].curr_sl;
                     if(best_tp == 0.0  || m_slots[k].curr_tp > best_tp)  best_tp  = m_slots[k].curr_tp;
                    }
                  else
                    {
                     if(worst_sl == 0.0 || m_slots[k].curr_sl > worst_sl) worst_sl = m_slots[k].curr_sl;
                     if(best_tp == 0.0  || m_slots[k].curr_tp < best_tp)  best_tp  = m_slots[k].curr_tp;
                    }
                 }
              }
            if(worst_sl > 0.0)
              {
               double pad = (open_cnt == 1) ? 0.0 : 25.0;
               double srv_sl = (net_dir == 1) ? Round5(worst_sl - pad) : Round5(worst_sl + pad);
               double srv_tp = (open_cnt == 1 && best_tp > 0.0 && !m_slots[m_single_id > 0 ? m_single_id : 1].partial_mode) ? Round5(best_tp) : 0.0;
               double cur_srv_sl = PositionGetDouble(POSITION_SL);
               double cur_srv_tp = PositionGetDouble(POSITION_TP);
               if(MathAbs(cur_srv_sl - srv_sl) >= 5.0 || MathAbs(cur_srv_tp - srv_tp) >= 5.0)
                  m_trade.PositionModify(_Symbol, srv_sl, srv_tp);
              }
           }
        }
      else
        {
         // EXEC_HEDGING_DIRECT_MAGIC: Cada slot k gerencia sua posição com MagicNumber = m_base_magic + k
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            ulong slot_magic = m_base_magic + (ulong)k;
            double target_lots = (double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult;
            double actual_lots = 0.0;

            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                 {
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_lots += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_lots -= m_pos.Volume();
                 }
              }

            if(target_lots == 0.0 && MathAbs(actual_lots) >= 0.99)
              {
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                     m_trade.PositionClose(m_pos.Ticket());
                 }
              }
            else if(MathAbs(target_lots - actual_lots) >= 0.99)
              {
               if(target_lots * actual_lots < 0.0)
                 {
                  for(int i=PositionsTotal()-1; i>=0; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                  actual_lots = 0.0;
                 }
               double delta = target_lots - actual_lots;
               double sl_srv = (m_slots[k].curr_sl > 0.0) ? Round5(m_slots[k].curr_sl) : 0.0;
               double tp_srv = (m_slots[k].curr_tp > 0.0) ? Round5(m_slots[k].curr_tp) : 0.0;
               if(!MQLInfoInteger(MQL_TESTER))
                 {
                  if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
                    {
                     if(!m_slots[k].real_synced)
                       {
                        ResetSlotPosition(k);
                        SaveVirtualStateToDisk();
                       }
                     continue;
                    }
                  double live_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  double live_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                  if(!m_slots[k].real_synced && live_bid > 0.0 && live_ask > 0.0)
                    {
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 150.0)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.0f vs Atual=%.0f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        SaveVirtualStateToDisk();
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round5(live_ask) : Round5(live_bid);
                     m_slots[k].p1_entry = Round5(live_bid);
                     m_slots[k].avg_price = Round5(live_bid);
                     double sl_d = MathMax(200.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(160.0, m_slots[k].init_tp_pts);
                     m_slots[k].curr_sl = (m_slots[k].dir == 1) ? Round5(fill_ref - sl_d) : Round5(fill_ref + sl_d);
                     m_slots[k].curr_tp = (m_slots[k].dir == 1) ? Round5(fill_ref + tp_d) : Round5(fill_ref - tp_d);
                     sl_srv = m_slots[k].curr_sl;
                     tp_srv = m_slots[k].curr_tp;
                    }
                 }
               m_trade.SetExpertMagicNumber(slot_magic);
               bool sent = false;
               // Se for reducao parcial de posicao existente no mesmo sentido, usa PositionClosePartial
               if(actual_lots != 0.0 && MathAbs(target_lots) < MathAbs(actual_lots) && target_lots * actual_lots > 0.0)
                 {
                  double vol_reduce = MathRound(MathAbs(delta));
                  for(int i=PositionsTotal()-1; i>=0 && vol_reduce >= 0.99; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                       {
                        double pv = m_pos.Volume();
                        if(pv <= vol_reduce + 0.01)
                          {
                           if(m_trade.PositionClose(m_pos.Ticket()))
                             {
                              vol_reduce -= pv;
                              sent = true;
                             }
                          }
                        else
                          {
                           if(m_trade.PositionClosePartial(m_pos.Ticket(), vol_reduce))
                             {
                              vol_reduce = 0.0;
                              sent = true;
                             }
                          }
                       }
                    }
                 }
               else if(delta > 0.0)
                  sent = m_trade.Buy(MathRound(delta), _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               else if(delta < 0.0)
                  sent = m_trade.Sell(MathRound(-delta), _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
               if(sent)
                 {
                  m_slots[k].real_synced = true;
                 }
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                 {
                  ResetSlotPosition(k);
                 }
               SaveVirtualStateToDisk();
              }

            // Sincroniza SL e TP físicos no servidor para todos os tickets deste MagicNumber
            if(MathAbs(target_lots) >= 0.99 && m_slots[k].curr_sl > 0.0)
              {
               double sl_srv = Round5(m_slots[k].curr_sl);
               double tp_srv = (m_slots[k].curr_tp > 0.0) ? Round5(m_slots[k].curr_tp) : 0.0;
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                    {
                     m_slots[k].real_synced = true;
                     if(MathAbs(m_pos.StopLoss() - sl_srv) >= 5.0 || MathAbs(m_pos.TakeProfit() - tp_srv) >= 5.0)
                        m_trade.PositionModify(m_pos.Ticket(), sl_srv, tp_srv);
                    }
                 }
              }
           }
        }
     }"""

    new_win_sync = """   void              SyncRealPositionsWithVirtualSlots()
     {
      // Trava Estrutural Absoluta: Conta HEDGING ou EA Individual SEMPRE opera em EXEC_HEDGING_DIRECT_MAGIC!
      if(AccountInfoInteger(ACCOUNT_MARGIN_MODE) == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING || m_single_id > 0 || GetSingleActiveSlotId() > 0)
         m_exec_mode = EXEC_HEDGING_DIRECT_MAGIC;

      if(m_exec_mode == EXEC_NETTING_VIRTUAL_SYNC)
        {
         if(!MQLInfoInteger(MQL_TESTER) && (GetTickCount64() - m_last_net_sync_ms) < 4000)
            return;

         double target_net_lots = 0.0;
         for(int k=1; k<=16; k++)
           {
            if(m_slots[k].enabled && m_slots[k].dir != 0)
              {
               int c_lots = MathMin(GetMaxBaseLotsForSlot(k), MathMax(0, m_slots[k].lots));
               target_net_lots += (double)(m_slots[k].dir * c_lots) * m_lot_mult;
              }
           }
         double max_port_net = 12.0 * m_lot_mult;
         if(target_net_lots > max_port_net)  target_net_lots = max_port_net;
         if(target_net_lots < -max_port_net) target_net_lots = -max_port_net;
         target_net_lots = MathRound(target_net_lots);

         double actual_net_lots = 0.0;
         for(int i=PositionsTotal()-1; i>=0; i--)
           {
            if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol)
              {
               if(m_pos.PositionType() == POSITION_TYPE_BUY)
                  actual_net_lots += m_pos.Volume();
               else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                  actual_net_lots -= m_pos.Volume();
              }
           }

         double diff = target_net_lots - actual_net_lots;
         if(MathAbs(diff) >= 0.99)
           {
            m_trade.SetExpertMagicNumber(m_base_magic);
            double vol = MathRound(MathMin(MathAbs(diff), 3.0 * m_lot_mult));
            if(vol >= 1.0)
              {
               if(diff > 0.0)
                  m_trade.Buy(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
               else
                  m_trade.Sell(vol, _Symbol, 0.0, 0.0, 0.0, "JUMBA_NET_SYNC");
               m_last_net_sync_ms = GetTickCount64();
               SaveVirtualStateToDisk();
              }
           }

         if(!MQLInfoInteger(MQL_TESTER) && MathAbs(target_net_lots) >= 0.99 && PositionSelect(_Symbol))
           {
            int net_dir = (target_net_lots > 0.0) ? 1 : -1;
            int open_cnt = 0;
            double worst_sl = 0.0;
            double best_tp  = 0.0;
            for(int k=1; k<=16; k++)
              {
               if(m_slots[k].enabled && m_slots[k].dir == net_dir && m_slots[k].curr_sl > 0.0)
                 {
                  open_cnt++;
                  if(net_dir == 1)
                    {
                     if(worst_sl == 0.0 || m_slots[k].curr_sl < worst_sl) worst_sl = m_slots[k].curr_sl;
                     if(best_tp == 0.0  || m_slots[k].curr_tp > best_tp)  best_tp  = m_slots[k].curr_tp;
                    }
                  else
                    {
                     if(worst_sl == 0.0 || m_slots[k].curr_sl > worst_sl) worst_sl = m_slots[k].curr_sl;
                     if(best_tp == 0.0  || m_slots[k].curr_tp < best_tp)  best_tp  = m_slots[k].curr_tp;
                    }
                 }
              }
            if(worst_sl > 0.0)
              {
               double pad = (open_cnt == 1) ? 0.0 : 25.0;
               double srv_sl = (net_dir == 1) ? Round5(worst_sl - pad) : Round5(worst_sl + pad);
               double srv_tp = (open_cnt == 1 && best_tp > 0.0 && !m_slots[m_single_id > 0 ? m_single_id : 1].partial_mode) ? Round5(best_tp) : 0.0;
               double cur_srv_sl = PositionGetDouble(POSITION_SL);
               double cur_srv_tp = PositionGetDouble(POSITION_TP);
               if(MathAbs(cur_srv_sl - srv_sl) >= 5.0 || MathAbs(cur_srv_tp - srv_tp) >= 5.0)
                  m_trade.PositionModify(_Symbol, srv_sl, srv_tp);
              }
           }
        }
      else
        {
         // EXEC_HEDGING_DIRECT_MAGIC: Cada slot k gerencia sua posição com MagicNumber = m_base_magic + k
         for(int k=1; k<=16; k++)
           {
            if(!m_slots[k].enabled)
               continue;
            ulong slot_magic = m_base_magic + (ulong)k;
            int max_base = GetMaxBaseLotsForSlot(k);
            if(m_slots[k].lots > max_base)
               m_slots[k].lots = max_base;
            if(m_slots[k].lots < 0)
               m_slots[k].lots = 0;

            double max_slot_vol = MathRound((double)max_base * m_lot_mult);
            double target_lots = MathRound((double)(m_slots[k].dir * m_slots[k].lots) * m_lot_mult);
            if(target_lots > max_slot_vol)  target_lots = max_slot_vol;
            if(target_lots < -max_slot_vol) target_lots = -max_slot_vol;

            double actual_lots = 0.0;
            for(int i=PositionsTotal()-1; i>=0; i--)
              {
               if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                 {
                  if(m_pos.PositionType() == POSITION_TYPE_BUY)
                     actual_lots += m_pos.Volume();
                  else if(m_pos.PositionType() == POSITION_TYPE_SELL)
                     actual_lots -= m_pos.Volume();
                 }
              }

            ulong now_ms = GetTickCount64();
            if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0)
              {
               ulong elapsed = now_ms - m_last_order_ms[k];
               if(elapsed < 1500 || (elapsed < 5000 && MathAbs(target_lots - m_last_sent_lots[k]) < 0.01))
                  continue;
              }

            if(target_lots == 0.0 && MathAbs(actual_lots) >= 0.99)
              {
               m_trade.SetExpertMagicNumber(slot_magic);
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                     m_trade.PositionClose(m_pos.Ticket());
                 }
               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = 0.0;
               continue;
              }
            else if(MathAbs(target_lots - actual_lots) >= 0.99)
              {
               if(target_lots * actual_lots < 0.0)
                 {
                  m_trade.SetExpertMagicNumber(slot_magic);
                  for(int i=PositionsTotal()-1; i>=0; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                        m_trade.PositionClose(m_pos.Ticket());
                    }
                  m_last_order_ms[k] = GetTickCount64();
                  m_last_sent_lots[k] = 0.0;
                  continue;
                 }

               // Circuit Breaker: Nunca adiciona lotes se ja atingiu o teto maximo do slot!
               if(MathAbs(actual_lots) >= max_slot_vol - 0.01 && MathAbs(target_lots) > MathAbs(actual_lots))
                  continue;

               double delta = target_lots - actual_lots;
               double sl_srv = (m_slots[k].curr_sl > 0.0) ? Round5(m_slots[k].curr_sl) : 0.0;
               double tp_srv = (m_slots[k].curr_tp > 0.0) ? Round5(m_slots[k].curr_tp) : 0.0;
               if(!MQLInfoInteger(MQL_TESTER))
                 {
                  if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
                    {
                     if(!m_slots[k].real_synced)
                       {
                        ResetSlotPosition(k);
                        SaveVirtualStateToDisk();
                       }
                     continue;
                    }
                  double live_bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                  double live_ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                  if(!m_slots[k].real_synced && live_bid > 0.0 && live_ask > 0.0)
                    {
                     if(MathAbs(live_bid - m_slots[k].p1_entry) > 150.0)
                       {
                        PrintFormat("[JUMBA %s] Entrada cancelada por atraso/slippage (Sinal=%.0f vs Atual=%.0f)",
                                    m_slots[k].name, m_slots[k].p1_entry, live_bid);
                        ResetSlotPosition(k);
                        SaveVirtualStateToDisk();
                        continue;
                       }
                     double fill_ref = (m_slots[k].dir == 1) ? Round5(live_ask) : Round5(live_bid);
                     m_slots[k].p1_entry = Round5(live_bid);
                     m_slots[k].avg_price = Round5(live_bid);
                     double sl_d = MathMax(200.0, m_slots[k].init_sl_pts);
                     double tp_d = MathMax(160.0, m_slots[k].init_tp_pts);
                     m_slots[k].curr_sl = (m_slots[k].dir == 1) ? Round5(fill_ref - sl_d) : Round5(fill_ref + sl_d);
                     m_slots[k].curr_tp = (m_slots[k].dir == 1) ? Round5(fill_ref + tp_d) : Round5(fill_ref - tp_d);
                     sl_srv = m_slots[k].curr_sl;
                     tp_srv = m_slots[k].curr_tp;
                    }
                 }
               DeletePendingOrdersForSlot(k);
               m_trade.SetExpertMagicNumber(slot_magic);
               bool sent = false;
               // Se for reducao parcial de posicao existente no mesmo sentido, usa PositionClosePartial
               if(actual_lots != 0.0 && MathAbs(target_lots) < MathAbs(actual_lots) && target_lots * actual_lots > 0.0)
                 {
                  double vol_reduce = MathRound(MathAbs(delta));
                  for(int i=PositionsTotal()-1; i>=0 && vol_reduce >= 0.99; i--)
                    {
                     if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                       {
                        double pv = m_pos.Volume();
                        if(pv <= vol_reduce + 0.01)
                          {
                           if(m_trade.PositionClose(m_pos.Ticket()))
                             {
                              vol_reduce -= pv;
                              sent = true;
                             }
                          }
                        else
                          {
                           if(m_trade.PositionClosePartial(m_pos.Ticket(), vol_reduce))
                             {
                              vol_reduce = 0.0;
                              sent = true;
                             }
                          }
                       }
                    }
                 }
               else
                 {
                  double room = MathMax(0.0, max_slot_vol - MathAbs(actual_lots));
                  double vol = MathRound(MathMin(MathAbs(delta), room));
                  if(vol < 1.0 || vol > max_slot_vol)
                     continue;
                  if(delta > 0.0)
                     sent = m_trade.Buy(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
                  else if(delta < 0.0)
                     sent = m_trade.Sell(vol, _Symbol, 0.0, sl_srv, tp_srv, m_slots[k].name);
                 }

               m_last_order_ms[k] = GetTickCount64();
               m_last_sent_lots[k] = target_lots;

               if(sent)
                 {
                  m_slots[k].real_synced = true;
                 }
               else if(!MQLInfoInteger(MQL_TESTER) && !m_slots[k].real_synced)
                 {
                  ResetSlotPosition(k);
                 }
               SaveVirtualStateToDisk();
              }

            // Sincroniza SL e TP físicos no servidor para todos os tickets deste MagicNumber
            if(MathAbs(target_lots) >= 0.99 && MathAbs(actual_lots) >= 0.99 && m_slots[k].curr_sl > 0.0)
              {
               double sl_srv = Round5(m_slots[k].curr_sl);
               double tp_srv = (m_slots[k].curr_tp > 0.0) ? Round5(m_slots[k].curr_tp) : 0.0;
               for(int i=PositionsTotal()-1; i>=0; i--)
                 {
                  if(m_pos.SelectByIndex(i) && m_pos.Symbol() == _Symbol && m_pos.Magic() == slot_magic)
                    {
                     m_slots[k].real_synced = true;
                     if(MathAbs(m_pos.StopLoss() - sl_srv) >= 5.0 || MathAbs(m_pos.TakeProfit() - tp_srv) >= 5.0)
                        m_trade.PositionModify(m_pos.Ticket(), sl_srv, tp_srv);
                    }
                 }
              }
           }
        }
     }"""
    assert old_win_sync in txt, "old_win_sync not found in WIN core"
    txt = txt.replace(old_win_sync, new_win_sync, 1)

    # 7. In OnTickProcess(): guard SL_TP_SERVER with 5000ms in-flight check & remove duplicate SyncRealPositionsWithVirtualSlots()
    old_win_tick_sl = """            // B. Posição Aberta foi encerrada nativamente pelo SL ou TP no Servidor da Corretora / Tester!
            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
               string rsn = "SL_TP_SERVER";
               double exit_px = GetLastExitDealPrice(slot_magic, last_px, rsn);
               CloseVirtualSlot(k, exit_px, rsn);
              }"""
    new_win_tick_sl = """            // B. Posição Aberta foi encerrada nativamente pelo SL ou TP no Servidor da Corretora / Tester!
            else if(m_slots[k].dir != 0 && m_slots[k].real_synced && MathAbs(actual_lots) < 0.01)
              {
               if(!MQLInfoInteger(MQL_TESTER) && m_last_order_ms[k] > 0 && (GetTickCount64() - m_last_order_ms[k]) < 5000)
                  continue;
               string rsn = "SL_TP_SERVER";
               double exit_px = GetLastExitDealPrice(slot_magic, last_px, rsn);
               CloseVirtualSlot(k, exit_px, rsn);
              }"""
    assert old_win_tick_sl in txt, "old_win_tick_sl not found in WIN core"
    txt = txt.replace(old_win_tick_sl, new_win_tick_sl, 1)

    old_win_dup_sync = """      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
         SyncRealPositionsWithVirtualSlots();
        }"""
    new_win_dup_sync = """      if(curr_bar_time != m_last_m5_bar_time)
        {
         OnNewM5Bar(curr_bar_time, today_str);
         m_last_m5_bar_time = curr_bar_time;
        }"""
    assert old_win_dup_sync in txt, "old_win_dup_sync not found in WIN core"
    txt = txt.replace(old_win_dup_sync, new_win_dup_sync, 1)

    # 8. In OnNewM5Bar(): add live trade allowed / slippage guard before evaluating signals
    old_win_bar_guard = """      // Se estamos na mesma sessão, avalia sinais para as estratégias que estão FLAT
      if(b1_date != today_str)
         return;"""
    new_win_bar_guard = """      // Se estamos na mesma sessão, avalia sinais para as estratégias que estão FLAT
      if(b1_date != today_str)
         return;

      if(!MQLInfoInteger(MQL_TESTER))
        {
         if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
            return;
         double live_b = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(live_b > 0.0)
           {
            if(MathAbs(live_b - new_bar_open) > 150.0)
               return;
            new_bar_open = Round5(live_b);
           }
        }"""
    assert old_win_bar_guard in txt, "old_win_bar_guard not found in WIN core"
    txt = txt.replace(old_win_bar_guard, new_win_bar_guard, 1)

    # 9. In ArmPendingOrder(): call DeletePendingOrdersForSlot(k) before placing pending order and clamp vol
    old_win_arm = """         ulong slot_magic = m_base_magic + (ulong)k;
         m_trade.SetExpertMagicNumber(slot_magic);
         double vol = MathRound((double)MathMax(1, init_lots) * m_lot_mult);"""
    new_win_arm = """         ulong slot_magic = m_base_magic + (ulong)k;
         DeletePendingOrdersForSlot(k);
         m_trade.SetExpertMagicNumber(slot_magic);
         double vol = MathRound((double)MathMin(GetMaxBaseLotsForSlot(k), MathMax(1, init_lots)) * m_lot_mult);"""
    assert old_win_arm in txt, "old_win_arm not found in WIN core"
    txt = txt.replace(old_win_arm, new_win_arm, 1)

    with open(WIN_CORE_PATH, "w", encoding="utf-8-sig") as f:
        f.write(txt)
    print("[OK] Patched Jumba_GEX_NWE_Core.mqh")


def patch_fix_profile_script():
    with open(FIX_PRF_PATH, "r", encoding="utf-8") as f:
        txt = f.read()

    old_wdo_inp = """        inp_str = f\"\"\"InpBaseMagic={base_magic}
InpLotMultiplier=1.0
InpMaxDailyLossBRL=2000.0
InpExecMode=1
InpDrawGexLevels=true
InpShowHud=true\"\"\""""
    new_wdo_inp = """        inp_str = f\"\"\"InpBaseMagic={base_magic}
InpLotMultiplier=1.0
InpMaxDailyLossBRL=2000.0
InpExecMode=0
InpDrawGexLevels=true
InpShowHud=true\"\"\""""
    assert old_wdo_inp in txt, "old_wdo_inp not found in fix_18_wf_monitor_profile.py"
    txt = txt.replace(old_wdo_inp, new_wdo_inp, 1)

    # Also ensure all .ex5/.mq5 in MT5_EXP_SUB are copied to dst_exp_root as well!
    old_copy = """        for f in os.listdir(MT5_EXP_SUB):
            if f.endswith((".ex5", ".mq5")):
                shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_sub, f))"""
    new_copy = """        for f in os.listdir(MT5_EXP_SUB):
            if f.endswith((".ex5", ".mq5")):
                shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_sub, f))
                shutil.copy2(os.path.join(MT5_EXP_SUB, f), os.path.join(dst_exp_root, f))"""
    assert old_copy in txt, "old_copy not found in fix_18_wf_monitor_profile.py"
    txt = txt.replace(old_copy, new_copy, 1)

    with open(FIX_PRF_PATH, "w", encoding="utf-8") as f:
        f.write(txt)
    print("[OK] Patched fix_18_wf_monitor_profile.py")


if __name__ == "__main__":
    patch_wdo_core()
    patch_win_core()
    patch_fix_profile_script()

