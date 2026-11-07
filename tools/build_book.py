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
BOOK_ID = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "hongsin-fengshen-yanyi-th"))
ITEM_TYPES = {"ของวิเศษ", "ค่ายกล", "วิชา", "อาวุธ", "พาหนะ"}

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
        return f'<sup><a id="r-{anchor}" href="#f-{anchor}">{n}</a></sup>'

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
            notes.append(f'<li id="f-{anchor}">{inline(defs[k], fnmap)} <a href="#r-{anchor}">↩</a></li>')
        parts.append('<section class="footnotes"><ol>' + "".join(notes) + "</ol></section>")
    return title, "\n".join(parts)


def table_rows(path):
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            yield [c.strip() for c in line.strip().strip("|").split("|")]


def first_chapter(name, th):
    for n in sorted(th):
        if name in th[n]:
            return int(n)
    return None


def clean(cell):
    return re.sub(r"\s*\(.*?\)", "", cell).split(" / ")[0].split("/")[0].strip()


def appendix_characters(th):
    rows = []
    for c in table_rows("CHARACTERS.md"):
        if not re.fullmatch(r"C\d+", c[0]):
            continue
        name, zh = clean(c[2]), clean(c[1])
        if not name or not zh:
            continue
        ch = first_chapter(name, th)
        if ch:
            rows.append((ch, name, zh))
    rows.sort()
    out = ["# รายชื่อตัวละคร", "", "เรียงตามบทที่ชื่อไทยปรากฏครั้งแรกในคำแปล ชื่อเดียวกันอาจมีฉายาหรือคำเรียกอื่นในเนื้อเรื่อง", ""]
    body = "".join(f"<tr><td>{esc(n)}</td><td>{esc(z)}</td><td>{ch}</td></tr>" for ch, n, z in rows)
    return out, f"<table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>บทแรก</th></tr>{body}</table>", len(rows)


def appendix_items(th):
    rows, seen = [], set()
    for c in table_rows("GLOSSARY.md"):
        if len(c) < 3 or c[2] not in ITEM_TYPES:
            continue
        zh_forms = [z.strip() for z in re.sub(r"\(.*?\)", "", c[0]).split("/")]
        th_forms = [t.strip() for t in re.sub(r"\(.*?\)", "", c[1]).split("/")]
        if len(zh_forms) != len(th_forms):
            zh_forms, th_forms = zh_forms[:1], th_forms[:1]
        for z, t in zip(zh_forms, th_forms):
            if not z or not t or "…" in t or t in seen or not re.search(r"[㐀-鿿]", z):
                continue
            ch = first_chapter(t, th)
            if ch:
                seen.add(t)
                rows.append((ch, t, z, c[2]))
    rows.sort()
    out = ["# ดัชนีของวิเศษ ค่ายกล และวิชา", "", "เรียงตามบทที่ปรากฏครั้งแรก คุณสมบัติของแต่ละรายการให้อ่านจากเนื้อเรื่องและเชิงอรรถ", ""]
    body = "".join(f"<tr><td>{esc(t)}</td><td>{esc(z)}</td><td>{esc(k)}</td><td>{ch}</td></tr>" for ch, t, z, k in rows)
    return out, f"<table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>ประเภท</th><th>บทแรก</th></tr>{body}</table>", len(rows)


def collect():
    th = {p.stem: p.read_text(encoding="utf-8") for p in sorted((ROOT / "translations" / "th").glob("[0-9][0-9][0-9].md"))}
    sections = []
    for p in sorted((ROOT / "book").glob("*.md")):
        title, body = convert(p.read_text(encoding="utf-8"), p.stem)
        sections.append((p.stem, title, body))
    for n, text in th.items():
        title, body = convert(text, f"ch{n}")
        sections.append((f"ch{n}", title, body))
    for slug, fn in (("zz-characters", appendix_characters), ("zz-items", appendix_items)):
        head, table, count = fn(th)
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
    parts = [f'<section class="title"><h1>{TITLE}</h1><p>{SUBTITLE}</p><p>{CREATOR}</p></section>',
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
        title_body = f'<section class="title"><h1>{TITLE}</h1><p>{SUBTITLE}</p><p>{CREATOR}</p></section>'
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
               f'<dc:creator>{esc(CREATOR)}</dc:creator><dc:language>th</dc:language>'
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
