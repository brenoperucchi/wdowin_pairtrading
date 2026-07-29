import os
import sys
import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def parse_portuguese_date(date_str):
    """
    Parses a date string in Portuguese format like "segunda-feira, 27 de julho de 2026",
    "27 de julho", or "Hoje, 27 de julho" and returns a datetime.date object.
    """
    try:
        date_str = date_str.replace('\xa0', ' ').strip()
        if "hoje" in date_str.lower():
            return datetime.date.today()
        if "," in date_str:
            date_str = date_str.split(",")[1].strip()
        parts = [p.strip() for p in date_str.split(" de ")]
        months = {
            "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4, "maio": 5, "junho": 6,
            "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
        }
        if len(parts) == 3:
            day = int(parts[0])
            month_name = parts[1].lower()
            year = int(parts[2])
            if month_name in months:
                return datetime.date(year, months[month_name], day)
        elif len(parts) == 2:
            day = int(parts[0])
            month_name = parts[1].lower()
            year = datetime.date.today().year
            if month_name in months:
                return datetime.date(year, months[month_name], day)
    except Exception:
        pass
    return None

def fetch_economic_calendar():
    """
    Busca o calendário econômico do dia (Brasil BRL e EUA USD) via Investing.com widget,
    classifica por impacto (Alto, Médio, Baixo) e por horário de Brasília (GMT-3),
    escrevendo no stdout (para o log diário) e salvando em gex/docs/DAILY_ECONOMIC_CALENDAR.txt.
    """
    url = "https://ec.forexprostools.com/?columns=time,country,importance,event&calType=week&timeZone=12&lang=12"
    
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    gex_dir = os.path.dirname(engine_dir)
    docs_dir = os.path.join(gex_dir, 'docs')
    os.makedirs(docs_dir, exist_ok=True)
    report_path = os.path.join(docs_dir, 'DAILY_ECONOMIC_CALENDAR.txt')
    
    today = datetime.date.today()
    today_str = today.strftime("%d/%m/%Y")
    
    output_lines = []
    output_lines.append("============================================================")
    output_lines.append(f"  CALENDÁRIO ECONÔMICO (BRASIL & EUA) - {today_str}")
    output_lines.append("  Fuso Horário: Brasília (GMT-3) | Fonte: Investing.com")
    output_lines.append("============================================================")
    
    events_high = []
    events_medium = []
    events_low = []
    
    for attempt in range(1, 4):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page.set_extra_http_headers({
                    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector("tr.eventRow", timeout=25000)
                page.wait_for_timeout(2000)
                content = page.content()
                browser.close()
                
            soup = BeautifulSoup(content, 'html.parser')
            table = soup.select_one("table.ecoCalTable")
            current_date = None
            
            local_high = []
            local_medium = []
            local_low = []
            
            if table:
                for r in table.select("tr"):
                    classes = r.get("class", [])
                    if 'theader' in classes:
                        current_date = parse_portuguese_date(r.text.strip())
                    elif 'eventRow' in classes and current_date == today:
                        time_td = r.select_one("td.time")
                        country_td = r.select_one("td.flagCur")
                        event_td = r.select_one("td.event")
                        sentiment_td = r.select_one("td.sentiment")
                        
                        time_val = time_td.text.strip() if time_td else ""
                        country_val = country_td.text.strip() if country_td else ""
                        event_val = event_td.text.strip() if event_td else ""
                        
                        if country_val in ['USD', 'BRL'] and time_val and event_val:
                            bulls = 1
                            if sentiment_td:
                                img_key = str(sentiment_td.get("data-img_key") or "")
                                if "bull3" in img_key:
                                    bulls = 3
                                elif "bull2" in img_key:
                                    bulls = 2
                                elif "bull1" in img_key:
                                    bulls = 1
                                else:
                                    full_bulls = len(sentiment_td.select("i.grayFullBullishIcon"))
                                    if full_bulls > 0:
                                        bulls = full_bulls
                                        
                            event_item = {
                                "time": time_val,
                                "country": country_val,
                                "event": event_val
                            }
                            
                            if bulls >= 3:
                                local_high.append(event_item)
                            elif bulls == 2:
                                local_medium.append(event_item)
                            else:
                                local_low.append(event_item)
                                
            if local_high or local_medium or local_low:
                events_high = local_high
                events_medium = local_medium
                events_low = local_low
                break
        except Exception:
            import time
            time.sleep(2)

    # Formatar seções por impacto
    if events_high:
        events_high.sort(key=lambda x: x['time'])
        output_lines.append("\n 🔴 ALTO IMPACTO (Super Quarta / Volatilidade Máxima):")
        for e in events_high:
            output_lines.append(f"   - [{e['time']}] [{e['country']}] {e['event']}")
            
    if events_medium:
        events_medium.sort(key=lambda x: x['time'])
        output_lines.append("\n 🟡 MÉDIO IMPACTO:")
        for e in events_medium:
            output_lines.append(f"   - [{e['time']}] [{e['country']}] {e['event']}")
            
    if events_low:
        events_low.sort(key=lambda x: x['time'])
        output_lines.append("\n 🟢 BAIXO IMPACTO:")
        for e in events_low:
            output_lines.append(f"   - [{e['time']}] [{e['country']}] {e['event']}")
            
    if not (events_high or events_medium or events_low):
        # Trava de Segurança: se o relatório de hoje já existia com dados válidos, não sobrescrever com erro!
        if os.path.exists(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    existing_text = f.read()
                if today_str in existing_text and ("ALTO IMPACTO" in existing_text or "MÉDIO IMPACTO" in existing_text):
                    print("Aviso: Falha temporária na busca. Preservando relatório válido anterior para hoje.")
                    return
            except Exception:
                pass
        output_lines.append("\n [-] Nenhum evento econômico (USD/BRL) agendado para hoje.")
        
    output_lines.append("\n============================================================")
    
    report_text = "\n".join(output_lines)
    print(report_text)
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
    except Exception as e:
        print(f"[Aviso] Erro ao salvar arquivo de relatório: {e}")

if __name__ == "__main__":
    fetch_economic_calendar()
