#!/usr/bin/env python3
"""节点级思维导图 HTML 生成器。用法: gen_mindmap.py <data.json> <out.html>
data.json: {title, subtitle, footer, branches:[{name,color,bg,points:[[title,badge,text]],figs:[[path,cap]]}]}
"""
import json, sys, base64, os, html

CSS = """
:root{--blue:#3B6FB6;--line:#C9D6E8;--ink:#1A1A1A;--gray:#71717A}
*{box-sizing:border-box}
body{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;color:var(--ink);margin:0;background:#F6F8FC;line-height:1.65}
.wrap{max-width:1060px;margin:0 auto;padding:24px 18px 60px}
header{background:linear-gradient(135deg,#3B6FB6,#2E7D4F);color:#fff;border-radius:14px;padding:22px 26px;margin-bottom:16px}
header h1{margin:0 0 6px;font-size:23px}
header p{margin:0;opacity:.92;font-size:13.5px}
h2{font-size:18px;border-left:5px solid var(--blue);padding-left:10px;margin:26px 0 12px}
h2 .sub{font-size:12.5px;color:var(--gray);font-weight:normal;margin-left:8px}
.legend{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:8px;background:#fff;border:1px solid #D8E0EC;border-radius:12px;padding:12px;margin-bottom:6px;font-size:13px}
.bd{display:inline-block;font-size:11px;padding:1px 8px;border-radius:99px;margin-right:4px}
.tree,.tree ul{list-style:none;margin:0;padding:0}
.tree{padding-left:6px}
.tree ul{padding-left:26px;position:relative}
.tree ul::before{content:"";position:absolute;left:9px;top:-14px;bottom:16px;border-left:2px solid var(--line)}
.tree li{position:relative;padding:5px 0 5px 24px}
.tree li::before{content:"";position:absolute;left:-17px;top:0;height:100%;border-left:2px solid var(--line)}
.tree li:last-child::before{height:24px}
.tree li::after{content:"";position:absolute;left:-17px;top:24px;width:20px;border-top:2px solid var(--line)}
.node{display:inline-block;background:#fff;border:1px solid #D8E0EC;border-left-width:5px;border-radius:9px;padding:7px 12px;font-size:13.5px;max-width:700px}
.root{font-size:17px;font-weight:700;background:linear-gradient(135deg,#3B6FB6,#2E7D4F);color:#fff;border:none;padding:10px 18px}
.sec{font-weight:700;font-size:15px}
.kname{font-weight:700}
details.figbox{margin-top:6px}
details.figbox summary{cursor:pointer;font-size:12.5px;color:#3B6FB6;user-select:none}
details.figbox img{max-width:520px;width:100%;border:1px solid #D8E0EC;border-radius:8px;margin-top:6px;background:#fff}
figcaption{font-size:12px;color:var(--gray);text-align:center;margin-top:5px}
footer{margin-top:30px;font-size:12px;color:var(--gray);text-align:center}
"""

def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def main(data_path, out_path):
    d = json.load(open(data_path, encoding="utf-8"))
    branches = ""
    for br in d["branches"]:
        ps = ""
        for title, badge, text in br["points"]:
            bc, bt = d["badges"][badge]
            ps += f'''<li><div class="node" style="border-left-color:{br['color']}"><span class="kname">{title}</span> <span class="bd" style="background:{bc};color:{bt}">{badge}</span><br>{text}</div></li>'''
        fs = ""
        for path, cap in br.get("figs", []):
            fs += f'''<li><div class="node" style="border-left-color:#C47B17;background:#FFFBF4;font-size:13px">📐 {cap.split("(")[0]}</div>
<details class="figbox"><summary>查看教材原图</summary><img src="data:image/png;base64,{b64(path)}" alt="{html.escape(cap)}"><figcaption>{cap}</figcaption></details></li>'''
        branches += f'''<li><div class="node" style="border-left-color:{br['color']};background:{br['bg']}"><span class="sec">{br['name']}</span></div>
<ul>{ps}{fs}</ul></li>'''
    leg = "<div class='legend'>" + "".join(
        f"<div><span class='bd' style='background:{c};color:{t}'>{n}</span></div>" for n, (c, t) in d["badges"].items()
    ) + "<div>📐 橙色节点=教材原图,点击展开</div></div>"
    page = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(d["title"])}</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>{d["title"]}</h1><p>{d.get("subtitle","")}</p></header>
<h2>图例<span class="sub">徽章标注知识点类型</span></h2>{leg}
<h2>思维导图<span class="sub">{d.get("order","从中心向外读")}</span></h2>
<ul class="tree"><li><div class="node root">{d["root"]}</div><ul>{branches}</ul></li></ul>
<footer>{d.get("footer","")}</footer></div></body></html>'''
    open(out_path, "w", encoding="utf-8").write(page)
    print("written:", out_path, f"{os.path.getsize(out_path)/1024/1024:.2f} MB")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
