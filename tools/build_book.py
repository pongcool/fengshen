"""รวมเล่มคำแปลเป็น HTML ไฟล์เดียวและ EPUB 3 (PLAN.md ระยะ 4)

ใช้: python -X utf8 tools/build_book.py            -> build/fengshen.html, build/fengshen.epub
     python -X utf8 tools/build_book.py --check    -> ตรวจผลรวมเล่มโดยไม่เขียนไฟล์

ใช้ไลบรารีมาตรฐานเท่านั้น แปลงเฉพาะ Markdown ที่โครงการใช้: หัวบท (#, ##), ย่อหน้า, บทกวีแบบ >,
รายการ -, ตัวหนา **…**, เชิงอรรถ [^id] / [^id]: ข้อความ และตัดป้าย <!-- ยN --> ออก
ส่วนหน้าอยู่ใน book/*.md; ภาคผนวก (รายชื่อตัวละคร, ดัชนีของวิเศษ ค่ายกล วิชา) สร้างจาก
CHARACTERS.md และ GLOSSARY.md โดยหาบทที่ปรากฏครั้งแรกจากคำแปล ไม่เติมคำอธิบายที่ต้นฉบับไม่ได้ให้
"""
import argparse
import datetime
import html
import re
import uuid
import zipfile

from term_stats import ROOT

TITLE = "เฟิงเสินเหยี่ยนอี้"
SUBTITLE = "封神演義 ฉบับแปลภาษาไทย"
CREATOR = "แปลโดย Claude (Anthropic) ตรวจโดย Codex (OpenAI)"
RIGHTS = "คำแปลอนุญาตภายใต้ CC BY-NC 4.0 (ห้ามใช้เพื่อการค้า) ต้นฉบับจีนเป็นสาธารณสมบัติ"
BOOK_ID = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "hongsin-fengshen-yanyi-th"))
ITEM_TYPES = {"ของวิเศษ", "ค่ายกล", "วิชา", "อาวุธ", "พาหนะ"}
# แถว CHARACTERS ที่จีน/ไทยหลายรูปเป็นชื่อเรียกของคนเดียว (ตรวจจากช่องข้อมูลเมื่อ 2026-11-07, RBUILD-C3)
ALIAS_ROWS = {"C078", "C081", "C159", "C160", "C164", "C167", "C170", "C236", "C277"}
# 月合老人 กับ 月合仙翁 เป็นคนเดียวกัน ส่วน 符元仙翁 เป็นอีกองค์
SPECIAL_ROWS = {"C221": [("月合仙翁", "เยว่เหอเซียนเวิง"), ("符元仙翁", "ฝูหยวนเซียนเวิง")]}

CSS = """
body { font-family: "Sarabun", "Noto Serif Thai", "Noto Sans Thai", "Tahoma", serif; line-height: 1.8; margin: 0 auto; max-width: 42em; padding: 0 1em; }
h1 { font-size: 1.5em; margin: 2em 0 1em; text-align: center; }
h2 { font-size: 1.2em; margin: 1.5em 0 0.5em; }
p { margin: 0 0 0.8em; text-indent: 0; }
blockquote { margin: 0.6em 0 1em 1.5em; padding: 0; }
blockquote p { margin: 0 0 0.2em; }
.footnotes { border-top: 1px solid #999; margin-top: 2em; padding-top: 0.5em; font-size: 0.9em; }
.footnotes ol { padding-left: 1.5em; }
sup a, .footnotes a { text-decoration: none; }
table { border-collapse: collapse; width: 100%; font-size: 0.95em; }
td, th { border-bottom: 1px solid #ccc; padding: 0.2em 0.4em; text-align: left; vertical-align: top; }
.title { text-align: center; margin-top: 30%; }
.title p { text-align: center; }
nav ol { list-style: none; padding-left: 0; }
"""


REFCOUNT = {}


def esc(s):
    return html.escape(s, quote=False)


