#!/usr/bin/env python3
"""通用节点讲义 HTML 生成器。
用法: gen_lecture.py <data.json> <out.html>
data.json 结构:
{
 "title": "...", "subtitle": "...",
 "legend": [["#D93025","必考核心"],["#B8860B","重要考点"]],
 "blocks": [
   {"type":"h","text":"一、..."},
   {"type":"p","html":"段落,可含 <font color=...><b>...</b></font>"},
   {"type":"list","items":[["一级", [["二级1"],["二级2", [["三级"]])]]]]},
   {"type":"table","header":[...],"rows":[[html,...],...]},
   {"type":"fig","src":"/abs/path.png","caption":"图4-1 ...(P66)","big":false},
   {"type":"quiz","items":[{"q":"...","a":"..."}]},
   {"type":"note","html":"..."}
 ]
}
"""
import json, sys, base64, os, html, pymupdf

CSS = """
:root{--blue:#3B6FB6;--ink:#1A1A1A;--gray:#71717A;--line:#C9D6E8}
*{box-sizing:border-box}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;color:var(--ink);margin:0;background:#F7F9FC;line-height:1.75}
.wrap{max-width:920px;margin:0 auto;padding:24px 20px 60px}
header{background:linear-gradient(135deg,#3B6FB6,#2E7D4F);color:#fff;border-radius:14px;padding:22px 26px;margin-bottom:16px}
header h1{margin:0 0 6px;font-size:23px}
header p{margin:0;opacity:.92;font-size:13.5px}
.legend{display:flex;gap:16px;flex-wrap:wrap;background:#fff;border:1px solid #D8E0EC;border-radius:10px;padding:10px 14px;margin-bottom:18px;font-size:13.5px}
h2{font-size:18px;border-left:5px solid var(--blue);padding-left:10px;margin:28px 0 10px}
h3{font-size:15.5px;margin:18px 0 8px;color:#22406B}
p{font-size:14.5px;margin:8px 0}
ul,ol{padding-left:26px;margin:6px 0}
li{font-size:14.5px;margin:4px 0}
table{width:100%;border-collapse:collapse;background:#fff;font-size:13.5px;border-radius:10px;overflow:hidden;margin:10px 0}
th{background:var(--blue);color:#fff;padding:8px 10px;text-align:left}
td{border-bottom:1px solid #EDF1F7;padding:8px 10px;vertical-align:top}
tr:last-child td{border-bottom:none}
figure{margin:14px 0;background:#fff;border:1px solid #D8E0EC;border-radius:10px;padding:10px}
figure.big img{width:100%}
figure img{max-width:460px;width:100%;display:block;margin:0 auto;border-radius:6px}
figcaption{font-size:12.5px;color:var(--gray);text-align:center;margin-top:6px}
.note{background:#FFF9EC;border:1px dashed #E0C068;border-radius:10px;padding:10px 14px;font-size:13.5px;margin:12px 0}
.quiz{background:#fff;border:1px solid #D8E0EC;border-radius:10px;padding:12px 16px;margin:10px 0}
.quiz .q{font-weight:700;margin-bottom:6px}
.quiz details{margin-top:6px}
.quiz summary{cursor:pointer;color:#3B6FB6;font-size:13px}
.quiz .a{background:#F2F8F3;border-radius:8px;padding:8px 12px;margin-top:6px;font-size:13.5px}
.ev{margin-top:8px}
.evcap{font-size:12px;color:#B36F0D;font-weight:700}
.ev img{max-width:100%;border:1px solid #C47B17;border-radius:6px;margin-top:4px;display:block}
footer{margin-top:30px;font-size:12px;color:var(--gray);text-align:center}
.tree,.tree ul{list-style:none;margin:0;padding:0}
.tree{padding-left:6px}
.tree ul{padding-left:26px;position:relative}
.tree ul::before{content:"";position:absolute;left:9px;top:-14px;bottom:16px;border-left:2px solid #C9D6E8}
.tree li{position:relative;padding:5px 0 5px 24px}
.tree li::before{content:"";position:absolute;left:-17px;top:0;height:100%;border-left:2px solid #C9D6E8}
.tree li:last-child::before{height:24px}
.tree li::after{content:"";position:absolute;left:-17px;top:24px;width:20px;border-top:2px solid #C9D6E8}
.tnode{display:inline-block;background:#fff;border:1px solid #D8E0EC;border-left-width:5px;border-radius:9px;padding:7px 12px;font-size:13.5px;max-width:700px}
.troot{font-size:16px;font-weight:700;background:linear-gradient(135deg,#3B6FB6,#2E7D4F);color:#fff;border:none;padding:9px 16px}
.tsec{font-weight:700;font-size:14.5px}
details.figbox{margin-top:6px}
details.figbox summary{cursor:pointer;font-size:12.5px;color:#3B6FB6;user-select:none}
details.figbox img{max-width:520px;width:100%;border:1px solid #D8E0EC;border-radius:8px;margin-top:6px;background:#fff}
figcaption{font-size:12px;color:#71717A;text-align:center;margin-top:5px}

"""

