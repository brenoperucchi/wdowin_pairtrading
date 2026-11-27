// rtdmw (baseado no rtdmin): cliente RTD UNICO do Profit (RTDTrading.RtdServer) sem Excel.
// O servidor RTD do Profit aceita uma sessao so: um segundo cliente derruba o primeiro. Por isso este programa
// faz tudo: CSV por minuto (igual ao rtdmin) + Times & Trades com corretora por negocio.
// Uso: rtdmw pasta ATIVO=rotulo ... [--tt=T&T0:ROTULO:LINHAS ...] [--dump=arquivo:N]
//   ex.: rtdmw Z:\\home\\mt5\\.mt5\\rtd-csv WINZ26=WINZ26 WDOZ26=WDOZ26 --tt=T&T0:WINZ26:300 --tt=T&T1:WDOZ26:300
#include <windows.h>
#include <oleauto.h>
#include <cstdio>
#include <string>
#include <vector>
#include <map>
#include <array>
#include <cstring>
#include <csignal>
#include <cstdarg>
#include <cstdlib>

static const GUID IID_IRTDUpdateEvent_ = {0xA43788C1,0xD91B,0x11D3,{0x8F,0x39,0x00,0xC0,0x4F,0x36,0x51,0xB8}};
static volatile LONG g_notify = 0;

struct UpdateEvent {
  const void* vtbl; LONG ref; long hb;
};
static HRESULT STDMETHODCALLTYPE UE_QI(UpdateEvent* t, REFIID riid, void** out){
  if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IDispatch) || IsEqualIID(riid, IID_IRTDUpdateEvent_)) { *out=t; InterlockedIncrement(&t->ref); return S_OK; }
  *out=nullptr; return E_NOINTERFACE;
}
static ULONG STDMETHODCALLTYPE UE_AddRef(UpdateEvent* t){ return InterlockedIncrement(&t->ref); }
static ULONG STDMETHODCALLTYPE UE_Release(UpdateEvent* t){ return InterlockedDecrement(&t->ref); }
static HRESULT STDMETHODCALLTYPE UE_GetTypeInfoCount(UpdateEvent*, UINT* n){ *n=0; return S_OK; }
static HRESULT STDMETHODCALLTYPE UE_GetTypeInfo(UpdateEvent*, UINT, LCID, ITypeInfo**){ return E_NOTIMPL; }
static HRESULT STDMETHODCALLTYPE UE_GetIDsOfNames(UpdateEvent*, REFIID, LPOLESTR* names, UINT n, LCID, DISPID* ids){
  for(UINT i=0;i<n;i++){
    if(!lstrcmpiW(names[i],L"UpdateNotify")) ids[i]=10;
    else if(!lstrcmpiW(names[i],L"HeartbeatInterval")) ids[i]=11;
    else if(!lstrcmpiW(names[i],L"Disconnect")) ids[i]=12;
    else ids[i]=DISPID_UNKNOWN;
  } return S_OK;
}
static HRESULT STDMETHODCALLTYPE UE_Invoke(UpdateEvent* t, DISPID id, REFIID, LCID, WORD flags, DISPPARAMS* p, VARIANT* res, EXCEPINFO*, UINT*){
  if(id==10){ InterlockedExchange(&g_notify,1); return S_OK; }
  if(id==11){
    if(flags & DISPATCH_PROPERTYGET){ if(res){ VariantInit(res); res->vt=VT_I4; res->lVal=t->hb; } }
    else if(p && p->cArgs>0){ VARIANT v; VariantInit(&v); if(SUCCEEDED(VariantChangeType(&v,&p->rgvarg[0],0,VT_I4))) t->hb=v.lVal; }
    return S_OK;
  }
  if(id==12) return S_OK;
  return DISP_E_MEMBERNOTFOUND;
}
static HRESULT STDMETHODCALLTYPE UE_UpdateNotify(UpdateEvent*){ InterlockedExchange(&g_notify,1); return S_OK; }
static HRESULT STDMETHODCALLTYPE UE_GetHB(UpdateEvent* t, long* v){ *v=t->hb; return S_OK; }
static HRESULT STDMETHODCALLTYPE UE_PutHB(UpdateEvent* t, long v){ t->hb=v; return S_OK; }
static HRESULT STDMETHODCALLTYPE UE_Disconnect(UpdateEvent*){ return S_OK; }