def inline(text, fnmap):
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)

    def ref(m):
        key = m.group(1)
        if key not in fnmap:
            raise ValueError(f"เชิงอรรถไม่มีคำอธิบาย: {key}")
        n, anchor = fnmap[key]
        REFCOUNT[anchor] = REFCOUNT.get(anchor, 0) + 1
        return f'<sup><a id="r-{anchor}-{REFCOUNT[anchor]}" href="#f-{anchor}">{n}</a></sup>'

    return re.sub(r"\[\^([^\]]+)\]", ref, out)


def convert(md, slug):
    """แปลง Markdown ของโครงการเป็น (title, xhtml body)"""
    md = re.sub(r"<!--.*?-->\n?", "", md, flags=re.S)
    lines = md.split("\n")
    defs = {}
    body_lines = []
    for line in lines:
        m = re.match(r"\[\^([^\]]+)\]:\s*(.*)", line)
        if m:
            defs[m.group(1)] = m.group(2)
        else:
            body_lines.append(line)
    order = []
    for m in re.finditer(r"\[\^([^\]]+)\](?!:)", "\n".join(body_lines)):
        if m.group(1) not in order:
            order.append(m.group(1))
    fnmap = {k: (i + 1, f"{slug}-{i + 1}") for i, k in enumerate(order)}
    unused = set(defs) - set(order)
    if unused:
        raise ValueError(f"{slug}: เชิงอรรถไม่ถูกอ้าง {sorted(unused)}")

    title = None
    parts = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            parts.append(f"<h1>{inline(title, fnmap)}</h1>")
            i += 1
        elif line.startswith("## "):
            parts.append(f"<h2>{inline(line[3:].strip(), fnmap)}</h2>")
            i += 1
        elif line.startswith(">"):
            verses = []
            while i < len(body_lines) and body_lines[i].startswith(">"):
                t = body_lines[i][1:].strip()
                if t:
                    verses.append(f"<p>{inline(t, fnmap)}</p>")
                i += 1
            parts.append("<blockquote>" + "".join(verses) + "</blockquote>")
        elif line.startswith("- "):
            items = []
            while i < len(body_lines) and body_lines[i].startswith("- "):
                items.append(f"<li>{inline(body_lines[i][2:].strip(), fnmap)}</li>")
                i += 1
            parts.append("<ul>" + "".join(items) + "</ul>")
        else:
            para = [line.strip()]
            i += 1
            while i < len(body_lines) and body_lines[i].strip() and not body_lines[i].startswith((">", "#", "- ")):
                para.append(body_lines[i].strip())
                i += 1
            parts.append(f"<p>{inline(' '.join(para), fnmap)}</p>")
    if order:
        notes = []
        for k in order:
            n, anchor = fnmap[k]
            if k not in defs:
                raise ValueError(f"{slug}: ไม่มีคำอธิบายเชิงอรรถ {k}")
            backs = " ".join(f'<a href="#r-{anchor}-{j}">↩</a>' for j in range(1, REFCOUNT.get(anchor, 1) + 1))
            notes.append(f'<li id="f-{anchor}">{inline(defs[k], fnmap)} {backs}</li>')
        parts.append('<section class="footnotes"><ol>' + "".join(notes) + "</ol></section>")
    return title, "\n".join(parts)


def table_rows(path):
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            yield [c.strip() for c in line.strip().strip("|").split("|")]


def ref_chapters(cell):
    return sorted({int(x) for x in re.findall(r"(?<!\d)(\d{3})(?!\d)", cell) if 1 <= int(x) <= 100})


def first_chapter(zh, name, src, th, refs=()):
    """บทแรกที่ต้นฉบับมีคำจีนนี้และคำแปลบทเดียวกันมีรูปไทยนี้ (RBUILD-C1)
    ถ้าไม่พบ ใช้บทแรกในช่องอ้างอิงของเอกสารกลาง"""
    for n in sorted(src):
        if zh in src[n] and n in th and name in th[n]:
            return int(n)
    return refs[0] if refs else None


def split_cell(cell):
    return [x.strip() for x in re.sub(r"\s*\(.*?\)", "", cell).split("/") if x.strip()]


