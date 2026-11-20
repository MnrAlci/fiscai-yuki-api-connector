"""HTML-sjablonen: dashboard (widget + export) en handleiding. Editie-afhankelijke huisstijl."""
from __future__ import annotations

import base64
import json
import os
import re
from html import escape
from pathlib import Path

from . import edition
from .attribution import ATTRIBUTION, ensure
from .handleiding import handleiding_html_body

ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"
MCP_APP_MIME = "text/html;profile=mcp-app"

try:                                   # alleen aanwezig in editie A
    from . import intern_branding
except ImportError:                    # editie B
    intern_branding = None

# Neutrale basiskleuren (editie B); het accent ("navy") is instelbaar met YUKI_BRAND_COLOR.
BASE_COLORS = {"navy": "#1F4E79", "gold": "#9AA5B1", "ink": "#1F2933", "body": "#323F4B",
               "line": "#E4E7EB", "bg": "#F5F7FA", "white": "#FFFFFF"}


def _data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def branding() -> dict:
    """Merkinstellingen. A: vaste huisstijl. B: instelbaar via omgevingsvariabelen."""
    if edition.EDITION == "intern" and intern_branding:
        logo = ASSETS / intern_branding.LOGO_FILE
        return {"colors": intern_branding.COLORS, "logo": _data_uri(logo, "image/png") if logo.exists() else "",
                "logo_alt": intern_branding.LOGO_ALT, "name": "", "footer": ""}
    color = os.environ.get("YUKI_BRAND_COLOR", BASE_COLORS["navy"]).strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        color = BASE_COLORS["navy"]
    name = os.environ.get("YUKI_BRAND_NAME", "").strip()[:80] or "FISCAi Yuki API Connector"
    logo = ""
    lp = os.environ.get("YUKI_BRAND_LOGO_PATH", "").strip()
    if lp and Path(lp).is_file() and Path(lp).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
        mime = "image/png" if lp.lower().endswith(".png") else "image/jpeg" if lp.lower().endswith((".jpg", ".jpeg")) else "image/gif"
        logo = _data_uri(Path(lp), mime)
    c = dict(BASE_COLORS, navy=color)
    return {"colors": c, "logo": logo, "logo_alt": name, "name": name, "footer": ATTRIBUTION}


def _style(c: dict) -> str:
    return f"""
:root{{--navy:{c['navy']};--gold:{c['gold']};--ink:{c['ink']};--body:{c['body']};--line:{c['line']};--bg:{c['bg']};}}
*{{box-sizing:border-box}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--body);font:13px/1.55 'Poppins',system-ui,sans-serif}}
header{{display:flex;align-items:center;gap:16px;border-top:2px solid var(--gold);background:#fff;border-radius:16px;padding:12px 16px;border:1px solid var(--line)}}
header img{{height:44px;width:auto}}
header .name{{font:18px Georgia,'Marcellus',serif;color:var(--navy)}}
h1,h2{{font-family:Georgia,'Marcellus',serif;color:var(--ink);font-weight:400}}
h1{{font-size:20px}} h2{{font-size:16px;margin:20px 0 8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:12px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 14px;box-shadow:0 1px 2px rgba(16,24,40,.06)}}
.card .l{{color:#4a5262;font-size:12px}} .card .v{{color:var(--navy);font-size:20px;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;border:1px solid var(--line)}}
th{{background:var(--navy);color:#fff;text-align:left;padding:6px 10px;font-weight:500}}
td{{padding:6px 10px;border-top:1px solid var(--line)}} td.n,th.n{{text-align:right}}
.bar{{height:8px;background:var(--navy);border-radius:4px}}
.klein{{font-size:11px;color:#4a5262}} footer{{margin-top:20px;font-size:11px;color:#4a5262}}
ul{{margin:4px 0 0 18px;padding:0}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
"""


def _header(b: dict) -> str:
    img = f'<img src="{b["logo"]}" alt="{escape(b["logo_alt"])}">' if b["logo"] else ""
    name = f'<span class="name">{escape(b["name"])}</span>' if b["name"] else ""
    return f"<header>{img}{name}</header>"


def _footer(b: dict) -> str:
    return f"<footer>{b['footer']}</footer>" if b["footer"] else ""


def page(title: str, body: str, extra_script: str = "") -> str:
    b = branding()
    html = (f"<!doctype html><html lang=\"nl\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{escape(title)}</title><style>{_style(b['colors'])}</style></head><body>"
            f"{_header(b)}{body}{_footer(b)}{extra_script}</body></html>")
    return ensure(html, edition.REQUIRE_ATTRIBUTION)


DASH_BODY = """<main><h1 id="titel">Dashboard</h1><p class="klein" id="sub"></p>
<div class="grid" id="kpi"></div><h2>Debiteuren</h2><div id="deb"></div>
<h2>Crediteuren</h2><div id="cred"></div><h2>Afpuntingsvoorstellen</h2><div id="afp"></div><h2>Btw-saldo (indicatie)</h2><div id="btw"></div>
<h2>Bronnen en aannames</h2><div class="klein" id="bron"></div></main>"""

