"""
Alpaca Paper Trader - Morning Session (stdlib only, no pip installs needed)
"""
import json, sys
from datetime import date, datetime, timedelta
from pathlib import Path
import urllib.request

API_KEY    = "PK336G46LMIUWTHFUMWUNGXKH5"
API_SECRET = "4rnyugfbV6cajxcgQnfoASc95S5XENSASzMVAR5dBZ5F"
BASE_URL   = "https://paper-api.alpaca.markets"
DATA_URL   = "https://data.alpaca.markets"
MAX_DAILY_BUYS = 2; MAX_DAILY_SELLS = 2; MAX_ROLLOVER = 6
TAKE_PROFIT_PCT = 0.05; STOP_LOSS_PCT = 0.03; POSITION_SIZE_PCT = 0.05
RSI_OVERBOUGHT = 70; RSI_OVERSOLD = 30; MA_SHORT = 20; MA_LONG = 50; LOOKBACK_DAYS = 75
WATCHLIST = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","JPM","V","UNH","XOM","JNJ","PG","MA","HD","CVX","MRK","ABBV","PEP","KO"]
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "state.json"; LOG_FILE = SCRIPT_DIR / "trading_log.json"; OUT_FILE = SCRIPT_DIR / "morning_output.txt"
HEADERS = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": API_SECRET, "accept": "application/json"}
output_lines = []
def say(msg): print(msg); output_lines.append(msg)
def api_get(path, base=BASE_URL, params=None):
    url = f"{base}{path}" + ("?" + "&".join(f"{k}={v}" for k,v in params.items()) if params else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=15) as r: return json.loads(r.read())