def appendix_characters(src, th):
    rows = set()
    for c in table_rows("CHARACTERS.md"):
        if not re.fullmatch(r"C\d+", c[0]):
            continue
        zh_forms, th_forms = split_cell(c[1]), split_cell(c[2])
        refs = ref_chapters(c[-1])
        if not zh_forms or not th_forms:
            continue
        # แถวที่รวมหลายบุคคล: จำนวนรูปไทยเท่ารูปจีนและมากกว่าหนึ่ง (RBUILD-C3)
        # ยกเว้นแถวที่เป็นชื่อเรียกหลายรูปของคนเดียว (ALIAS_ROWS) และแถวพิเศษใน SPECIAL_ROWS
        if c[0] in SPECIAL_ROWS:
            people = SPECIAL_ROWS[c[0]]
        elif c[0] in ALIAS_ROWS or not (len(th_forms) > 1 and len(th_forms) == len(zh_forms)):
            people = [(zh_forms[0], th_forms[0])]
        else:
            people = list(zip(zh_forms, th_forms))
        for zh, name in people:
            if len(people) > 1:
                ch = first_chapter(zh, name, src, th)
            else:
                ch = refs[0] if refs else first_chapter(zh, name, src, th)
            if ch:
                rows.add((ch, name, zh))
    rows = sorted(rows)
    out = ["# รายชื่อตัวละคร", "", "เรียงตามบทที่ปรากฏครั้งแรก ชื่อเดียวกันอาจมีฉายาหรือคำเรียกอื่นในเนื้อเรื่อง ชื่อที่ซ้ำกันแต่บทแรกต่างกันเป็นคนละคน", ""]
    body = "".join(f"<tr><td>{esc(n)}</td><td>{esc(z)}</td><td>{ch}</td></tr>" for ch, n, z in rows)
    return out, f"<table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>บทแรก</th></tr>{body}</table>", len(rows)


def item_type(cell):
    for t in ITEM_TYPES:
        if cell.startswith(t):
            return t
    return None


def appendix_items(src, th):
    rows, seen = [], set()
    for c in table_rows("GLOSSARY.md"):
        if len(c) < 3:
            continue
        kind = item_type(c[2])
        if not kind:
            continue
        zh_forms, th_forms = split_cell(c[0]), split_cell(c[1])
        if len(zh_forms) != len(th_forms):
            zh_forms, th_forms = zh_forms[:1], th_forms[:1]
        for z, t in zip(zh_forms, th_forms):
            if "…" in t or z in seen or not re.fullmatch(r"[㐀-鿿豈-﫿]{2,}", z):
                continue
            refs = ref_chapters(c[4]) if len(c) > 4 else []
            # แถวรายการเดียวที่มีตำแหน่งอ้างอิง ใช้บทแรกตามเอกสารกลาง (เช่น 金箍 ของหม่าซุ่ย 082 ไม่ใช่ห่วงคาดหัวใน 074)
            ch = refs[0] if refs and len(zh_forms) == 1 else first_chapter(z, t, src, th, refs)
            if ch:
                seen.add(z)
                rows.append((ch, t, z, kind))
    rows.sort()
    out = ["# ดัชนีของวิเศษ ค่ายกล และวิชา", "", "เรียงตามบทที่ปรากฏครั้งแรก คุณสมบัติของแต่ละรายการให้อ่านจากเนื้อเรื่องและเชิงอรรถ", ""]
    body = "".join(f"<tr><td>{esc(t)}</td><td>{esc(z)}</td><td>{esc(k)}</td><td>{ch}</td></tr>" for ch, t, z, k in rows)
    return out, f"<table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>ประเภท</th><th>บทแรก</th></tr>{body}</table>", len(rows)