def b64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

def render_list(items, depth=0):
    out = ["<ul>"]
    for it in items:
        text = it[0]
        children = it[1] if len(it) > 1 else []
        out.append(f"<li>{text}")
        if children:
            out.append(render_list(children, depth+1))
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)

def main(data_path, out_path):
    d = json.load(open(data_path, encoding="utf-8"))
    parts = [f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(d["title"])}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header><h1>{d["title"]}</h1><p>{d.get("subtitle","")}</p></header>
<div class="legend"><b>考点分级:</b> {"".join(f'<span><font color="{c}"><b>■ {t}</b></font></span>' for c, t in d.get("legend", []))}</div>''']
    for b in d["blocks"]:
        t = b["type"]
        if t == "h": parts.append(f"<h2>{b['text']}</h2>")
        elif t == "h3": parts.append(f"<h3>{b['text']}</h3>")
        elif t == "p": parts.append(f"<p>{b['html']}</p>")
        elif t == "list": parts.append(render_list(b["items"]))
        elif t == "table":
            rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in b["rows"])
            head = "".join(f"<th>{h}</th>" for h in b["header"])
            parts.append(f"<table><tr>{head}</tr>{rows}</table>")
        elif t == "fig":
            big = " big" if b.get("big") else ""
            parts.append(f'<figure class="fig{big}"><img src="{b64(b["src"])}" alt="{html.escape(b.get("caption",""))}"><figcaption>{b.get("caption","")}</figcaption></figure>')
        elif t == "quiz":
            for item in b["items"]:
                ev_html = ""
                for ev in item.get("ev", []):
                    try:
                        doc = pymupdf.open(ev["pdf"])
                        page = doc[ev["page"] - 1]
                        W = page.rect.width
                        clip = pymupdf.Rect(ev.get("x0", 0.07 * W), ev["y0"], ev.get("x1", 0.94 * W), ev["y1"])
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6), clip=clip)
                        img = "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode()
                        ev_html += f'<div class="ev"><div class="evcap">📐 教材出处:{ev.get("cap","")}</div><img src="{img}" alt="教材原文截图"></div>'
                    except Exception as e:
                        ev_html += f'<div class="ev">教材截图生成失败:{e}</div>'
                ans = f'<div class="a">{item["a"]}{ev_html}</div>'
                parts.append(f'<div class="quiz"><div class="q">{item["q"]}</div><details><summary>查看参考答案与教材出处</summary>{ans}</details></div>')
        elif t == "note":
            parts.append(f'<div class="note">{b["html"]}</div>')
        elif t == "mindmap":
            branches = ""
            for br in b["branches"]:
                ps = ""
                for title, badge, text in br["points"]:
                    bc, bt = d["badges"][badge]
                    ps += f'<li><div class="tnode" style="border-left-color:{br["color"]}"><b>{title}</b> <span class="bd" style="background:{bc};color:{bt}">{badge}</span><br>{text}</div></li>'
                fs = ""
                for path, cap in br.get("figs", []):
                    fs += f'<li><div class="tnode" style="border-left-color:#C47B17;background:#FFFBF4;font-size:13px">📐 {cap.split("(")[0]}</div><details class="figbox"><summary>查看教材原图</summary><img src="{b64(path)}" alt="{html.escape(cap)}"><figcaption>{cap}</figcaption></details></li>'
                branches += f'<li><div class="tnode" style="border-left-color:{br["color"]};background:{br["bg"]}"><span class="tsec">{br["name"]}</span></div><ul>{ps}{fs}</ul></li>'
            parts.append(f'<ul class="tree"><li><div class="tnode troot">{b["root"]}</div><ul>{branches}</ul></li></ul>')
    parts.append(f'<footer>{d.get("footer","")}</footer></div></body></html>')
    open(out_path, "w", encoding="utf-8").write("".join(parts))
    print("written:", out_path, f"{os.path.getsize(out_path)/1024:.0f} KB")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
