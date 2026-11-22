//+------------------------------------------------------------------+
//|                                          Jumba_LicenseGuard.mqh  |
//|   Camada 4 Anti-Rateio (Tier QUANT): verificacao de licenca MT5  |
//|   por AccountInfoInteger(ACCOUNT_LOGIN) + valid_until (API Cloud)|
//|                                                                  |
//|   Uso opt-in via CJumbaSafetyGuard::EnableLicenseCheck(...).     |
//|   Ordens reduces_only=true nunca sao bloqueadas para nunca       |
//|   impedir fechamento de posicoes abertas.                        |
//+------------------------------------------------------------------+
#property strict

#ifndef JUMBA_LICENSE_GUARD_MQH
#define JUMBA_LICENSE_GUARD_MQH

class CJumbaLicenseGuard
  {
private:
   string            m_api_url;
   string            m_token;
   long              m_expected_login;
   bool              m_authorized;
   int               m_last_check_day;
   int               m_valid_until_key;
   string            m_last_reason;
   ulong             m_last_attempt_ms;

   int               TodayKey()
     {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent() > 0 ? TimeCurrent() : TimeLocal(), dt);
      return dt.year * 10000 + dt.mon * 100 + dt.day;
     }

   string            CacheFileName(const long login)
     {
      return "mw_license_" + IntegerToString(login) + ".dat";
     }

   int               ParseDateKey(const string date_str)
     {
      // Converte "YYYY-MM-DD" para inteiro YYYYMMDD
      if(StringLen(date_str) < 10)
         return 0;
      string clean = StringSubstr(date_str, 0, 4) + StringSubstr(date_str, 5, 2) + StringSubstr(date_str, 8, 2);
      return (int)StringToInteger(clean);
     }

   string            ExtractJsonString(const string json, const string key)
     {
      string pat = "\"" + key + "\"";
      int idx = StringFind(json, pat);
      if(idx < 0)
         return "";
      int colon = StringFind(json, ":", idx + StringLen(pat));
      if(colon < 0)
         return "";
      int q1 = StringFind(json, "\"", colon + 1);
      if(q1 < 0)
         return "";
      int q2 = StringFind(json, "\"", q1 + 1);
      if(q2 <= q1)
         return "";
      return StringSubstr(json, q1 + 1, q2 - q1 - 1);
     }

   void              SaveCache(const long login, const int check_day, const int valid_until_key)
     {
      int h = FileOpen(CacheFileName(login), FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(h == INVALID_HANDLE)
         return;
      FileWriteString(h, IntegerToString(check_day) + ";" + IntegerToString(valid_until_key));
      FileClose(h);
     }

   void              ClearCache(const long login)
     {
      if(FileIsExist(CacheFileName(login), FILE_COMMON))
         FileDelete(CacheFileName(login), FILE_COMMON);
     }

   bool              LoadCache(const long login)
     {
      if(!FileIsExist(CacheFileName(login), FILE_COMMON))
         return false;
      int h = FileOpen(CacheFileName(login), FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
      if(h == INVALID_HANDLE)
         return false;
      string content = FileReadString(h);
      FileClose(h);

      string parts[];
      if(StringSplit(content, ';', parts) < 2)
         return false;
      int cached_day = (int)StringToInteger(parts[0]);
      int valid_key = (int)StringToInteger(parts[1]);
      int today = TodayKey();
      if(cached_day == today && valid_key >= today)
        {
         m_last_check_day = cached_day;
         m_valid_until_key = valid_key;
         m_authorized = true;
         m_last_reason = "OK_CACHE";
         return true;
        }
      return false;
     }

public:
                     CJumbaLicenseGuard()
     {
      m_api_url = "";
      m_token = "";
      m_expected_login = 0;
      m_authorized = false;
      m_last_check_day = 0;
      m_valid_until_key = 0;
      m_last_reason = "NOT_CONFIGURED";
      m_last_attempt_ms = 0;
     }

   string            LastReason() { return m_last_reason; }

   void              Configure(const string api_url, const string license_token, const long expected_login = 0)
     {
      m_api_url = api_url;
      m_token = license_token;
      m_expected_login = expected_login;
      m_authorized = false;
      m_last_check_day = 0;
      m_valid_until_key = 0;
      m_last_reason = "PENDING";
      m_last_attempt_ms = 0;
     }

   bool              VerifyRemote()
     {
      if(MQLInfoInteger(MQL_TESTER))
        {
         m_authorized = true;
         m_last_reason = "TESTER";
         return true;
        }

      long login = AccountInfoInteger(ACCOUNT_LOGIN);
      int today = TodayKey();

      if(m_expected_login > 0 && login != m_expected_login)
        {
         m_authorized = false;
         m_last_reason = "ACCOUNT_MISMATCH";
         ClearCache(login);
         return false;
        }

      if(StringLen(m_api_url) == 0 || StringLen(m_token) == 0)
        {
         m_authorized = false;
         m_last_reason = "MISSING_CREDENTIALS";
         return false;
        }

      m_last_attempt_ms = GetTickCount64();

      string base = m_api_url;
      if(StringSubstr(base, StringLen(base) - 1, 1) == "/")
         base = StringSubstr(base, 0, StringLen(base) - 1);

      string url = StringFormat("%s/api/v1/mt5/verify?account_login=%I64d&token=%s&symbol=%s",
                                base, login, m_token, _Symbol);
      char post[];
      char result[];
      string res_headers = "";
      ResetLastError();
      int status = WebRequest("GET", url, "", NULL, 3000, post, 0, result, res_headers);

      if(status == 200)
        {
         string body = CharArrayToString(result, 0, -1, CP_UTF8);
         bool is_auth = (StringFind(body, "\"authorized\":true") >= 0 || StringFind(body, "\"authorized\": true") >= 0);
         if(is_auth)
           {
            string vu_str = ExtractJsonString(body, "valid_until");
            int vu_key = ParseDateKey(vu_str);
            if(vu_key > 0 && today > vu_key)
              {
               m_authorized = false;
               m_valid_until_key = vu_key;
               m_last_reason = "EXPIRED";
               ClearCache(login);
               return false;
              }
            m_authorized = true;
            m_last_check_day = today;
            m_valid_until_key = (vu_key > 0) ? vu_key : today;
            m_last_reason = "OK";
            SaveCache(login, today, m_valid_until_key);
            return true;
           }

         string reason = ExtractJsonString(body, "reason");
         m_authorized = false;
         m_last_check_day = today;
         m_last_reason = (StringLen(reason) > 0) ? reason : "UNAUTHORIZED";
         ClearCache(login);
         return false;
        }

      int err = GetLastError();
      if(err == 4060)
         PrintFormat("[MAGICWALLS LICENSE] Adicione %s em Ferramentas -> Opcoes -> Expert Advisors -> Permitir WebRequest.", base);

      // Tolerancia breve apenas para o proprio dia se ja validado hoje; no dia seguinte bloqueia
      if(LoadCache(login))
         return true;

      m_authorized = false;
      m_last_reason = StringFormat("HTTP_%d_ERR_%d", status, err);
      return false;
     }

   bool              IsAuthorized()
     {
      if(MQLInfoInteger(MQL_TESTER))
         return true;

      int today = TodayKey();
      long login = AccountInfoInteger(ACCOUNT_LOGIN);
      if(m_expected_login > 0 && login != m_expected_login)
        {
         m_authorized = false;
         m_last_reason = "ACCOUNT_MISMATCH";
         return false;
        }

      if(m_authorized && m_last_check_day == today && (m_valid_until_key == 0 || today <= m_valid_until_key))
         return true;

      if(LoadCache(login))
         return true;

      ulong now_ms = GetTickCount64();
      if(m_last_attempt_ms == 0 || (now_ms - m_last_attempt_ms) >= 60000)
         return VerifyRemote();

      return false;
     }
  };

#endif