static void* g_vtbl[] = {
  (void*)UE_QI,(void*)UE_AddRef,(void*)UE_Release,(void*)UE_GetTypeInfoCount,(void*)UE_GetTypeInfo,
  (void*)UE_GetIDsOfNames,(void*)UE_Invoke,(void*)UE_UpdateNotify,(void*)UE_GetHB,(void*)UE_PutHB,(void*)UE_Disconnect };

static HRESULT call(IDispatch* d, const wchar_t* name, WORD flags, VARIANT* args, int nargs, VARIANT* res){
  DISPID id; LPOLESTR n=(LPOLESTR)name;
  HRESULT hr = d->GetIDsOfNames(IID_NULL,&n,1,LOCALE_USER_DEFAULT,&id);
  if(FAILED(hr)) return hr;
  DISPPARAMS dp={args,nullptr,(UINT)nargs,0};
  return d->Invoke(id,IID_NULL,LOCALE_USER_DEFAULT,flags,&dp,res,nullptr,nullptr);
}

static std::string utf8(const wchar_t* w){
  int n=WideCharToMultiByte(CP_UTF8,0,w,-1,nullptr,0,nullptr,nullptr); std::string s(n?n-1:0,'\0');
  if(n>1) WideCharToMultiByte(CP_UTF8,0,w,-1,&s[0],n,nullptr,nullptr); return s;
}
static std::wstring wide(const char* a){
  int n=MultiByteToWideChar(CP_UTF8,0,a,-1,nullptr,0); std::wstring s(n?n-1:0,L'\0');
  if(n>1) MultiByteToWideChar(CP_UTF8,0,a,-1,&s[0],n); return s;
}
static std::string jesc(const std::string& s){
  std::string o; for(unsigned char c: s){ if(c=='"'||c=='\\'){o+='\\';o+=c;} else if(c<0x20){char b[8];sprintf(b,"\\u%04x",c);o+=b;} else o+=c; } return o;
}
static std::string vstr(VARIANT& v){
  VARIANT t; VariantInit(&t);
  if(SUCCEEDED(VariantChangeType(&t,&v,0,VT_BSTR))){ std::string s=utf8(t.bstrVal); VariantClear(&t); return s; }
  return "";
}
static bool isnum(VARIANT& v){ return v.vt==VT_I2||v.vt==VT_I4||v.vt==VT_R4||v.vt==VT_R8||v.vt==VT_CY||v.vt==VT_I8||v.vt==VT_UI4||v.vt==VT_UI2||v.vt==VT_DECIMAL; }


struct Snap { bool ok=false; std::string date, hor, qtt, vol, neg, avc, avv, anc, anv; };
struct Asset {
  std::string rtd, label;
  std::map<std::string,std::string> val;   // campo -> ultimo valor valido (texto)
  Snap prev;                               // ultima leitura valida do minuto corrente
  std::string lastWritten;                 // HH:MM do ultimo minuto gravado (arquivo do dia)
  std::string lastDateFile;
  unsigned long long lines=0, resets=0, gaps=0, reads=0;
  DWORD lastRead=0;
};
static const char* FIELDS[] = {"DAT","HOR","QTT","VOL","NEG","AGRVOLC","AGRVOLV","AGRNEGC","AGRNEGV"};
static const int NF = 9;
static std::string g_dir;