def collect():
    th = {p.stem: p.read_text(encoding="utf-8") for p in sorted((ROOT / "translations" / "th").glob("[0-9][0-9][0-9].md"))}
    src = {p.name[:3]: p.read_text(encoding="utf-8") for p in (ROOT / "chapters").glob("[0-9][0-9][0-9]-*.md")}
    sections = []
    for p in sorted((ROOT / "book").glob("*.md")):
        title, body = convert(p.read_text(encoding="utf-8"), p.stem)
        sections.append((p.stem, title, body))
    for n, text in th.items():
        title, body = convert(text, f"ch{n}")
        sections.append((f"ch{n}", title, body))
    for slug, fn in (("zz-characters", appendix_characters), ("zz-items", appendix_items)):
        head, table, count = fn(src, th)
        title, body = convert("\n".join(head), slug)
        sections.append((slug, title, body + table))
        print(f"{title}: {count} รายการ")
    return sections


def xhtml(title, body, css_href):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="th" xml:lang="th">'
            f'<head><meta charset="utf-8"/><title>{esc(title)}</title><link rel="stylesheet" href="{css_href}"/></head>'
            f"<body>{body}</body></html>")


def build_html(sections, out):
    toc = "".join(f'<li><a href="#{s}">{esc(t)}</a></li>' for s, t, _ in sections)
    parts = [f'<section class="title"><h1>{TITLE}</h1><p>{SUBTITLE}</p><p>{CREATOR}</p><p>{RIGHTS}</p></section>',
             f'<nav><h2>สารบัญ</h2><ol>{toc}</ol></nav>']
    for slug, _, body in sections:
        parts.append(f'<section id="{slug}">{body}</section>')
    doc = ('<!DOCTYPE html><html lang="th"><head><meta charset="utf-8"/>'
           '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
           f"<title>{TITLE}</title><style>{CSS}</style></head><body>{''.join(parts)}</body></html>")
    out.write_text(doc, encoding="utf-8")


def build_epub(sections, out):
    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest, spine = [], []
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        title_body = f'<section class="title"><h1>{TITLE}</h1><p>{SUBTITLE}</p><p>{CREATOR}</p><p>{RIGHTS}</p></section>'
        z.writestr("OEBPS/title.xhtml", xhtml(TITLE, title_body, "style.css"), compress_type=zipfile.ZIP_DEFLATED)
        manifest.append('<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="title"/>')
        for slug, title, body in sections:
            z.writestr(f"OEBPS/{slug}.xhtml", xhtml(title, body, "style.css"), compress_type=zipfile.ZIP_DEFLATED)
            manifest.append(f'<item id="{slug}" href="{slug}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="{slug}"/>')
        nav = "".join(f'<li><a href="{s}.xhtml">{esc(t)}</a></li>' for s, t, _ in sections)
        z.writestr("OEBPS/nav.xhtml",
                   xhtml("สารบัญ", f'<nav epub:type="toc" id="toc"><h1>สารบัญ</h1><ol>{nav}</ol></nav>', "style.css"),
                   compress_type=zipfile.ZIP_DEFLATED)
        manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
        manifest.append('<item id="css" href="style.css" media-type="text/css"/>')
        opf = ('<?xml version="1.0" encoding="utf-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="th">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               f'<dc:identifier id="bookid">{BOOK_ID}</dc:identifier><dc:title>{TITLE}</dc:title>'
               f'<dc:creator>{esc(CREATOR)}</dc:creator><dc:language>th</dc:language><dc:rights>{esc(RIGHTS)}</dc:rights>'
               f'<meta property="dcterms:modified">{modified}</meta></metadata>'
               f'<manifest>{"".join(manifest)}</manifest><spine>{"".join(spine)}</spine></package>')
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sections = collect()
    chapters = [s for s in sections if s[0].startswith("ch")]
    notes = sum(b.count('class="footnotes"') and b.count("<li id=\"f-") for _, _, b in sections)
    print(f"ส่วนทั้งหมด {len(sections)} (บท {len(chapters)}), เชิงอรรถ {notes}")
    if len(chapters) != 100:
        raise SystemExit("จำนวนบทไม่ครบ 100")
    if args.check:
        return
    out_dir = ROOT / "build"
    out_dir.mkdir(exist_ok=True)
    build_html(sections, out_dir / "fengshen.html")
    build_epub(sections, out_dir / "fengshen.epub")
    for f in ("fengshen.html", "fengshen.epub"):
        print(f"{out_dir / f}: {(out_dir / f).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