DASH_JS = r"""<script>
(function(){
var fmt=new Intl.NumberFormat('nl-BE',{style:'currency',currency:'EUR'});
function e(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]});}
function m(x){return x==null?'-':fmt.format(x);}
function ageTable(a){if(!a)return '';var rows='';var max=1;var k=Object.keys(a.ouderdom.buckets);
k.forEach(function(b){max=Math.max(max,Math.abs(a.ouderdom.buckets[b].bedrag));});
k.forEach(function(b){var v=a.ouderdom.buckets[b];rows+='<tr><td>'+e(b.replace('_',' '))+'</td><td class="n">'+v.aantal+'</td><td class="n">'+m(v.bedrag)+'</td><td><div class="bar" style="width:'+Math.round(Math.abs(v.bedrag)/max*100)+'%"></div></td></tr>';});
var top='';(a.top||[]).forEach(function(t){top+='<tr><td>'+e(t.relatie)+'</td><td class="n">'+t.posten+'</td><td class="n">'+m(t.openstaand)+'</td></tr>';});
return '<table><tr><th>Ouderdom (dagen na vervaldag)</th><th class="n">Aantal</th><th class="n">Bedrag</th><th></th></tr>'+rows+
'<tr><td><strong>'+e(a.ouderdom.negatieve_posten.label)+'</strong></td><td class="n">'+a.ouderdom.negatieve_posten.aantal+'</td><td class="n">'+m(a.ouderdom.negatieve_posten.bedrag)+'</td><td></td></tr></table>'+
'<p class="klein">DSO/DPO: '+(a.dagen&&a.dagen.waarde_dagen!=null?a.dagen.waarde_dagen+' dagen':'niet berekend')+'</p>'+
(top?'<table><tr><th>Top relaties</th><th class="n">Posten</th><th class="n">Openstaand</th></tr>'+top+'</table>':'');}
function afpBlock(d){var a=d.afpunting;if(!a)return '';var h='';['debiteuren','crediteuren'].forEach(function(s){var x=a[s];if(!x)return;var sm=x.samenvatting;
h+='<p><strong>'+e(s)+'</strong>: '+sm.voorstellen+' voorstellen (hoog '+sm.hoog+', middel '+sm.middel+', laag '+sm.laag+'); '+sm.negatieve_posten_zonder_voorstel+' negatieve posten zonder voorstel.</p>';
if(x.top_voorstellen&&x.top_voorstellen.length){h+='<table><tr><th>Voorstel</th><th>Type</th><th class="n">Zekerheid</th><th class="n">Betalingen</th><th class="n">Facturen</th></tr>';
x.top_voorstellen.forEach(function(v){h+='<tr><td>'+e(v.id)+' '+e((v.relaties||[]).join(' / '))+'</td><td>'+e(v.type)+'</td><td class="n">'+v.zekerheid+'</td><td class="n">'+m(v.som_betalingen)+'</td><td class="n">'+m(v.som_facturen)+'</td></tr>';});h+='</table>';}});
if(d.afpuntingscheck_voorstel)h+='<p class="klein">'+e(d.afpuntingscheck_voorstel)+'</p>';return h;}
function render(d){if(!d)return;var k=d.kerncijfers||{};
document.getElementById('titel').textContent='Dashboard '+(d.administratie||'');
document.getElementById('sub').textContent='Periode '+(d.periode?d.periode.van+' tot '+d.periode.tot:'')+' | peildatum '+(d.periode?d.periode.peildatum:'');
var cards=[['Omzet',m(k.omzet)],['Kosten',m(k.kosten)],['Resultaat',m(k.resultaat)],['Liquide middelen',m(k.liquide_middelen)],
['Liquiditeit (current ratio)',k.liquiditeit==null?'-':k.liquiditeit],['Openstaande debiteuren',m(d.debiteuren&&d.debiteuren.ouderdom.netto)],
['Openstaande crediteuren',m(d.crediteuren&&d.crediteuren.ouderdom.netto)],['Btw netto te betalen',m(d.btw&&d.btw.netto_te_betalen)]];
document.getElementById('kpi').innerHTML=cards.map(function(c){return '<div class="card"><div class="l">'+e(c[0])+'</div><div class="v">'+e(c[1])+'</div></div>';}).join('');
document.getElementById('deb').innerHTML=ageTable(d.debiteuren);document.getElementById('cred').innerHTML=ageTable(d.crediteuren);
document.getElementById('afp').innerHTML=afpBlock(d);document.getElementById('btw').innerHTML=d.btw?'<p>Te vorderen (411): '+m(d.btw.btw_te_vorderen_411)+' | te betalen (451): '+m(d.btw.btw_te_betalen_451)+'</p><p class="klein">'+e(d.btw.opmerking)+'</p>':'';
document.getElementById('bron').innerHTML='<ul>'+(d.bronnen||[]).map(function(b){return '<li>'+e(b)+'</li>';}).join('')+'</ul><ul>'+(d.aannames||[]).map(function(b){return '<li>'+e(b)+'</li>';}).join('')+'</ul>';}
var el=document.getElementById('yuki-data');if(el){try{render(JSON.parse(el.textContent));}catch(x){}}
var id=0;function send(msg){window.parent.postMessage(msg,'*');}
window.addEventListener('message',function(ev){var d=ev.data;if(!d||d.jsonrpc!=='2.0')return;
if(d.method==='ui/notifications/tool-result'&&d.params){render(d.params.structuredContent||null);}
if(d.id===1&&d.result){send({jsonrpc:'2.0',method:'ui/notifications/initialized'});}});
if(window.parent!==window){send({jsonrpc:'2.0',id:1,method:'ui/initialize',params:{appInfo:{name:'yuki-dashboard',version:'1.0.0'},appCapabilities:{},protocolVersion:'2025-11-21'}});}
})();
</script>"""