static bool numtxt(const std::string& s){ if(s.empty()) return false; for(char c: s) if(!((c>='0'&&c<='9')||c=='-'||c=='.')) return false; return true; }
static bool horok(const std::string& s){ return s.size()==8 && s[2]==':' && s[5]==':'; }
static bool datok(const std::string& s){ return s.size()==10 && s[2]=='/' && s[5]=='/'; }
static std::string fname(const Asset& a, const std::string& date){
  std::string d=date; for(auto& c: d) if(c=='/') c='_';
  return g_dir+"\\"+a.label+"_min_"+d+".csv";
}
static void loadLast(Asset& a, const std::string& date){
  a.lastWritten=""; a.lastDateFile=date;
  FILE* f=fopen(fname(a,date).c_str(),"rb"); if(!f) return;
  char buf[512]; std::string last;
  while(fgets(buf,sizeof buf,f)){ if(strncmp(buf,"RESET",5)!=0 && strlen(buf)>=5) last.assign(buf,5); }
  fclose(f); a.lastWritten=last;
}
static void writeLine(Asset& a, const Snap& s, const char* tag){
  if(a.lastDateFile!=s.date) loadLast(a,s.date);
  std::string minute=s.hor.substr(0,5);
  bool reset = tag!=nullptr;
  if(!reset){ if(!a.lastWritten.empty() && minute<=a.lastWritten) return; }
  FILE* f=fopen(fname(a,s.date).c_str(),"ab"); if(!f) return;
  std::string first = reset? std::string(tag) : minute;
  std::string line=first+";"+s.hor+";"+s.qtt+";"+s.vol+";"+s.neg+";"+s.avc+";"+s.avv+";"+s.anc+";"+s.anv+"\n";
  fputs(line.c_str(),f); fclose(f);
  if(reset) a.resets++;
  else {
    int pm = (a.lastWritten.size()==5)? ( (a.lastWritten[0]-'0')*600+(a.lastWritten[1]-'0')*60+(a.lastWritten[3]-'0')*10+(a.lastWritten[4]-'0') ) : -1;
    int cm = (minute[0]-'0')*600+(minute[1]-'0')*60+(minute[3]-'0')*10+(minute[4]-'0');
    if(pm>=0 && cm-pm>1) a.gaps += (cm-pm-1);
    a.lastWritten=minute; a.lines++;
  }
}
static bool snapOf(Asset& a, Snap& s){
  auto g=[&](const char* k)->std::string{ auto it=a.val.find(k); return it==a.val.end()?"":it->second; };
  s.date=g("DAT"); s.hor=g("HOR"); s.qtt=g("QTT"); s.vol=g("VOL"); s.neg=g("NEG"); s.avc=g("AGRVOLC"); s.avv=g("AGRVOLV"); s.anc=g("AGRNEGC"); s.anv=g("AGRNEGV");
  s.ok = datok(s.date)&&horok(s.hor)&&numtxt(s.qtt)&&numtxt(s.vol)&&numtxt(s.neg)&&numtxt(s.avc)&&numtxt(s.avv)&&numtxt(s.anc)&&numtxt(s.anv);
  return s.ok;
}
static void onRead(Asset& a){
  Snap cur; if(!snapOf(a,cur)) return;
  a.reads++; a.lastRead=GetTickCount();
  if(a.prev.ok){
    bool sameDay = (a.prev.date==cur.date);
    bool retro = sameDay && (atoll(cur.qtt.c_str()) < atoll(a.prev.qtt.c_str()));
    bool newMin = !sameDay || cur.hor.substr(0,5)!=a.prev.hor.substr(0,5);
    if(newMin || retro) writeLine(a,a.prev,nullptr);   // minuto anterior fechado
    if(retro) writeLine(a,cur,"RESET");                 // acumulado retrocedeu
  }
  a.prev=cur;
}


