"""Generates the hero banner and crop illustrations (SVG) into static/img. Replace any file with a real photo
(same name, e.g. static/img/hero.svg -> point the CSS at hero.jpg) whenever you have your own images.
Run: python tools/make_images.py"""
import os

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "img")
os.makedirs(os.path.join(OUT, "crops"), exist_ok=True)

vx, vy = 800, 400
rows = []
for i in range(-9, 10):
    x0, x1 = 800 + i * 240, 800 + (i + .5) * 240
    rows.append(f'<polygon points="{vx+(x0-vx)*.03:.0f},{vy+4} {vx+(x1-vx)*.03:.0f},{vy+4} {x1:.0f},720 {x0:.0f},720" '
                f'fill="{"#2f8f3d" if i % 2 == 0 else "#3aa04a"}"/>')
plants = []
for r in range(14):
    t = (r / 13) ** 1.8
    y, size = 420 + t * 290, 4 + t * 20
    for i in range(-10, 11):
        x = 800 + (i + .25) * (240 * (.03 + t * .97))
        if 0 <= x <= 1600:
            plants.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{size*.9:.1f}" ry="{size*.55:.1f}" fill="#1f6f33" opacity=".75"/>'
                          f'<ellipse cx="{x:.0f}" cy="{y-size*.35:.0f}" rx="{size*.55:.1f}" ry="{size*.4:.1f}" fill="#58b85a"/>')