def api_post(path, body):
    req = urllib.request.Request(f"{BASE_URL}{path}", data=json.dumps(body).encode(), headers={**HEADERS,"content-type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read())
def log_entry(entry):
    entry["timestamp"] = datetime.utcnow().isoformat(); h = []
    if LOG_FILE.exists():
        try: h = json.loads(LOG_FILE.read_text())
        except: pass
    h.append(entry); LOG_FILE.write_text(json.dumps(h, indent=2))
def load_state():
    today = str(date.today())
    if STATE_FILE.exists():
        s = json.loads(STATE_FILE.read_text()); last = s.get("last_run_date")
        if last != today:
            d = max(1,(date.today()-date.fromisoformat(last)).days) if last else 1
            s["buys_remaining"] = min(s["buys_remaining"]+MAX_DAILY_BUYS*d,MAX_ROLLOVER)
            s["sells_remaining"] = min(s["sells_remaining"]+MAX_DAILY_SELLS*d,MAX_ROLLOVER)
            s["last_run_date"] = today; STATE_FILE.write_text(json.dumps(s,indent=2))
    else:
        s = {"last_run_date":today,"buys_remaining":MAX_DAILY_BUYS,"sells_remaining":MAX_DAILY_SELLS}
        STATE_FILE.write_text(json.dumps(s,indent=2))
    return s
def mean(l): return sum(l)/len(l)
def rsi(closes, p=14):
    if len(closes)<p+1: return 50.0
    g=[]; lo=[]
    for i in range(1,len(closes)): d=closes[i]-closes[i-1]; g.append(max(d,0)); lo.append(max(-d,0))
    ag=mean(g[:p]); al=mean(lo[:p])
    for i in range(p,len(g)): ag=(ag*(p-1)+g[i])/p; al=(al*(p-1)+lo[i])/p
    return 100.0 if al==0 else 100.0-100.0/(1+ag/al)
def score(closes):
    if len(closes)<MA_LONG+5: return None
    mom=min(max(((closes[-1]-closes[-20])/closes[-20]+0.10)/0.20,0),1)
    ma=min(max(((mean(closes[-MA_SHORT:])-mean(closes[-MA_LONG:]))/mean(closes[-MA_LONG:])+0.05)/0.10,0),1)
    r=rsi(closes); rs=0.0 if r>RSI_OVERBOUGHT else 0.3 if r<RSI_OVERSOLD else 1.0-abs(r-55)/45
    return 0.40*mom+0.30*ma+0.30*rs
def main():
    say(f"\n=== Alpaca Paper Trader - Morning Session ==="); say(f"  Time: {datetime.utcnow().isoformat()[:19]} UTC\n")
    try: acc = api_get("/v2/account")
    except Exception as e: say(f"  [ERROR] {e}"); sys.exit(1)
    bp=float(acc["buying_power"]); pv=float(acc["portfolio_value"])
    say(f"  Portfolio value:  ${pv:,.2f}"); say(f"  Buying power:     ${bp:,.2f}")
    s=load_state(); bl=s["buys_remaining"]; sl=s["sells_remaining"]
    say(f"  Buy slots left:   {bl}"); say(f"  Sell slots left:  {sl}\n")
    clk=api_get("/v2/clock")
    if not clk["is_open"]:
        say(f"  Market is CLOSED. Next open: {clk.get('next_open','?')}")
        log_entry({"action":"SKIP","message":f"Market closed"}); STATE_FILE.write_text(json.dumps(s,indent=2)); return
    pos={p["symbol"]:p for p in api_get("/v2/positions")}; say(f"  Open positions: {list(pos.keys()) or 'none'}")
    end=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"); start=(datetime.utcnow()-timedelta(days=LOOKBACK_DAYS+15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    scores={}
    for sym in WATCHLIST:
        try:
            bars=api_get(f"/v2/stocks/{sym}/bars",base=DATA_URL,params={"timeframe":"1Day","start":start,"end":end,"limit":"100","adjustment":"all","feed":"iex"}).get("bars",[])
            if bars and len(bars)>=MA_LONG:
                cl=[b["c"] for b in bars]; sc=score(cl)
                if sc is not None: scores[sym]=(sc,cl[-1])
        except Exception as e: say(f"  [warn] {sym}: {e}")
    ranked=sorted(scores.items(),key=lambda x:x[1][0],reverse=True)
    say("\n  Top picks:")
    for sym,(sc,pr) in ranked[:5]: say(f"    {sym:6s}  score={sc:.3f}  price=${pr:.2f}{'  <- held' if sym in pos else ''}")
    be=0; say("")
    for sym,(sc,lp) in ranked:
        if bl<=0 or be>=MAX_DAILY_BUYS: break
        if sym in pos or sc<0.55: continue
        qty=max(1,int(bp*POSITION_SIZE_PCT/lp)); tp=round(lp*(1+TAKE_PROFIT_PCT),2); sl2=round(lp*(1-STOP_LOSS_PCT),2)
        msg=f"BUY {qty}x{sym} @ ~${lp:.2f} | TP=${tp:.2f} SL=${sl2:.2f} | score={sc:.3f}"; say(f"  -> {msg}")
        try:
            api_post("/v2/orders",{"symbol":sym,"qty":str(qty),"side":"buy","type":"market","time_in_force":"day","order_class":"bracket","take_profit":{"limit_price":str(tp)},"stop_loss":{"stop_price":str(sl2)}})
            log_entry({"action":"BUY","symbol":sym,"qty":qty,"approx_price":lp,"take_profit":tp,"stop_loss":sl2,"score":sc,"message":msg}); bl-=1; be+=1
        except Exception as e: log_entry({"action":"ERROR","symbol":sym,"message":str(e)}); say(f"    [error] {e}")
    if be==0: say("  No buy signals met threshold today.")
    se=0
    if pos and sl>0:
        for sym,sc2 in sorted({sym:(scores[sym][0] if sym in scores else 0.0) for sym in pos}.items(),key=lambda x:x[1]):
            if sl<=0 or se>=MAX_DAILY_SELLS or sc2>0.45: break
            p2=pos[sym]; qty=int(float(p2["qty"])); pl=float(p2["unrealized_plpc"])*100
            msg=f"SELL {qty}x{sym} | score={sc2:.3f} | P&L={pl:+.1f}%"; say(f"  -> {msg}")
            try:
                api_post("/v2/orders",{"symbol":sym,"qty":str(qty),"side":"sell","type":"market","time_in_force":"day"})
                log_entry({"action":"SELL","symbol":sym,"qty":qty,"score":sc2,"unrealized_plpc":pl,"message":msg}); sl-=1; se+=1
            except Exception as e: log_entry({"action":"ERROR","symbol":sym,"message":str(e)}); say(f"    [error] {e}")
    s["buys_remaining"]=bl; s["sells_remaining"]=sl; STATE_FILE.write_text(json.dumps(s,indent=2))
    say(f"\n  Done. Slots remaining - buys: {bl}, sells: {sl}")
    log_entry({"action":"SESSION_COMPLETE","buys_executed":be,"sells_executed":se,"buys_remaining":bl,"sells_remaining":sl,"portfolio_value":pv,"message":"Session complete"})
if __name__=="__main__":
    main(); OUT_FILE.write_text("\n".join(output_lines)); print(f"\n  Output saved to: {OUT_FILE}")
