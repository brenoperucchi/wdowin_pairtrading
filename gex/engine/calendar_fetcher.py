import os
import sys
import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def fetch_economic_calendar():
    """
    Busca o calendario economico do dia (Brasil BRL e EUA USD) via widget oficial Investing.com (forexprostools),
    configurado com horario de Brasilia (GMT-3), classificando por impacto (Alto, Medio, Baixo),
    com projecoes e valores anteriores.
    Salva em gex/docs/DAILY_ECONOMIC_CALENDAR.txt e escreve no stdout.
    """
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    gex_dir = os.path.dirname(engine_dir)
    docs_dir = os.path.join(gex_dir, 'docs')
    os.makedirs(docs_dir, exist_ok=True)
    report_path = os.path.join(docs_dir, 'DAILY_ECONOMIC_CALENDAR.txt')
    
    today = datetime.date.today()
    today_str = today.strftime("%d/%m/%Y")
    
    url = "https://ec.forexprostools.com/?columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous&calType=day&timeZone=12&lang=12"
    
    events_high = []
    events_medium = []
    events_low = []
    
    try:
        r = requests.get(url, impersonate='chrome124', timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.select_one('table.ecoCalTable')
            if table:
                for tr in table.find_all('tr'):
                    if not tr.get('id', '').startswith('eventRowId_'):
                        continue
                    
                    time_td = tr.find('td', class_='time')
                    flag_td = tr.find('td', class_='flagCur')
                    sentiment_td = tr.find('td', class_='sentiment')
                    event_td = tr.find('td', class_='event')
                    act_td = tr.find('td', class_='act')
                    fore_td = tr.find('td', class_='fore')
                    prev_td = tr.find('td', class_='prev')
                    
                    time_val = time_td.text.strip() if time_td else ""
                    country_val = flag_td.text.strip() if flag_td else ""
                    event_val = event_td.text.strip() if event_td else ""
                    act_val = act_td.text.strip() if act_td else ""
                    fore_val = fore_td.text.strip() if fore_td else ""
                    prev_val = prev_td.text.strip() if prev_td else ""
                    
                    if not event_val or country_val not in ['USD', 'BRL']:
                        continue
                        
                    bulls = 1
                    if sentiment_td:
                        img_key = str(sentiment_td.get('data-img_key') or '')
                        if 'bull3' in img_key:
                            bulls = 3
                        elif 'bull2' in img_key:
                            bulls = 2
                        elif 'bull1' in img_key:
                            bulls = 1
                        else:
                            full_bulls = len(sentiment_td.find_all('i', class_='grayFullBullishIcon'))
                            if full_bulls > 0:
                                bulls = full_bulls
                                
                    event_item = {
                        'time': time_val,
                        'country': country_val,
                        'event': event_val,
                        'actual': act_val,
                        'forecast': fore_val,
                        'previous': prev_val
                    }
                    
                    if bulls >= 3:
                        events_high.append(event_item)
                    elif bulls == 2:
                        events_medium.append(event_item)
                    else:
                        events_low.append(event_item)
    except Exception as e:
        print(f"[Aviso] Erro ao buscar calendario economico: {e}")

    output_lines = []
    output_lines.append("============================================================")
    output_lines.append(f"  CALENDARIO ECONOMICO (BRASIL & EUA) - {today_str}")
    output_lines.append("  Fuso Horario: Brasilia (GMT-3) | Fonte: Investing.com")
    output_lines.append("============================================================")

    if events_high:
        events_high.sort(key=lambda x: x['time'])
        output_lines.append("\n [!] ALTO IMPACTO (Volatilidade Maxima / Foco Operacional):")
        for e in events_high:
            details = []
            if e['previous']: details.append(f"Prev: {e['previous']}")
            if e['forecast']: details.append(f"Proj: {e['forecast']}")
            det_str = f" [{ ' | '.join(details) }]" if details else ""
            output_lines.append(f"   - [{e['time']}] [{e['country']}] {e['event']}{det_str}")

    if events_medium:
        events_medium.sort(key=lambda x: x['time'])
        output_lines.append("\n [*] MEDIO IMPACTO:")
        for e in events_medium:
            details = []
            if e['previous']: details.append(f"Prev: {e['previous']}")
            if e['forecast']: details.append(f"Proj: {e['forecast']}")
            det_str = f" [{ ' | '.join(details) }]" if details else ""
            output_lines.append(f"   - [{e['time']}] [{e['country']}] {e['event']}{det_str}")

    if events_low:
        events_low.sort(key=lambda x: x['time'])
        output_lines.append("\n [-] BAIXO IMPACTO / CFTC:")
        for e in events_low:
            details = []
            if e['previous']: details.append(f"Prev: {e['previous']}")
            if e['forecast']: details.append(f"Proj: {e['forecast']}")
            det_str = f" [{ ' | '.join(details) }]" if details else ""
            output_lines.append(f"   - [{e['time']}] [{e['country']}] {e['event']}{det_str}")

    if not (events_high or events_medium or events_low):
        output_lines.append("\n [-] Nenhum evento economico (USD/BRL) agendado para hoje.")

    output_lines.append("\n============================================================")

    report_text = "\n".join(output_lines)
    print(report_text)

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
    except Exception as e:
        print(f"[Aviso] Erro ao salvar arquivo de relatorio: {e}")

if __name__ == "__main__":
    fetch_economic_calendar()
