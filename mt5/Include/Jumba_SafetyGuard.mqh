//+------------------------------------------------------------------+
//|                                          Jumba_SafetyGuard.mqh  |
//|   Kill-switch anti-loop compartilhado pelos motores WIN e WDO    |
//|                                                                  |
//|   Incidente 03/11/2026: 7 EAs WDO em cascata (1->6->36->216...)  |
//|   executaram 8.963 contratos em 258 negocios. Esta trava impede  |
//|   que qualquer EA Jumba envie ordem de abertura quando:          |
//|     1) o volume da ordem excede o teto por ordem;                |
//|     2) a exposicao bruta Jumba no simbolo excede o teto;         |
//|     3) o EA enviou ordens demais em 60s (taxa de loop);          |
//|     4) outro EA Jumba ja acionou o kill-switch no simbolo hoje;  |
//|     5) conta NETTING com EA individual (posicao unica por ativo  |
//|        torna o controle por MagicNumber impossivel).             |
//|   Ao disparar: cancela pendentes proprias, grava a GlobalVariable|
//|   JUMBA_KILL_<SIMBOLO> (vale ate o fim do dia) e emite Alert.    |
//|   Para rearmar no mesmo dia: apague a GlobalVariable (F3) e      |
//|   reinicie os EAs.                                               |
//+------------------------------------------------------------------+
#property strict

#ifndef JUMBA_SAFETY_GUARD_MQH
#define JUMBA_SAFETY_GUARD_MQH

#include "Jumba_LicenseGuard.mqh"

class CJumbaSafetyGuard
  {
private:
   string            m_tag;            // "WIN" / "WDO" para logs
   long              m_magic_lo;       // faixa de magics Jumba deste motor
   long              m_magic_hi;
   double            m_max_order_vol;  // teto por ordem (contratos)
   double            m_max_gross_vol;  // teto de exposicao bruta Jumba no simbolo
   int               m_max_orders_60s; // teto de ordens enviadas por este EA em 60s
   ulong             m_order_ms[];     // timestamps (ms) das ultimas ordens
   ulong             m_last_stop_log_ms;
   bool              m_halted;
   string            m_reason;
   bool              m_license_enabled;
   CJumbaLicenseGuard m_license;

   string            KillName()            { return "JUMBA_KILL_" + _Symbol; }
   string            DailyStopGlobalKey()  { return "JUMBA_DAILY_STOP_GLOBAL"; }
   string            DailyStopAssetKey()   { return (StringFind(m_tag, "WDO") >= 0) ? "JUMBA_DAILY_STOP_WDO" : "JUMBA_DAILY_STOP_WIN"; }

   bool              IsDateGvActive(const string gv_name)
     {
      if(MQLInfoInteger(MQL_TESTER))
         return false;
      if(!GlobalVariableCheck(gv_name))
         return false;
      double val = GlobalVariableGet(gv_name);
      double today = TodayKey();
      if(MathAbs(val - today) < 0.5)
         return true;
      if(val > 0.0 && val < today - 0.5)
         GlobalVariableDel(gv_name); // dia anterior: limpa automaticamente
      return false;
     }

   double            TodayKey()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent() > 0 ? TimeCurrent() : TimeLocal(), dt);
      return (double)(dt.year * 10000 + dt.mon * 100 + dt.day);
     }