hero = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 720" preserveAspectRatio="xMidYMid slice">
<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7cc4e8"/><stop offset=".6" stop-color="#cfeaf2"/><stop offset="1" stop-color="#fbeec2"/></linearGradient>
<radialGradient id="sun" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff7c2"/><stop offset=".45" stop-color="#ffe784" stop-opacity=".9"/><stop offset="1" stop-color="#ffe784" stop-opacity="0"/></radialGradient>
<linearGradient id="h1" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fc47a"/><stop offset="1" stop-color="#5fa35a"/></linearGradient>
<linearGradient id="h2" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#6fb064"/><stop offset="1" stop-color="#3f8f47"/></linearGradient></defs>
<rect width="1600" height="720" fill="url(#sky)"/><circle cx="1180" cy="190" r="190" fill="url(#sun)"/><circle cx="1180" cy="190" r="62" fill="#fff4b0"/>
<g fill="#fff" opacity=".85"><ellipse cx="330" cy="150" rx="120" ry="30"/><ellipse cx="420" cy="132" rx="80" ry="26"/><ellipse cx="900" cy="100" rx="110" ry="26"/><ellipse cx="980" cy="86" rx="70" ry="22"/></g>
<path d="M0 360 Q 220 250 480 340 T 980 330 T 1600 300 L1600 430 L0 430Z" fill="url(#h1)"/>
<path d="M0 395 Q 300 320 620 385 T 1200 370 T 1600 370 L1600 440 L0 440Z" fill="url(#h2)"/>
<g fill="#2e6b3a"><rect x="212" y="372" width="8" height="30"/><circle cx="216" cy="362" r="26"/><rect x="1330" y="366" width="8" height="34"/><circle cx="1334" cy="354" r="30"/></g>
<rect y="396" width="1600" height="324" fill="#3aa04a"/>{"".join(rows)}{"".join(plants)}
<g transform="translate(1180,300)"><ellipse cx="40" cy="388" rx="95" ry="14" fill="#000" opacity=".18"/>
<path d="M-8 380 L10 250 L74 250 L92 380Z" fill="#26493a"/><path d="M6 262 Q40 236 78 262 L86 330 L0 330Z" fill="#c9a24a"/>
<rect x="30" y="226" width="22" height="26" rx="9" fill="#a86f4a"/><circle cx="41" cy="212" r="27" fill="#b87a52"/>
<ellipse cx="41" cy="190" rx="66" ry="12" fill="#e5c46b"/><path d="M7 190 Q41 130 75 190Z" fill="#f0d27d"/>
<rect x="-4" y="262" width="20" height="82" rx="10" fill="#c9a24a" transform="rotate(14 -4 262)"/>
<rect x="68" y="262" width="20" height="92" rx="10" fill="#c9a24a" transform="rotate(-24 78 262)"/>
<rect x="116" y="196" width="7" height="190" fill="#7a5230" transform="rotate(10 119 290)"/>
<path d="M112 190 q26 -14 42 8 l-14 10 q-14 -10 -28 -2z" fill="#9aa4a8" transform="rotate(10 119 290)"/></g></svg>'''
open(os.path.join(OUT, "hero.svg"), "w").write(hero)


def frame(a, b, body, k=1.0):
    wrap = f'<g transform="translate(200,150) scale({k}) translate(-200,-155)">{body}</g>' if k != 1 else body
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260" preserveAspectRatio="xMidYMid slice">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
            f'<rect width="400" height="260" fill="url(#g)"/><path d="M0 210 Q100 190 200 205 T400 200 V260 H0Z" fill="#000" opacity=".12"/>{wrap}</svg>')


def leaf(x, y, rot, c="#3f9a4a", s=1):
    return f'<path d="M0 0 C 18 -22 52 -22 70 0 C 52 18 18 18 0 0Z" fill="{c}" transform="translate({x},{y}) rotate({rot}) scale({s})"/>'


def ears(cx, base, color, n=7, sway=0):
    o = f'<path d="M{cx} 230 Q {cx+sway} 150 {cx+sway*1.4} {base}" stroke="#7a9a3a" stroke-width="4" fill="none"/>'
    for i in range(n):
        y, x = base + i * 14, cx + sway * 1.4
        o += (f'<ellipse cx="{x-9:.0f}" cy="{y}" rx="6" ry="13" fill="{color}" transform="rotate(-28 {x-9:.0f} {y})"/>'
              f'<ellipse cx="{x+9:.0f}" cy="{y}" rx="6" ry="13" fill="{color}" transform="rotate(28 {x+9:.0f} {y})"/>')
    return o


C = {
 "wheat": frame("#f6e7b0", "#e0b95a", "".join(ears(cx, 60 + (k % 2) * 14, "#d9a83a", 7, (k - 2) * 8) for k, cx in enumerate([110, 160, 200, 240, 290]))),
 "rice": frame("#e6f2c4", "#b9d676", "".join(f'<path d="M{cx} 235 Q {cx+30} 120 {cx+75} 80" stroke="#6fa13c" stroke-width="4" fill="none"/>' + "".join(
     f'<ellipse cx="{cx+34+j*7}" cy="{104-j*5+(j%2)*7}" rx="4" ry="9" fill="#e9c45a" transform="rotate(40 {cx+34+j*7} {104-j*5})"/>' for j in range(9)) for cx in (110, 190, 260))),
 "maize": frame("#fff1b5", "#f1c84f", '<g transform="translate(200,130)"><path d="M-60 90 C-110 20 -70 -40 -30 -70 C-20 -20 -20 30 -10 90Z" fill="#4c9a43"/><path d="M60 90 C110 20 70 -40 30 -70 C20 -20 20 30 10 90Z" fill="#3f8a3b"/><rect x="-36" y="-82" width="72" height="170" rx="36" fill="#f5c53d"/>' + "".join(f'<circle cx="{-24+c*12}" cy="{-62+r*14}" r="5" fill="#e8aa1f"/>' for r in range(11) for c in range(5)) + '</g>'),
 "potato": frame("#e9dcc6", "#a98763", "".join(f'<ellipse cx="{x}" cy="{y}" rx="{w}" ry="{h}" fill="#c79a66" transform="rotate({r} {x} {y})"/>' + "".join(f'<circle cx="{x+dx}" cy="{y+dy}" r="3" fill="#8a6338"/>' for dx, dy in [(-14, -6), (10, 8), (0, -12), (16, -4)]) for x, y, w, h, r in [(130, 160, 56, 36, -12), (230, 150, 62, 40, 14), (185, 195, 50, 30, 4)])),
 "tomato": frame("#d9efd0", "#8cc17a", "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#df3a2f"/><circle cx="{x-r*.35:.0f}" cy="{y-r*.35:.0f}" r="{r*.22:.0f}" fill="#fff" opacity=".35"/><path d="M{x-14} {y-r+4} L{x} {y-r-8} L{x+14} {y-r+4} L{x+5} {y-r+10} L{x} {y-r+3} L{x-5} {y-r+10}Z" fill="#2f8f3d"/>' for x, y, r in [(150, 150, 46), (240, 140, 52), (200, 200, 40)])),
 "cotton": frame("#d6ecf2", "#9cc9a0", "".join(f'<path d="M{x} 235 L{x} {y+30}" stroke="#6b8f3a" stroke-width="5"/>' + leaf(x, y + 60, -150, "#4c9a43", .7) + "".join(f'<circle cx="{x+dx}" cy="{y+dy}" r="{rr}" fill="#fff"/>' for dx, dy, rr in [(-14, 0, 17), (14, 0, 17), (0, -16, 18), (0, 8, 16)]) + f'<path d="M{x-26} {y+22} L{x} {y+44} L{x+26} {y+22}" fill="#7a5a36"/>' for x, y in [(140, 110), (230, 90), (300, 130)])),
 "sugarcane": frame("#dff0c8", "#8fc060", "".join(f'<rect x="{x}" y="40" width="16" height="190" rx="6" fill="#7a9a3a"/>' + "".join(f'<rect x="{x-2}" y="{y}" width="20" height="5" rx="2" fill="#566f26"/>' for y in range(70, 230, 34)) + leaf(x + 8, 56, -70, "#4c9a43", 1.1) + leaf(x + 8, 56, -20, "#3f8a3b", 1.1) + leaf(x + 8, 66, -150, "#4c9a43", 1.0) for x in (130, 190, 250))),
 "groundnut": frame("#f3e4c8", "#c9a36d", "".join(f'<g transform="rotate({r} {x} {y})"><ellipse cx="{x-14}" cy="{y}" rx="24" ry="19" fill="#d8b27a"/><ellipse cx="{x+14}" cy="{y}" rx="24" ry="19" fill="#d8b27a"/></g>' for x, y, r in [(150, 150, -20), (250, 140, 16), (200, 200, 4)]), 1.6),
 "ragi": frame("#ead9f0", "#b28cc7", "".join(f'<path d="M{cx} 235 Q {cx+sw} 150 {cx+sw*1.6:.0f} 85" stroke="#6b8f3a" stroke-width="4" fill="none"/>' + "".join(f'<path d="M{cx+sw*1.6:.0f} 85 q {(k-2)*16} -34 {(k-2)*22} -56" stroke="#7b4a2d" stroke-width="7" stroke-linecap="round" fill="none"/>' for k in range(5)) for cx, sw in [(120, -10), (200, 4), (280, 14)])),
 "chickpea": frame("#e4efc9", "#a8c46e", "".join(leaf(x, y, r, "#4c9a43", .85) for x, y, r in [(120, 190, -60), (170, 170, -20), (230, 170, -150), (280, 190, -120)]) + "".join(f'<ellipse cx="{x}" cy="{y}" rx="19" ry="14" fill="#d9c27a"/><circle cx="{x-6}" cy="{y}" r="5" fill="#b89b4a"/><circle cx="{x+6}" cy="{y}" r="5" fill="#b89b4a"/>' for x, y in [(160, 120), (215, 105), (255, 130)]), 1.7),
 "default": frame("#dff0cf", "#9ccf86", '<path d="M200 235 Q 200 150 200 110" stroke="#3f8a3b" stroke-width="7" fill="none"/>' + leaf(200, 150, -30, "#4caf50", 1.2) + leaf(200, 130, -150, "#66bb6a", 1.2) + leaf(200, 112, -70, "#43a047", .9)),
}
for name, svg in C.items():
    open(os.path.join(OUT, "crops", name + ".svg"), "w").write(svg)
print("images written to", OUT)