def dashboard_html(data: dict | None = None) -> str:
    """Dashboardpagina. Met ``data``: statische export (gegevens ingebed). Zonder: widgetsjabloon."""
    embed = ""
    if data is not None:
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        embed = f'<script type="application/json" id="yuki-data">{payload}</script>'
    return page("Dashboard", DASH_BODY + embed, DASH_JS)


def afpunting_html(out: dict) -> str:
    """Export van de afpuntingsvoorstellen; zelfde huisstijl-kader als de andere exports."""
    parts = [f"<main><h1>Afpuntingsvoorstellen {escape(str(out.get('administratie', '')))}</h1>",
             f"<p class=\"klein\">Peildatum {escape(str(out.get('peildatum', '')))}. Enkel voorstellen: er is niets afgepunt of gewijzigd in Yuki.</p>"]
    for sd, r in out["resultaten"].items():
        sm = r["samenvatting"]
        parts.append(f"<h2>{escape(sd.capitalize())}</h2><p class=\"klein\">{sm['negatieve_posten']} negatieve posten, {sm['open_facturen']} open facturen, "
                     f"{sm['voorstellen']} voorstellen (hoog {sm['hoog']}, middel {sm['middel']}, laag {sm['laag']}); "
                     f"{sm['negatieve_posten_zonder_voorstel']} negatieve posten zonder voorstel.</p>")
        for v in r["voorstellen"]:
            rows = "".join(f"<tr><td>{escape(d['rol'])}</td><td>{escape(str(d['relatie']))}</td><td>{escape(str(d['referentie'] or ''))}</td>"
                           f"<td>{escape(str(d['datum'] or ''))}</td><td class=\"n\">{d['bedrag']:.2f}</td></tr>" for d in v["documenten"])
            parts.append(f"<h3>{escape(v['id'])} - {escape(v['type'])} - zekerheid {v['zekerheid']:.2f} ({escape(v['zekerheid_label'])})</h3>"
                         f"<table><tr><th>Rol</th><th>Relatie</th><th>Referentie</th><th>Datum</th><th class=\"n\">Bedrag</th></tr>{rows}</table>"
                         f"<p class=\"klein\">Verschil {v['verschil']:.2f}. Reden: {escape('; '.join(v['reden']))}.<br>Voorgestelde actie: {escape(v['voorgestelde_actie'])}</p>")
        if r["zonder_voorstel"]:
            rows = "".join(f"<tr><td>{escape(str(d['relatie']))}</td><td>{escape(str(d['referentie'] or ''))}</td><td>{escape(str(d['datum'] or ''))}</td>"
                           f"<td class=\"n\">{d['bedrag']:.2f}</td><td>{escape(d['voorgestelde_actie'])}</td></tr>" for d in r["zonder_voorstel"])
            parts.append("<h3>Negatieve posten zonder voorstel</h3><table><tr><th>Relatie</th><th>Referentie</th><th>Datum</th><th class=\"n\">Bedrag</th><th>Actie</th></tr>"
                         + rows + "</table>")
    parts.append("<p class=\"klein\">" + escape(" ".join(out.get("aannames", []))) + "</p></main>")
    return page("Afpuntingsvoorstellen", "".join(parts))


def handleiding_html() -> str:
    return page("Handleiding saldi", "<main>" + handleiding_html_body() + "</main>")


def widget_resource() -> dict:
    return {"uri": "ui://yuki/dashboard.html", "name": "yuki-dashboard", "title": "Yuki dashboard",
            "description": "Kerncijfers, ouderdomsanalyse en btw-indicatie (alleen lezen).",
            "mimeType": MCP_APP_MIME,
            "_meta": {"ui": {"csp": {"connectDomains": [], "resourceDomains": []}, "prefersBorder": True}}}