public:
                     CJumbaSafetyGuard()
     {
      m_tag = "JUMBA";
      m_magic_lo = 0;
      m_magic_hi = 0;
      m_max_order_vol = 3.0;
      m_max_gross_vol = 48.0;
      m_max_orders_60s = 8;
      m_last_stop_log_ms = 0;
      m_halted = false;
      m_reason = "";
      m_license_enabled = false;
      ArrayResize(m_order_ms, 0);
     }

   void              Configure(string tag, long base_magic, double lot_mult, int active_slots)
     {
      m_tag = tag;
      m_magic_lo = base_magic;
      m_magic_hi = base_magic + 16;
      double lm = MathMax(1.0, lot_mult);
      m_max_order_vol = 3.0 * lm;                  // maior lote base de qualquer slot = 3
      m_max_gross_vol = 3.0 * 16.0 * lm;           // 16 slots x 3 lotes x multiplicador
      m_max_orders_60s = 6 + 3 * MathMax(1, active_slots);
      m_last_stop_log_ms = 0;
      m_halted = false;
      m_reason = "";
      m_license_enabled = false;
      ArrayResize(m_order_ms, 0);
     }

   // Opt-in para versoes comerciais (Tier QUANT): ativa verificacao de conta + expiracao via API Cloud
   bool              EnableLicenseCheck(const string api_url, const string license_token, const long expected_login = 0)
     {
      m_license_enabled = true;
      m_license.Configure(api_url, license_token, expected_login);
      return m_license.VerifyRemote();
     }

   bool              IsHalted()   { return m_halted; }
   string            Reason()     { return m_reason; }
   bool              IsDailyStopGlobalActive() { return IsDateGvActive(DailyStopGlobalKey()); }
   bool              IsDailyStopAssetActive()  { return IsDateGvActive(DailyStopAssetKey()); }
   bool              IsDailyStopActive()       { return IsDailyStopGlobalActive() || IsDailyStopAssetActive(); }

   string            DailyStopReason()
     {
      if(IsDailyStopGlobalActive())
         return "STOP DIARIO GLOBAL ATINGIDO";
      if(IsDailyStopAssetActive())
         return (StringFind(m_tag, "WDO") >= 0) ? "STOP DIARIO WDO ATINGIDO" : "STOP DIARIO WIN ATINGIDO";
      return "";
     }

   // Exposicao bruta (soma de |volume|) de todas as posicoes Jumba deste motor no simbolo
   double            JumbaGrossExposure()
     {
      double gross = 0.0;
      for(int i=PositionsTotal()-1; i>=0; i--)
        {
         ulong t = PositionGetTicket(i);
         if(t == 0 || PositionGetString(POSITION_SYMBOL) != _Symbol)
            continue;
         long mg = PositionGetInteger(POSITION_MAGIC);
         if(mg >= m_magic_lo && mg <= m_magic_hi)
            gross += PositionGetDouble(POSITION_VOLUME);
        }
      return gross;
     }

   void              Halt(string why)
     {
      if(m_halted)
         return;
      m_halted = true;
      m_reason = why;
      if(!MQLInfoInteger(MQL_TESTER))
         GlobalVariableSet(KillName(), TodayKey());
      // Cancela todas as pendentes Jumba deste motor no simbolo (nao zera posicoes: decisao manual)
      CTrade tr;
      for(int i=OrdersTotal()-1; i>=0; i--)
        {
         ulong ot = OrderGetTicket(i);
         if(ot == 0 || OrderGetString(ORDER_SYMBOL) != _Symbol)
            continue;
         long mg = OrderGetInteger(ORDER_MAGIC);
         if(mg >= m_magic_lo && mg <= m_magic_hi)
            tr.OrderDelete(ot);
        }
      string msg = StringFormat("[%s KILL-SWITCH] %s | %s | Novas ordens BLOQUEADAS. Verifique posicoes manualmente.",
                                m_tag, _Symbol, why);
      Print(msg);
      if(!MQLInfoInteger(MQL_TESTER))
         Alert(msg);
     }

   // Chamado a cada tick: propaga kill-switch acionado por outro EA no mesmo simbolo
   bool              CheckGlobalKill()
     {
      if(m_halted)
         return true;
      if(MQLInfoInteger(MQL_TESTER))
         return false;
      if(GlobalVariableCheck(KillName()))
        {
         if(GlobalVariableGet(KillName()) == TodayKey())
           {
            Halt("Kill-switch global acionado por outro EA Jumba neste simbolo hoje");
            return true;
           }
         GlobalVariableDel(KillName()); // de outro dia: rearma automaticamente
        }
      return false;
     }

   // Trava de conta NETTING com EA individual (chamar no Init / ConfigurePreset)
   void              CheckAccountMode(bool individual_ea)
     {
      if(MQLInfoInteger(MQL_TESTER))
         return;
      long mm = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
      if(individual_ea && mm != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
        {
         // Nao grava kill global: e erro de configuracao deste EA, nao loop de mercado
         m_halted = true;
         m_reason = "Conta NETTING com EA individual: use o Portfolio Master (um unico EA por ativo)";
         string msg = StringFormat("[%s KILL-SWITCH] %s | %s", m_tag, _Symbol, m_reason);
         Print(msg);
         Alert(msg);
        }
     }

   // Gate obrigatorio antes de QUALQUER ordem que possa abrir/aumentar exposicao.
   // reduces_only=true: ordem que apenas reduz exposicao (fechamento) - liberada mesmo com teto bruto.
   bool              AllowOrder(double vol, bool reduces_only=false)
     {
      if(CheckGlobalKill())
         return false;
      if(!reduces_only && IsDailyStopActive())
        {
         ulong now_log = GetTickCount64();
         if(now_log - m_last_stop_log_ms >= 60000)
           {
            m_last_stop_log_ms = now_log;
            PrintFormat("[%s DAILY-STOP] %s | Nova ordem bloqueada: %s", m_tag, _Symbol, DailyStopReason());
           }
         return false;
        }
      if(!reduces_only && m_license_enabled && !m_license.IsAuthorized())
        {
         ulong now_lic_log = GetTickCount64();
         if(now_lic_log - m_last_stop_log_ms >= 60000)
           {
            m_last_stop_log_ms = now_lic_log;
            PrintFormat("[%s LICENSE] %s | Nova ordem bloqueada (%s). Renove sua licenca QUANT.", m_tag, _Symbol, m_license.LastReason());
           }
         return false;
        }
      if(vol <= 0.0)
         return false;
      if(vol > m_max_order_vol + 0.01)
        {
         Halt(StringFormat("Volume por ordem %.0f > teto %.0f", vol, m_max_order_vol));
         return false;
        }
      if(!reduces_only)
        {
         double gross = JumbaGrossExposure();
         if(gross + vol > m_max_gross_vol + 0.01)
           {
            Halt(StringFormat("Exposicao bruta Jumba %.0f + %.0f > teto %.0f", gross, vol, m_max_gross_vol));
            return false;
           }
        }
      if(!MQLInfoInteger(MQL_TESTER))
        {
         ulong now = GetTickCount64();
         int keep = 0;
         int n = ArraySize(m_order_ms);
         for(int i=0; i<n; i++)
            if(now - m_order_ms[i] < 60000)
               m_order_ms[keep++] = m_order_ms[i];
         ArrayResize(m_order_ms, keep);
         if(keep >= m_max_orders_60s)
           {
            Halt(StringFormat("%d ordens em 60s (teto %d): padrao de loop", keep, m_max_orders_60s));
            return false;
           }
         ArrayResize(m_order_ms, keep + 1);
         m_order_ms[keep] = now;
        }
      return true;
     }
  };

#endif
