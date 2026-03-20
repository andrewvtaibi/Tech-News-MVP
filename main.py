# main.py — BioNews aggregator
# Version: v2.2.2  (2025-10-03)
# Focus: rock-solid run (no crashes), produce outputs even if feeds fail. No UI refactor.

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import csv, json, os, sys, time, logging, re
from urllib.parse import urlparse
from app.config import load_feeds, load_settings, app_root
from app.fetch import fetch_bytes, parse_and_normalize
from app.state import SeenStore
from app.logging_setup import setup_logging, _StreamToLogger

FEEDS_FILE    = "feeds.json"
SETTINGS_FILE = "settings.json"

def safe_write_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = sorted({k for r in rows for k in r.keys()}) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        if keys:
            w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
            for r in rows: w.writerow({k: r.get(k, "") for k in keys})
        else:
            f.write("")
    return path

def safe_write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path); return path

def safe_write_html(path: Path, html: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f: f.write(html)
    tmp.replace(path); return path

def parse_iso_utc(s: str | None):
    if not s: return None
    try:
        if s.endswith("Z"): return datetime.fromisoformat(s.replace("Z","+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        return None

def _strip_noise(s: str) -> str:
    if not s: return ""
    s = re.sub(r"\s+"," ",s); s = re.sub(r"\s*\bhttps?://\S+\b","",s)
    s = re.sub(r"\b(href|hreflang)=[\"'][^\"']+[\"']","",s,flags=re.I)
    return s.strip()

def _lc(s: str) -> str: return (s or "").lower()
def _has_any(s: str, terms: set[str]) -> bool:
    s = _lc(s); return any(t in s for t in terms)

def _norm_terms(terms) -> list[str]:
    if not terms: return []
    if isinstance(terms,str): terms=[terms]
    return [t.strip().lower() for t in terms if t and t.strip()]

def _item_text_for(it: dict, fields: list[str]) -> str:
    return " ".join(str(it.get(k,"")) for k in fields).lower()

def apply_include_exclude(items: list[dict], settings: dict) -> list[dict]:
    include = _norm_terms(settings.get("include_terms"))
    exclude = _norm_terms(settings.get("exclude_terms"))
    fields  = settings.get("filter_fields") or ["title","summary"]
    mode    = str(settings.get("include_mode","any")).lower()
    if not include and not exclude: return items
    out=[]
    for it in items:
        text = _item_text_for(it, fields); keep=True
        if include:
            keep = all(t in text for t in include) if mode=="all" else any(t in text for t in include)
        if keep and exclude and any(t in text for t in exclude): keep=False
        if keep: out.append(it)
    return out

def annotate_watchlist(items: list[dict], settings: dict) -> None:
    terms=_norm_terms(settings.get("watchlist_terms"))
    for it in items:
        if not terms: it["is_watch"]=False; it["watch_hits"]=[]; continue
        text=_item_text_for(it,["title","summary"])
        hits=[t for t in terms if t in text]
        it["is_watch"]=bool(hits); it["watch_hits"]=hits

_PIPELINE_KEYWORDS={"ind application","phase 1","phase i","phase 2","phase ii","phase 3","phase iii",
"pivotal","enrollment","topline","primary endpoint","secondary endpoint","fda approval","ema approval",
"cleared","510(k)","de novo","breakthrough device","orphan","fast track","priority review",
"complete response letter","crl","nda","bla","maa","trial initiated","dose-escalation","interim analysis",
"clinical hold","study halted","discontinue development"}
_PARTNERSHIP_MNA={"acquire","acquisition","merger","spin-out","spin off","collaboration","co-develop",
"partnership","licensing","license","option deal","strategic alliance"}

def score_items(items: list[dict], settings: dict) -> None:
    w=settings.get("score_weights") or {}; cat_w=w.get("category_weights") or {}
    sec_pen=float(w.get("sec_boilerplate_penalty",0.4)); sec_mat=float(w.get("sec_material_boost",1.5))
    for it in items:
        score=0.0; title=_lc(it.get("title","")); tag=_lc(it.get("feed_tag","")); cat=_lc(it.get("category",""))
        if _has_any(title,_PARTNERSHIP_MNA): score+=3.0
        if _has_any(title,_PIPELINE_KEYWORDS): score+=2.0
        score+=float(cat_w.get(cat,1.0))-1.0
        if tag.startswith("sec-") and not _has_any(title,_PARTNERSHIP_MNA|_PIPELINE_KEYWORDS): score-=sec_pen
        if tag.startswith("sec-") and _has_any(title,{"earnings","guidance","merger","acquisition","credit","debt","delisting","bankruptcy","leadership","ceo","cfo"}): score+=sec_mat
        if it.get("is_watch"): score+=float(w.get("watchlist",0.0))
        it["score"]=score

def qualifies_top(it: dict) -> bool:
    tag=_lc(it.get("feed_tag","")); cat=_lc(it.get("category","")); title=_lc(it.get("title",""))
    if tag in {"sec-latest-8k","arxiv-qbio"}: return False
    if cat=="preprint": return False
    if _has_any(title,_PIPELINE_KEYWORDS)|_has_any(title,_PARTNERSHIP_MNA): return True
    if cat=="regulator" and _has_any(title,{"approval","advisory","guidance","recall","warning","complete response letter","crl"}): return True
    return False

def _company_hints(title: str, summary: str) -> set[str]:
    text=f"{title} {summary}"
    hits=re.findall(r"\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})?)\b", text)
    return set(hits)

def _mk_sentence(it: dict) -> str:
    ttl=_strip_noise(it.get("title",""))
    cos=", ".join(sorted(_company_hints(it.get("title",""), it.get("summary","")))) or ""
    src=(it.get("source") or "").strip(); when=(it.get("published_iso") or "")[:10]
    line=ttl; 
    if cos: line+=f" ({cos})"
    if src: line+=f" — {src}"
    if when: line+=f" [{when}]"
    return line

def build_narrative_summary(items: list[dict], settings: dict) -> str:
    lims=settings.get("summary_section_limits") or {}
    ranked=sorted(items, key=lambda x:(float(x.get("score") or 0.0), x.get("published_iso","")), reverse=True)
    industry=[it for it in ranked if _lc(it.get("category","")) in {"industry","company"}][:int(lims.get("industry",10))]
    science=[it for it in ranked if _lc(it.get("category","")) in {"journal","science"}][:int(lims.get("science",8))]
    if not science:
        tmp=[]
        for it in ranked:
            if _lc(it.get("category",""))=="preprint": continue
            t=_lc(it.get("title","")+" "+it.get("summary",""))
            if any(k in t for k in _PIPELINE_KEYWORDS): tmp.append(it)
        science=tmp[:int(lims.get("science",8))]
    regulatory=[]
    for it in ranked:
        if _lc(it.get("category",""))=="regulator": regulatory.append(it)
        else:
            tag=_lc(it.get("feed_tag","")); t=_lc(it.get("title",""))
            if tag.startswith("sec-") and any(k in t for k in ("earnings","guidance","merger","acquisition","credit","debt","delisting","bankruptcy","leadership","ceo","cfo")):
                regulatory.append(it)
        if len(regulatory)>=int(lims.get("regulatory",3)): break
    parts=[]
    if industry: parts.append("<p><strong>Industry &amp; Business.</strong> "+" ".join(_mk_sentence(it) for it in industry)+"</p>")
    if science: parts.append("<p><strong>Science &amp; Pipeline.</strong> "+" ".join(_mk_sentence(it) for it in science)+"</p>")
    if regulatory: parts.append("<p><strong>Regulatory &amp; Filings.</strong> "+" ".join(_mk_sentence(it) for it in regulatory)+"</p>")
    return "".join(parts)

def _mk_bullet(it: dict) -> str:
    tag=(it.get("feed_tag") or "").strip()
    ttl=_strip_noise(it.get("title",""))
    cos=", ".join(sorted(_company_hints(it.get("title",""), it.get("summary","")))) or ""
    src=(it.get("source") or "").strip(); when=(it.get("published_iso") or "")[:10]
    meta=[]; 
    if tag: meta.append(tag)
    if src: meta.append(src)
    if when: meta.append(when)
    meta_s=" — ".join(meta); org_s=f" ({cos})" if cos else ""
    return f"<li>{ttl}{org_s}<span class='meta'>{meta_s}</span></li>"

def main(argv=None):
    argv = argv or sys.argv[1:]
    root = app_root()
    settings = load_settings(Path(SETTINGS_FILE))
    feeds = load_feeds(Path(FEEDS_FILE))

    logger = setup_logging(settings)
    sys.stdout = _StreamToLogger(logger, logging.INFO)
    sys.stderr = _StreamToLogger(logger, logging.ERROR)

    out_dir = root / (settings.get("out_dir") or "out")
    html_path = out_dir / "news.html"; json_path = out_dir / "news.json"; csv_path  = out_dir / "news.csv"

    logger.info("=== BioNews fetch start ===")
    logger.info(f"Feeds: {len(feeds)} | Window days: {settings.get('window_days',0)} | Max total: {settings.get('max_total_items',0)}")

    store = SeenStore(root / ".state" / "seen.json"); store.load(); store.prune(ttl_days=int(settings.get("seen_ttl_days",30)))

    max_workers = int(settings.get("fetch_workers", 6))
    http_timeout_sec = int(settings.get("http_timeout_sec", 15))
    fetch_task_timeout_sec = int(settings.get("fetch_task_timeout_sec", http_timeout_sec + 5))
    total_fetch_budget_sec = int(settings.get("total_fetch_budget_sec", 180))
    host_overrides = settings.get("host_overrides") or {}
    insecure_hosts = set(settings.get("ssl_insecure_hosts") or [])

    def _host_params(u: str):
        host = urlparse(u).hostname or ""
        o = host_overrides.get(host, {}) if host else {}
        return (
            int(o.get("timeout_sec", http_timeout_sec)),
            int(o.get("max_retries", 3)),
            float(o.get("backoff_base", 1.0)),
            float(o.get("backoff_cap", 8.0)),
        )

    results=[]; futures=[]; start_ts=time.time()

    def _task(fdesc: dict):
        try:
            url=fdesc["url"]; tag=fdesc.get("tag",""); category=fdesc.get("category","general")
            t_sec, retries, b_base, b_cap = _host_params(url)
            data = fetch_bytes(url, timeout_sec=t_sec, max_retries=retries, backoff_base=b_base, backoff_cap=b_cap, insecure_hosts=insecure_hosts)
            # NEVER raise: parse returns empty on failure
            source, items = parse_and_normalize(data)
            out=[]
            for it in items:
                it["feed_tag"]=tag; it["category"]=category
                it["source"]=it.get("source") or (source.get("source") if isinstance(source,dict) else (source or ""))
                out.append(it)
            return tag, out
        except Exception:
            return fdesc.get("tag",""), []

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for f in feeds:
            fut=ex.submit(_task, f); fut._bionews_feed=f; futures.append(fut)

        ok=0; fail=0; last_beat=time.time()
        for fut in futures:
            now=time.time()
            if now-start_ts>total_fetch_budget_sec:
                logger.warning(f"Global fetch budget exceeded ({total_fetch_budget_sec}s). Cancelling remaining tasks.")
                break
            if now-last_beat>=5: logger.info("...heartbeat..."); last_beat=now
            try:
                tag, items = fut.result(timeout=fetch_task_timeout_sec)
                if items: ok+=1; results.extend(items)
                else: fail+=1
            except FuturesTimeoutError:
                fdesc=getattr(fut,"_bionews_feed",{"tag":"unknown","url":""})
                logger.error(f"Fetch timeout ({fetch_task_timeout_sec}s): [{fdesc.get('tag','')}] {fdesc.get('url','')}")
                fut.cancel(); fail+=1
            except Exception as ex_err:
                fdesc=getattr(fut,"_bionews_feed",{"tag":"unknown","url":""})
                logger.error(f"Fetch error [{fdesc.get('tag','')}]: {ex_err!r}"); fail+=1

        for fut in futures:
            if not fut.done(): fut.cancel()

    logger.info(f"Fetch complete: ok={ok} fail={fail} | total_feeds={len(feeds)} | duration={int(time.time()-start_ts)}s")

    window_days=int(settings.get("window_days",0) or 0); allow_missing_ts=bool(settings.get("allow_missing_timestamps",True))
    if window_days>0:
        cutoff=datetime.now(timezone.utc)-timedelta(days=window_days)
        filtered=[]
        for it in results:
            dt=parse_iso_utc(it.get("published_iso"))
            if dt is None and allow_missing_ts: filtered.append(it)
            elif dt is not None and dt>=cutoff: filtered.append(it)
        results=filtered

    results=apply_include_exclude(results, settings)
    annotate_watchlist(results, settings)
    score_items(results, settings)

    if bool(settings.get("only_new",True)):
        kept=[]
        for it in results:
            uid=it.get("uid") or it.get("link") or it.get("title")
            if not uid: continue
            if store.is_seen(uid): continue
            kept.append(it); store.add([uid])
        results=kept; store.save()

    logger.info(f"Post-filter: {len(results)} items (new/scored)")

    max_total=int(settings.get("max_total_items",200))
    per_source_frac=float(settings.get("per_source_max_fraction",0.4))
    per_source_max_count=int(settings.get("per_source_max_count", max(1,int(max_total*per_source_frac))))
    explicit_caps=settings.get("per_source_caps") or {}

    by_tag=defaultdict(list)
    for it in results: by_tag[it.get("feed_tag","")].append(it)
    capped=[]
    for tag,lst in by_tag.items():
        cap=int(explicit_caps.get(tag, per_source_max_count))
        capped.extend(sorted(lst, key=lambda x:x.get("score",0.0), reverse=True)[:cap])
    results=sorted(capped, key=lambda x:x.get("score",0.0), reverse=True)[:max_total]

    top_n=int(settings.get("top_n",10))
    top_candidates=[it for it in results if qualifies_top(it)]
    top=sorted(top_candidates, key=lambda x:x.get("score",0.0), reverse=True)[:min(top_n,len(top_candidates))]

    summary_html=build_narrative_summary(results, settings)

    esc=lambda s:(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#39;")
    version="v2.2.2"
    cats=sorted({(it.get("category") or "general") for it in results})
    tags=sorted({it.get("feed_tag","") for it in results if it.get("feed_tag")})
    tag_options="<option value='all'>All sources</option>" + "".join(f"<option value='{esc(t)}'>{esc(t)}</option>" for t in tags)
    cats_html="".join(f"<span class='pill' onclick='setCat(\"{esc(c)}\")'>{esc(c)}</span>" for c in cats)

    cfg_json=json.dumps({"TOP_N":len(top),"SHOW_SUMMARIES":True,"COMPACT":False,"VERSION":version}, ensure_ascii=False)
    s_json=json.dumps({"generated_iso": datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00","Z"),
                       "total_items": len(results), "top_items": len(top)}, ensure_ascii=False)

    css="""
    :root{--fg:#111;--muted:#666;--bg:#fff;--chip:#eef;--chipb:#dde}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:var(--fg);margin:0;padding:0}
    header{padding:12px 16px;border-bottom:1px solid #ddd}
    h1{font-size:20px;margin:0}
    h2{font-size:16px;margin:14px 0 8px}
    .bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:8px}
    .pill{display:inline-block;padding:4px 8px;background:var(--chip);border:1px solid var(--chipb);border-radius:12px;cursor:pointer}
    .grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;padding:16px}
    .card{border:1px solid #ddd;border-radius:8px;padding:12px;background:#fff}
    ul{margin:8px 0 0 18px}
    li{margin:4px 0}
    .meta{color:var(--muted);margin-left:6px;font-size:12px}
    .top li{margin:6px 0}
    .small{font-size:12px;color:var(--muted)}
    select{padding:6px;border:1px solid #ccc;border-radius:6px}
    """
    js="""
<script>
const CFG = """+cfg_json+""";
const STATS = """+s_json+""";
let CURRENT_TAG='all', CURRENT_CAT='all';
function setTag(tag){ CURRENT_TAG=tag; filterAll(); }
function setCat(cat){ CURRENT_CAT=cat; filterAll(); }
function filterAll(){
  const ul=document.getElementById('all'); if(!ul) return;
  const lis=ul.querySelectorAll('li');
  lis.forEach(li=>{
    const txt=li.textContent.toLowerCase();
    let show=true;
    if(CURRENT_TAG!=='all'){ show=show && txt.includes(CURRENT_TAG.toLowerCase()); }
    if(CURRENT_CAT!=='all'){ show=show && txt.includes(CURRENT_CAT.toLowerCase()); }
    li.style.display= show ? '' : 'none';
  });
}
</script>
"""
    html=f"""<!doctype html><html><head><meta charset='utf-8'><title>BioNews</title>
<style>{css}</style></head><body>
<header>
  <h1>BioNews <span class='small'>{esc(version)}</span></h1>
  <div class='bar'>
    <div>
      <label for='srcsel'>Source:</label>
      <select id='srcsel' onchange='setTag(this.value)'>{tag_options}</select>
    </div>
    <div>
      <span>Categories:</span>
      <div>{cats_html}</div>
    </div>
  </div>
</header>

<div class='grid'>
  <div class='left'>
    <div class='card'>
      <h2>Executive Summary</h2>
      <div id='summary'>{summary_html}</div>
    </div>
    <div class='card'>
      <h2>Top Stories</h2>
      <ul class='top'>{"".join(_mk_bullet(it) for it in top)}</ul>
    </div>
    <div class='card'>
      <h2>All Items</h2>
      <div class='small'>Use the filters above to focus.</div>
      <ul id='all'>{"".join(_mk_bullet(it) for it in results)}</ul>
    </div>
  </div>
  <div class='right'>
    <div class='card'>
      <h2>Stats</h2>
      <div class='small'>Generated: {esc(json.loads(s_json)["generated_iso"])}</div>
      <div class='small'>Items: {len(results)} (Top {len(top)})</div>
    </div>
  </div>
</div>
{js}
</body></html>"""

    # ALWAYS WRITE OUTPUTS (even if empty), to guarantee artifacts for debugging.
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_write_html(html_path, html)
    safe_write_json(json_path, results)
    safe_write_csv(csv_path, results)
    logger.info(f"Wrote: {html_path} | {json_path} | {csv_path}")
    logger.info("=== BioNews fetch done ==="); return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrupted.")