// ---------- Times & Trades ----------
typedef std::array<std::string,6> Row;   // DAT QUL PRE ACP AVD AGR
static const char* TTF[6]={"DAT","QUL","PRE","ACP","AVD","AGR"};
struct TT {
  std::string rtd, label; int ai=-1; int nrows=0;
  std::vector<Row> cur;       // tabela atual (linha 0 = negocio mais novo)
  std::vector<Row> prev; bool havePrev=false; bool dirty=false;
  unsigned long long trades=0, gaps=0, events=0, lost_est=0;
  long long neg0=-1; std::string lastDate;
};
struct Tgt { int kind; int a; int b; int c; };   // kind 0: ativo/campo (a=ai,b=fi); kind 1: tt (a=ti,b=row,c=campo)
static std::vector<TT> g_tt;
static std::string g_dumpPath; static int g_dumpLeft=0;
static volatile LONG g_stop=0;

static bool rowEmpty(const Row& r){ return r[0].empty(); }
static void ttDump(const char* fmt, ...){
  if(g_dumpLeft<=0) return; FILE* f=fopen(g_dumpPath.c_str(),"ab"); if(!f) return;
  va_list ap; va_start(ap,fmt); vfprintf(f,fmt,ap); va_end(ap); fclose(f);
}
static void ttProcess(TT& t, std::vector<Asset>& assets){
  t.events++;
  size_t nt=0; while(nt<t.cur.size() && !rowEmpty(t.cur[nt])) nt++;
  std::vector<Row> T(t.cur.begin(), t.cur.begin()+nt);
  size_t np=t.prev.size();
  Asset& a=assets[t.ai];
  long long negNow=a.val.count("NEG")?atoll(a.val["NEG"].c_str()):-1;
  if(!t.havePrev){ t.prev=T; t.havePrev=true; if(negNow>=0) t.neg0=negNow; return; }
  if(T==t.prev) return;
  // procura o deslocamento k: T[k..] == prev[..] (sobreposicao exata da regiao comum)
  long k=-1; size_t minL = np<8?np:8;
  for(size_t kk=0; kk<=nt; kk++){
    size_t L = (nt-kk<np)? nt-kk : np;
    if(L<minL) break;
    bool ok=true; for(size_t j=0;j<L;j++) if(!(T[kk+j]==t.prev[j])){ ok=false; break; }
    if(ok){ k=(long)kk; break; }
  }
  size_t first = (k>=0)? (size_t)k : nt;   // linhas novas = T[0..first)
  std::string date=a.prev.date.empty()?"": a.prev.date; if(date.empty()) date=t.lastDate; else t.lastDate=date;
  if(date.empty()){ SYSTEMTIME st; GetLocalTime(&st); char b[16]; sprintf(b,"%02d/%02d/%04d",st.wDay,st.wMonth,st.wYear); date=b; }
  std::string d=date; for(auto& c: d) if(c=='/') c='_';
  std::string path=g_dir+"\\tt_"+t.label+"_"+d+".csv";
  FILE* f=fopen(path.c_str(),"ab");
  if(k<0){ t.gaps++; t.lost_est++; if(f) fputs("GAP;;;;;\n",f); }
  if(f){
    for(size_t i=first;i>0;i--){ const Row& r=T[i-1];
      std::string line=r[0]+";"+r[1]+";"+r[2]+";"+r[3]+";"+r[4]+";"+r[5]+"\n"; fputs(line.c_str(),f); }
    fclose(f);
  }
  t.trades+=first;
  if(g_dumpLeft>0){
    ttDump("%s np=%zu nt=%zu k=%ld novas=%zu neg=%lld top:", t.label.c_str(), np, nt, k, first, negNow);
    for(size_t i=0;i<nt && i<4;i++) ttDump(" [%s,%s,%s,%s,%s,%s]",T[i][0].c_str(),T[i][1].c_str(),T[i][2].c_str(),T[i][3].c_str(),T[i][4].c_str(),T[i][5].c_str());
    ttDump("\n"); g_dumpLeft--;
  }
  t.prev=T;
}
static BOOL WINAPI ctrlHandler(DWORD){ InterlockedExchange(&g_stop,1); return TRUE; }

int wmain(int argc, wchar_t** argv){
  if(argc<3){ fprintf(stderr,"uso: rtdmin pasta ativo_rtd=rotulo ...\n"); return 2; }
  g_dir=utf8(argv[1]); CreateDirectoryA(g_dir.c_str(),nullptr);
  std::vector<Asset> assets;
  std::vector<std::string> ttspecs;
  for(int i=2;i<argc;i++){ std::string s=utf8(argv[i]);
    if(s.rfind("--tt=",0)==0){ ttspecs.push_back(s.substr(5)); continue; }
    if(s.rfind("--dump=",0)==0){ std::string v=s.substr(7); size_t c=v.rfind(':'); g_dumpPath=v.substr(0,c); g_dumpLeft=atoi(v.substr(c+1).c_str()); continue; }
    size_t p=s.find('='); Asset a; a.rtd= p==std::string::npos?s:s.substr(0,p); a.label= p==std::string::npos?s:s.substr(p+1); assets.push_back(a); }
  CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
  { ITypeLib* tl=nullptr; const wchar_t* exe=L"C:\\users\\mt5\\AppData\\Roaming\\Nelogica\\Scalper\\profitchart.exe";
    LoadTypeLibEx(exe,REGKIND_REGISTER,&tl); if(tl) tl->Release();
    static const GUID PSOA={0x00020424,0,0,{0xC0,0,0,0,0,0,0,0x46}}; CoRegisterPSClsid(IID_IRTDUpdateEvent_,PSOA); }
  CLSID clsid; HRESULT hr=CLSIDFromString(L"{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}",&clsid);
  IDispatch* srv=nullptr; hr=CoCreateInstance(clsid,nullptr,CLSCTX_LOCAL_SERVER,IID_IDispatch,(void**)&srv);
  if(FAILED(hr)){ fprintf(stderr,"CoCreateInstance falhou %08lx\n",hr); return 1; }
  UpdateEvent ue{g_vtbl,1,100};
  VARIANT a1[1]; VariantInit(&a1[0]); a1[0].vt=VT_DISPATCH; a1[0].pdispVal=(IDispatch*)&ue;
  VARIANT r; VariantInit(&r); hr=call(srv,L"ServerStart",DISPATCH_METHOD,a1,1,&r);
  if(FAILED(hr)){ fprintf(stderr,"ServerStart falhou %08lx\n",hr); return 1; }
  for(auto& sp: ttspecs){ // T&T0:WINZ26:300
    size_t p1=sp.find(':'), p2=sp.rfind(':'); if(p1==std::string::npos||p2==p1){ fprintf(stderr,"--tt invalido: %s\n",sp.c_str()); continue; }
    TT t; t.rtd=sp.substr(0,p1); t.label=sp.substr(p1+1,p2-p1-1); t.nrows=atoi(sp.substr(p2+1).c_str());
    for(size_t i=0;i<assets.size();i++) if(assets[i].label==t.label) t.ai=(int)i;
    if(t.ai<0||t.nrows<=0){ fprintf(stderr,"--tt invalido (ativo?): %s\n",sp.c_str()); continue; }
    t.cur.assign(t.nrows,Row()); g_tt.push_back(t);
  }
  std::map<long,Tgt> tmap; long id=1;
  auto connectTopic=[&](const std::vector<std::string>& parts, long tid, VARIANT& rv)->HRESULT{
    SAFEARRAYBOUND bb={(ULONG)parts.size(),0}; SAFEARRAY* sa=SafeArrayCreate(VT_VARIANT,1,&bb);
    for(long k=0;k<(long)parts.size();k++){ VARIANT e; VariantInit(&e); e.vt=VT_BSTR; std::wstring w=wide(parts[k].c_str()); e.bstrVal=SysAllocString(w.c_str()); SafeArrayPutElement(sa,&k,&e); VariantClear(&e); }
    VARIANT args[3]; for(int k=0;k<3;k++) VariantInit(&args[k]);
    VARIANT_BOOL gnv=VARIANT_TRUE; args[0].vt=VT_BOOL|VT_BYREF; args[0].pboolVal=&gnv;
    args[1].vt=VT_ARRAY|VT_VARIANT|VT_BYREF; args[1].pparray=&sa; args[2].vt=VT_I4; args[2].lVal=tid;
    VariantInit(&rv); HRESULT h=call(srv,L"ConnectData",DISPATCH_METHOD,args,3,&rv);
    SafeArrayDestroy(sa); return h;
  };
  for(size_t ai=0;ai<assets.size();ai++) for(int fi=0;fi<NF;fi++){
    VARIANT rv; std::string fld=FIELDS[fi];
    hr=connectTopic({assets[ai].rtd,fld},id,rv);
    if(SUCCEEDED(hr)){ std::string v=vstr(rv); if(isnum(rv)||datok(v)||horok(v)) assets[ai].val[fld]=v; }
    tmap[id]={0,(int)ai,fi,0}; id++; VariantClear(&rv);
  }
  for(size_t ti=0;ti<g_tt.size();ti++) for(int r=0;r<g_tt[ti].nrows;r++) for(int f=0;f<6;f++){
    VARIANT rv; hr=connectTopic({g_tt[ti].rtd,TTF[f],std::to_string(r)},id,rv);
    if(SUCCEEDED(hr)) g_tt[ti].cur[r][f]=vstr(rv);
    tmap[id]={1,(int)ti,r,f}; id++; VariantClear(&rv);
  }
  SetConsoleCtrlHandler(ctrlHandler,TRUE);
  for(auto& a: assets) onRead(a);
  fprintf(stderr,"rtdmin ativo: %zu ativos, pasta %s\n",assets.size(),g_dir.c_str());
  DWORD lastRefresh=0,lastHb=GetTickCount(),lastStat=0,lastData=GetTickCount(); int fails=0; unsigned long long batches=0;
  for(;;){
    MSG m; while(PeekMessage(&m,nullptr,0,0,PM_REMOVE)){ TranslateMessage(&m); DispatchMessage(&m); }
    DWORD now=GetTickCount();
    if(InterlockedExchange(&g_notify,0) || now-lastRefresh>1000){
      lastRefresh=now; long count=0; VARIANT arg; VariantInit(&arg); arg.vt=VT_I4|VT_BYREF; arg.plVal=&count;
      VARIANT rv; VariantInit(&rv); hr=call(srv,L"RefreshData",DISPATCH_METHOD,&arg,1,&rv);
      if(FAILED(hr)){ if(++fails>10){ fprintf(stderr,"RefreshData falhando, saindo\n"); return 3; } }
      else {
        fails=0; batches++;
        if((rv.vt&VT_ARRAY)&&rv.parray){
          long lb1,lb2,ub2; SafeArrayGetLBound(rv.parray,1,&lb1); SafeArrayGetLBound(rv.parray,2,&lb2); SafeArrayGetUBound(rv.parray,2,&ub2);
          std::vector<bool> touched(assets.size(),false);
          for(long c=lb2;c<=ub2;c++){
            VARIANT vid,vv; VariantInit(&vid); VariantInit(&vv); long i0[2]={lb1,c},i1[2]={lb1+1,c};
            SafeArrayGetElement(rv.parray,i0,&vid); SafeArrayGetElement(rv.parray,i1,&vv);
            VARIANT t; VariantInit(&t); long tid=0; if(SUCCEEDED(VariantChangeType(&t,&vid,0,VT_I4))) tid=t.lVal;
            auto it=tmap.find(tid);
            if(it!=tmap.end()){ std::string v=vstr(vv); const Tgt& g=it->second;
              if(g.kind==0){ bool good = isnum(vv)||datok(v)||horok(v);
                if(good){ assets[g.a].val[FIELDS[g.b]]=v; touched[g.a]=true; } }
              else { g_tt[g.a].cur[g.b][g.c]=v; g_tt[g.a].dirty=true; } }
            VariantClear(&vid); VariantClear(&vv);
          }
          for(size_t i=0;i<assets.size();i++) if(touched[i]){ onRead(assets[i]); lastData=now; }
          for(auto& t: g_tt) if(t.dirty){ t.dirty=false; ttProcess(t,assets); }
          SafeArrayDestroy(rv.parray);
        }
      }
    }
    if(InterlockedCompareExchange(&g_stop,0,0)){ fprintf(stderr,"sinal de parada, encerrando\n"); call(srv,L"ServerTerminate",DISPATCH_METHOD,nullptr,0,nullptr); return 0; }
    // watchdog: sessao do servidor RTD derrubada por outro cliente (hor parado) em horario de pregao
    { bool inSession=false; for(auto& a: assets) if(a.prev.ok && a.prev.hor>="09:05:00" && a.prev.hor<="18:25:00") inSession=true;
      if(inSession && now-lastData>60000){ fprintf(stderr,"watchdog: sem dados ha 60 s em pregao, encerrando para reconectar\n"); call(srv,L"ServerTerminate",DISPATCH_METHOD,nullptr,0,nullptr); return 4; } }
    // mercado parado: grava o ultimo minuto lido apos 70 s sem leitura nova
    for(auto& a: assets){ if(a.prev.ok && a.lastRead && now-a.lastRead>70000){ writeLine(a,a.prev,nullptr); a.lastRead=0; } }
    if(now-lastStat>10000){
      lastStat=now; std::string js="{\"batches\":"+std::to_string(batches)+",\"assets\":{";
      for(size_t i=0;i<assets.size();i++){ auto& a=assets[i]; if(i) js+=",";
        js+="\""+a.label+"\":{\"rtd\":\""+a.rtd+"\",\"hor\":\""+a.prev.hor+"\",\"date\":\""+a.prev.date+"\",\"reads\":"+std::to_string(a.reads)+",\"lines\":"+std::to_string(a.lines)+",\"gaps\":"+std::to_string(a.gaps)+",\"resets\":"+std::to_string(a.resets)+",\"last_written\":\""+a.lastWritten+"\"}"; }
      js+="}";
      if(!g_tt.empty()){ js+=",\"tt\":{";
        for(size_t i=0;i<g_tt.size();i++){ auto& t=g_tt[i]; if(i) js+=",";
          long long negNow=assets[t.ai].val.count("NEG")?atoll(assets[t.ai].val["NEG"].c_str()):-1; long long nd=(t.neg0>=0&&negNow>=0)?negNow-t.neg0:-1;
          char cov[32]; if(nd>0) sprintf(cov,"%.3f",(double)t.trades/(double)nd); else strcpy(cov,"null");
          js+="\""+t.rtd+"\":{\"asset\":\""+t.label+"\",\"rows\":"+std::to_string(t.nrows)+",\"events\":"+std::to_string(t.events)+",\"trades\":"+std::to_string(t.trades)+",\"gaps\":"+std::to_string(t.gaps)+",\"neg_delta\":"+std::to_string(nd)+",\"coverage\":"+cov+"}"; }
        js+="}"; }
      js+="}\n"; std::string p=g_dir+"\\status.json"; std::string tmp=p+".tmp"; FILE* f=fopen(tmp.c_str(),"wb"); if(f){ fputs(js.c_str(),f); fclose(f); MoveFileExA(tmp.c_str(),p.c_str(),MOVEFILE_REPLACE_EXISTING); }
    }
    if(now-lastHb>10000){ lastHb=now; VARIANT hv; VariantInit(&hv); call(srv,L"Heartbeat",DISPATCH_METHOD,nullptr,0,&hv); }
    MsgWaitForMultipleObjects(0,nullptr,FALSE,100,QS_ALLINPUT);
  }
  return 0;
}
