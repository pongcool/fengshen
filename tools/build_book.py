"""รวมเล่มคำแปลเป็น HTML ไฟล์เดียวและ EPUB 3 (PLAN.md ระยะ 4)

ใช้: python -X utf8 tools/build_book.py            -> build/fengshen.html, build/fengshen.epub
     python -X utf8 tools/build_book.py --check    -> ตรวจผลรวมเล่มโดยไม่เขียนไฟล์

ใช้ไลบรารีมาตรฐานเท่านั้น แปลงเฉพาะ Markdown ที่โครงการใช้: หัวบท (#, ##), ย่อหน้า, บทกวีแบบ >,
รายการ -, ตัวหนา **…**, เชิงอรรถ [^id] / [^id]: ข้อความ และตัดป้าย <!-- ยN --> ออก
ส่วนหน้าอยู่ใน book/*.md; ภาคผนวก (รายชื่อตัวละคร, ทำเนียบเทพที่แต่งตั้ง, ดัชนีของวิเศษ ค่ายกล วิชา) สร้างจาก
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
# ประเภทใน GLOSSARY ที่ไม่ได้ขึ้นต้นด้วย ITEM_TYPES แต่ควรอยู่ในดัชนี: คำนำหน้าประเภท -> ประเภทที่แสดง
TYPE_MAP = {"สัตว์พาหนะ": "พาหนะ", "กลุ่มค่ายกล": "ค่ายกล", "ไฟวิเศษ": "วิชา", "ผลไม้เซียน": "ของวิเศษ"}
# ไม่รวมเครื่องทรมาน (炮烙 蠆盆 酒池) เพราะไม่ใช่ของวิเศษ ค่ายกล หรือวิชา
# แถวที่ประเภทกว้างเกินจะจับด้วยคำนำหน้า (สัตว์ ผลไม้ คัมภีร์ สิ่งก่อสร้าง การทำนาย) ระบุด้วยรูปจีนแรกของแถว
ITEM_ZH = {"封神榜": "คัมภีร์", "封神臺": "สิ่งก่อสร้าง", "紅杏": "ของวิเศษ", "先天數": "วิชา",
           "哮天犬": "สัตว์วิเศษ", "鐵嘴神鷹": "สัตว์วิเศษ",
           "白象": "พาหนะ", "青毛獅子": "พาหนะ", "金毛犼": "พาหนะ"}
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
                # ถ้าหาไม่พบ (เช่น รูปในแถวต่างจากรูปในไฟล์ต้นฉบับ C268 鄭椿/鄭樁) ใช้บทแรกในช่องอ้างอิงแทนการตัดทิ้ง
                ch = first_chapter(zh, name, src, th, refs)
            else:
                ch = refs[0] if refs else first_chapter(zh, name, src, th)
            if ch:
                rows.add((ch, name, zh))
    rows = sorted(rows)
    out = ["# รายชื่อตัวละคร", "", "เรียงตามบทที่ปรากฏครั้งแรก ชื่อเดียวกันอาจมีฉายาหรือคำเรียกอื่นในเนื้อเรื่อง ชื่อที่ซ้ำกันแต่บทแรกต่างกันเป็นคนละคน", ""]
    body = "".join(f"<tr><td>{esc(n)}</td><td>{esc(z)}</td><td>{ch}</td></tr>" for ch, n, z in rows)
    return out, f"<table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>บทแรก</th></tr>{body}</table>", len(rows)


# ทำเนียบเทพบท 099–100: เทพที่ต้นฉบับแต่งตั้งในร้อยแก้ว (ไม่มีบรรทัด 姓諱名) ระบุ (ย, ตำแหน่งจีนตามแถว GLOSSARY, ชื่อจีน)
# ตำแหน่งไทยดึงจาก GLOSSARY และชื่อไทยดึงจาก CHARACTERS/GLOSSARY ตามรูปจีน
GOD_DECREES = [
    (9, "三界首領八部三百六十五位清福正神", ["柏鑑"]),
    (9, "管領三山正神炳靈公", ["黃天化"]),
    (9, "東岳泰山天齊仁聖大帝", ["黃飛虎"]),
    (9, "南岳衡山司天昭聖大帝", ["崇黑虎"]),
    (9, "中岳嵩山中天崇聖大帝", ["聞聘"]),
    (9, "北岳恆山安天玄聖大帝", ["崔英"]),
    (9, "西岳華山金天順聖大帝", ["蔣雄"]),
    (10, "九天應元雷聲普化天尊", ["聞仲"]),
    (22, "南方三氣火德星君", ["羅宣"]),
    (27, "主掌瘟㾮昊天大帝", ["呂岳"]),
    (35, "坎宮斗母正神", ["金靈聖母"]),
    (187, "執年歲君太歲之神", ["殷郊"]),
    (187, "甲子太歲之神", ["楊任"]),
    (197, "金龍如意正一龍虎玄壇真君", ["趙公明"]),
    (201, "增長天王", ["魔禮青"]),
    (202, "廣目天王", ["魔禮紅"]),
    (203, "多文天王", ["魔禮海"]),
    (204, "持國天王", ["魔禮壽"]),
    (205, "哼哈二將之神", ["鄭倫", "陳奇"]),
    (205, "主痘碧霞元君", ["余化龍"]),
    (205, "衛房聖母元君", ["金氏"]),
    (211, "感應隨世仙姑正神", ["雲霄", "瓊霄", "碧霄"]),
    (213, "分水將軍", ["申公豹"]),
]
# แต่งตั้งเพิ่มหลังบท 099: (บท, ย, ตำแหน่งจีน, ชื่อจีน)
GOD_DECREES_LATER = [(100, 4, "冰消瓦解之神", ["飛廉", "惡來"])]
# หมวดของทำเนียบ (ผู้ใช้กำหนด 2026-11-09): (ชื่อหมวด, (บท, ยแรก)) แต่ละรายการอยู่หมวดสุดท้ายที่ยแรก <= ตำแหน่งของตน
# None = หมวดที่กำหนดด้วยตำแหน่งเท่านั้น (GOD_GROUP_BY_TITLE) เพราะต้นฉบับประกาศปนในย่อหน้าเดียวกับหมวดอื่น
GOD_GROUPS = [
    ("ผู้นำเทพและเทพแห่งภูเขา", (99, 9)),
    ("หมวดสายฟ้า — ประมุขและบริวาร 24 องค์", (99, 10)),
    ("หมวดไฟ — ประมุขและบริวาร 5 องค์", (99, 20)),
    ("หมวดโรคระบาด — ประมุขและบริวาร 6 องค์", (99, 27)),
    ("ประมุขหมวดดาวกระบวยและมหาจักรพรรดิจื่อเวย", (99, 35)),
    ("เทพดาวกระบวยทั้งห้าทิศ", (99, 36)),
    ("เทพประจำดาวต่าง ๆ", (99, 53)),
    ("กลุ่มดาวนักษัตร — รายชื่อ 20 องค์ที่ลงไว้ในหมวดดาวกระบวย", (99, 112)),
    ("ดาวเทียนกัง 36 องค์", (99, 123)),
    ("ดาวตี้ซ่า 72 องค์", (99, 142)),
    ("เทพดาวนพเคราะห์ 9 องค์", (99, 179)),
    ("หมวดน้ำ — ประมุขและบริวาร 4 องค์", (99, 183)),
    ("หมวดไท่ซุ่ยและเทพเข้าเวร", (99, 187)),
    ("จอมทัพใหญ่สี่อริยะ", (99, 194)),
    ("เสวียนถานเจินจวินและเทพบริวารด้านโชคลาภ", (99, 197)),
    ("ราชาสวรรค์ทั้งสี่", (99, 200)),
    ("สองขุนพลเฮิงฮา", None),
    ("เทพฝีดาษและเทพร่วมตระกูล", (99, 205)),
    ("เซียนกูทั้งสาม", (99, 210)),
    ("แม่ทัพแบ่งน้ำ", (99, 213)),
    ("แต่งตั้งเพิ่มเติมในบทที่ 100", (100, 1)),
]
# ท้ายทำเนียบ (ผู้ใช้สั่ง 2026-11-09) ผู้ที่ไม่ได้รับแต่งตั้งบนแท่น ไม่นับรวมจำนวนเทพที่แต่งตั้ง:
# (ชื่อหมวด, ตำแหน่งจีน, ตำแหน่งไทย หรือ None = ดึงจาก GLOSSARY, ชื่อจีน)
GOD_EXTRA = [
    # 100 ย11 後來李靖、金吒、木吒、哪吒、楊戩、韋護、雷震子，此七人俱是肉身成聖
    ("ผู้ศักดิ์สิทธิ์ทั้งร่างเนื้อทั้งเจ็ด", "肉身成聖", None, ["李靖", "金吒", "木吒", "哪吒", "楊戩", "韋護", "雷震子"]),
    # 100 ย17 封營丘，為齊侯 (คำแปล: เป็นเจ้าแคว้นฉี)
    ("จื่อหยา", "齊侯", "เจ้าแคว้นฉี", ["姜子牙"]),
]
# 中天北極紫微大帝 (099 ย44) อยู่กลางรายชื่อดาวกระบวยห้าทิศ แต่จัดคู่กับประมุขหมวดดาวกระบวย
GOD_GROUP_BY_TITLE = {"中天北極紫微大帝": "ประมุขหมวดดาวกระบวยและมหาจักรพรรดิจื่อเวย",
                      "哼哈二將之神": "สองขุนพลเฮิงฮา"}
# 099 ย19 ตำแหน่งที่ต้นฉบับบอกตัวบุคคลในวงเล็บ (閃電神（即金光聖母）)
GOD_ALIASES = {"閃電神": "金光聖母", "助風神": "菡芝仙"}
# รูปจีนในบท 099 ที่ต่างจากแถวบุคคล (S636 聞聘 = 文聘) ใช้หาชื่อไทยเท่านั้น คงรูปจีนตามต้นฉบับ
GOD_NAME_VARIANTS = {"聞聘": "文聘", "姜子牙": "子牙"}
# บรรทัดรายชื่อที่ไม่มีตำแหน่งกำกับ และตำแหน่งประกาศไว้ในร้อยแก้วย่อหน้าก่อน (099 ย194 四聖)
GOD_PARA_TITLE = {195: "鎮守靈霄寶殿四聖大元帥", 196: "鎮守靈霄寶殿四聖大元帥"}


def form_pairs(path, kinds=None, col=0):
    """จับคู่รูปจีน–ไทยในแถวเอกสารกลาง (col = คอลัมน์จีน): จำนวนเท่ากันจับคู่ตามลำดับ ไม่เท่ากันจับเฉพาะรูปแรก"""
    pairs = {}
    for c in table_rows(path):
        if len(c) < col + 3 or (kinds and not any(c[col + 2].startswith(k) for k in kinds)):
            continue
        if col and not re.fullmatch(r"C\d+", c[0]):
            continue
        zf, tf = split_cell(c[col]), split_cell(c[col + 1])
        if not zf or not tf:
            continue
        for z, t in (zip(zf, tf) if len(zf) == len(tf) else [(zf[0], tf[0])]):
            pairs.setdefault(z, t)
    return pairs


def parse_god(z, t):
    """'尾火虎 朱諱晤' / 'เหว่ยหั่วหู่ นามจูอู้' -> (ตำแหน่งจีน, ตำแหน่งไทย, ชื่อจีน, ชื่อไทย)"""
    if " " not in z:
        return "", "", z.replace("諱", ""), t
    zt, _, zn = z.rpartition(" ")
    tt, _, tn = t.rpartition(" นาม") if " นาม" in t else t.partition(" ")
    if zn.startswith("諱"):  # 鄧天君 諱忠: แซ่อยู่ในตำแหน่ง
        zn, tn = zt[0] + zn, tt.replace("เทียนจวิน", "") + tn
    return zt, tt, zn.replace("諱", ""), tn


def appendix_gods(src, th):
    paras = [l for l in src["099"].splitlines()[1:] if l.strip()]
    th_paras = {int(m.group(1)): m.group(2).strip()
                for m in re.finditer(r"<!--\s*ย(\d+)\s*-->\n(.*?)(?=\n<!--|\Z)", th["099"], re.S)}
    headers = [i for i, p in enumerate(paras, 1) if "名諱" in p and p.rstrip().endswith("：")]
    titles = form_pairs("GLOSSARY.md", ("ตำแหน่งเทพ", "วลี"))
    # ชื่อไทยของบุคคล: CHARACTERS ก่อน แล้วจึงแถวบุคคลและตำแหน่งเทพใน GLOSSARY (เช่น 金氏 นางจิน)
    names = {**form_pairs("GLOSSARY.md", ("บุคคล", "ผู้บำเพ็ญ", "ตำแหน่งเทพ")),
             **form_pairs("CHARACTERS.md", col=1)}
    entries = []
    for ch, y, zt, zns in [(99, *d) for d in GOD_DECREES] + GOD_DECREES_LATER:
        for zn in zns:
            entries.append(((ch, y), 0, zt, titles[zt], zn, names[GOD_NAME_VARIANTS.get(zn, zn)]))
    prev = None
    for c in table_rows("GLOSSARY.md"):
        if len(c) < 5 or not c[2].startswith("นามเทพที่แต่งตั้ง"):
            continue
        zf, tf = [x.strip() for x in c[0].split(" / ")], [x.strip() for x in c[1].split(" / ")]
        y = int(re.search(r"ย(\d+)", c[4]).group(1))
        for z, t in zip(zf, tf):
            zt, tt, zn, tn = parse_god(z, t)
            if zn in GOD_ALIASES:
                zt, tt, zn = zn, tn, GOD_ALIASES[zn]
                tn = names[zn]
            sec = max(h for h in headers if h <= y)
            if not zt and y in GOD_PARA_TITLE:
                zt = GOD_PARA_TITLE[y]
                tt = titles[zt]
            elif not zt and prev and prev[0] == sec:
                zt, tt = prev[1], prev[2]
            elif not zt:  # ใช้หัวรายชื่อ เช่น 隨斗部九曜星官名諱
                zt = paras[sec - 1].strip().split("名諱")[0]
                tt = re.sub(r"\s*\(.*?\)|:$", "", th_paras[sec]).removeprefix("นามของ").removeprefix("นาม").strip()
            if zt and y not in GOD_PARA_TITLE:
                prev = (sec, zt, tt)
            entries.append(((99, y), 1, zt, tt, zn, tn))
    entries = [e for _, e in sorted(enumerate(entries), key=lambda x: (x[1][0], x[1][1], x[0]))]
    groups = {label: [] for label, _ in GOD_GROUPS}
    for e in entries:
        label = GOD_GROUP_BY_TITLE.get(e[2]) or [lb for lb, start in GOD_GROUPS if start and start <= e[0]][-1]
        groups[label].append(e)
    out = ["# ทำเนียบเทพที่แต่งตั้ง", "",
           "นามเทพที่จื่อหยาแต่งตั้งบนแท่นแต่งตั้งเทพในบทที่ 99 และที่แต่งตั้งเพิ่มในบทที่ 100 "
           "จัดตามหมวด ภายในหมวดเรียงตามลำดับที่ประกาศในบท "
           "ชื่อบุคคลเขียนแซ่ต่อด้วยนาม ตำแหน่งใช้ตามคำแปลบทที่ 99–100 "
           "ผู้ที่มีบทบาทในเนื้อเรื่องดูบทที่ปรากฏครั้งแรกได้ใน “รายชื่อตัวละคร”", "",
           "ชื่อที่ต้นฉบับแต่งตั้งไว้สองตำแหน่งนับเป็นสองรายการ ได้แก่ โจวซิ่น (周信) เฉินเกิง (陳庚) "
           "ซุนเป่า (孫寶) และหวังหู่ (王虎) ต้นฉบับไม่ได้ระบุว่าเป็นคนเดียวกันหรือคนละคนที่ชื่อซ้ำกัน", "",
           "ท้ายทำเนียบรวมผู้ที่ไม่ได้รับแต่งตั้งบนแท่นไว้ด้วย ได้แก่ ผู้สำเร็จเป็นผู้ศักดิ์สิทธิ์ทั้งร่างเนื้อทั้งเจ็ด "
           "ตามที่ผู้เล่ากล่าวในบทที่ 100 และจื่อหยาผู้ประกอบพิธีแต่งตั้งเทพ ซึ่งได้เป็นเจ้าแคว้นฉี "
           "สองหมวดนี้ไม่นับรวมในจำนวนเทพที่แต่งตั้ง", ""]
    total = len(entries)
    for lb, zt, tt, zns in GOD_EXTRA:
        groups[lb] = [(None, 0, zt, tt or titles[zt], zn, names[GOD_NAME_VARIANTS.get(zn, zn)]) for zn in zns]
    summary = "".join(f"<tr><td>{esc(lb)}</td><td>{len(es)}</td></tr>" for lb, es in groups.items()
                      if lb not in dict((x[0], 1) for x in GOD_EXTRA))
    extra = "".join(f"<tr><td>{esc(lb)} (ไม่ได้แต่งตั้งบนแท่น)</td><td>{len(groups[lb])}</td></tr>" for lb, *_ in GOD_EXTRA)
    body = (f"<table><tr><th>หมวด</th><th>จำนวนรายการ</th></tr>{summary}"
            f"<tr><td><strong>รวมเทพที่แต่งตั้ง</strong></td><td><strong>{total}</strong></td></tr>{extra}</table>")
    for lb, es in groups.items():
        rows = "".join(f"<tr><td>{esc(tn)}</td><td>{esc(zn)}</td><td>{esc(tt)}</td><td>{esc(zt)}</td></tr>"
                       for _, _, zt, tt, zn, tn in es)
        col = ("สถานะ", "สถานะ (จีน)") if lb in dict((x[0], 1) for x in GOD_EXTRA) else ("ตำแหน่งเทพ", "ตำแหน่ง (จีน)")
        body += (f"<h2>{esc(lb)}</h2><table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>{col[0]}</th>"
                 f"<th>{col[1]}</th></tr>{rows}</table>")
    return out, body, total


def item_type(cell):
    for t in ITEM_TYPES:
        if cell.startswith(t):
            return t
    for prefix, t in TYPE_MAP.items():
        if cell.startswith(prefix):
            return t
    return None


# ชื่อย่อในช่องเจ้าของของ WORLD.md -> ชื่อหลักใน CHARACTERS.md
OWNER_SHORT = {"จื่อหยา": "เจียงจื่อหยา", "เจียงซ่าง": "เจียงจื่อหยา", "ไท่ซือเหวิน": "เหวินจ้ง", "เหวินหวัง": "จีชาง",
               "อู่หวัง": "จีฟา", "หยวนสื่อ": "หยวนสื่อเทียนจุน", "ทงเทียน": "ทงเทียนเจี้ยวจู่",
               "หรานเติง": "หรานเติงเต้าเหริน", "ไท่อี่": "ไท่อี่เจินเหริน", "เหวินซู": "เหวินซูกว่งฝ่าเทียนจุน",
               "เต้าเต๋อเจินจวิน": "ชิงซวีเต้าเต๋อเจินจวิน", "ผู่เสียน": "ผู่เสียนเจินเหริน", "ฉือหาง": "ฉือหางเต้าเหริน",
               "เจียอิ่น": "เจียอิ่นเต้าเหริน", "จุ่นถี": "จุ่นถีเต้าเหริน", "หงจวิน": "หงจวินเต้าเหริน",
               "หยุนเซียว": "เจ้าแม่หยุนเซียว", "ฉฺยงเซียว": "เจ้าแม่ฉฺยงเซียว", "ปี้เซียว": "เจ้าแม่ปี้เซียว"}
# เจ้าของที่กำหนดเอง (ชื่อจีนของรายการ -> ข้อความ) ใช้แทนผลที่ดึงจากเอกสารกลาง เมื่อช่องเจ้าของรวมผู้ที่ไม่ใช่เจ้าของ
# (ผู้บัญชาการ อาจารย์ ผู้ถูกกระทำ) แถวหลายรายการจับคู่ตามลำดับไม่ได้ หรือเอกสารกลางไม่ได้ระบุแต่ต้นฉบับบอกชัด (หลักฐานท้ายบรรทัด)
OWNER_OVERRIDE = {
    "如意": "—", "白光": "—",  # ใช้ทั่วไป ไม่ใช่ของชิ้นเดียว
    "封神榜": "หยวนสื่อเทียนจุน, เจียงจื่อหยา",
    "封神臺": "หยวนสื่อเทียนจุน, เจียงจื่อหยา, ไป่เจี้ยน",
    "竅中二氣": "เจิ้งหลุน", "黃氣": "เฉินฉี",
    "火眼金睛獸": "ฉงเฮยหู่, เจิ้งหลุน, อวี๋ฮว่า", "金睛獸": "ฉงเฮยหู่, เจิ้งหลุน",
    "三昧真火": "เหนอจา, เจียงจื่อหยา, หยางเจี่ยน", "扁拐": "จินจา",
    "神火罩": "ไท่อี่เจินเหริน, เหนอจา", "風火輪": "ไท่อี่เจินเหริน, เหนอจา",  # WORLD 風火二輪 บท 014
    "紫焰蛇矛": "เหนอจา",  # GLOSSARY: หมายถึงทวนปลายเพลิง
    "八卦帕": "เจ้าแม่สือจี",  # 013 石磯娘娘將八卦龍鬚帕丟起
    "醒酒氈": "วงศ์จี, ป๋ออี้เข่า, โจ้วหวัง", "七香車": "วงศ์จี, ป๋ออี้เข่า, โจ้วหวัง",
    "紅杏": "เหลยเจิ้นจื่อ", "仙杏": "เหลยเจิ้นจื่อ",
    "十絕陣": "เทียนจวินทั้งสิบแห่งเกาะจินเอ๋า", "方天戟": "อวี๋ฮว่า",
    "紅水陣": "หวังเทียนจวิน", "風吼陣": "ต่งเทียนจวิน", "化血陣": "ซุนเทียนจวิน", "烈焰陣": "ไป๋เทียนจวิน",
    "擒仙玄妙索": "ฉินหวาน", "四楞黃金鐧": "ฉินหวาน",  # 045 ผู้ขี่กวางลายเหลือง
    "畫桿戟": "ต่งเทียนจวิน",  # 046 บทสรรเสริญต่งเทียนจวิน
    "寶錄": "หรานเติงเต้าเหริน",  # 045 腰懸寶錄…號燃燈
    "八卦紫壽仙衣": "ชื่อจิงจื่อ",  # 048 赤精子…將八卦紫壽仙衣明現其身
    "慧眼": "หรานเติงเต้าเหริน",  # 047 燃燈借慧眼
    "九轉煉元功": "หยางเจี่ยน", "元功變化": "หยางเจี่ยน", "八九變化": "หยางเจี่ยน",  # 040, 058, 092
    "虎頭鎗": "หมอหลี่ชิง",  # 040 魔禮青虎頭鎗
    "狼牙棒": "เฟิงหลิน", "青鬃馬": "เฟิงหลิน",  # 036–037 風林 縱青鬃馬，使兩根狼牙棒
    "安邦臼杵鎗": "จางกุ้ยฟาง", "四面鐧": "จางกุ้ยฟาง",  # 036 บทสรรเสริญจางกุ้ยฟาง
    "青罰馬": "เจียงจื่อหยา", "白額虎": "เซินกงเป้า", "赤兔馬": "หม่าเฉิงหลง",
    "金鞭": "เหวินจ้ง",  # GLOSSARY 金鞭 (ของเหวินจ้ง)
    "黃河陣": "เจ้าแม่ทั้งสาม", "混元金斗": "เจ้าแม่ทั้งสามแห่งเกาะซานเซียน, เจ้าแม่ปี้เซียว",
    "金霞冠": "หั่วหลิงเซิ่งหมู่", "掃霞衣": "กว่งเฉิงจื่อ",
    "神手": "หม่าหยวน",
    "鸞飛劍": "เจ้าหญิงหลงจี๋", "五點桃花駒": "เจียงจื่อหยา, เจ้าหญิงหลงจี๋", "內旗門": "หงจิ่น",
    "替身法": "หูเหลย", "乾坤針": "เจ้าหญิงหลงจี๋",
    "聚仙": "พระแม่ทองแห่งสระหยก", "雲界": "พระแม่ทองแห่งสระหยก", "焰光旗": "เหล่าจื่อ",
    "七珍妙樹": "จุ่นถีเต้าเหริน",
    "掌心雷": "ตัวเป่าเต้าเหริน, ทงเทียนเจี้ยวจู่",  # 076 多寶道人…發一聲掌心雷; 077
    "紙車兒": "หานเซิง, หานเปี้ยน", "風車兒": "หานเซิง, หานเปี้ยน",
    "法像": "เหวินซูกว่งฝ่าเทียนจุน, ผู่เสียนเจินเหริน, ฉือหางเต้าเหริน",
    "白光劍": "เจ้าหญิงหลงจี๋", "四象塔": "จินหลิงเซิ่งหมู่", "龍虎如意": "จินหลิงเซิ่งหมู่",  # 083
    "飛金劍": "จินกวงเซิ่งหมู่, จินหลิงเซิ่งหมู่",  # 046; 083 聖母綽步，提飛金劍
    "青毛獅子": "ฉิวโส่วเซียน (ร่างเดิม), เหวินซูกว่งฝ่าเทียนจุน (พาหนะ)",  # 083–084 文殊騎了青獅
    "青獅": "ฉิวโส่วเซียน (ร่างเดิม), เหวินซูกว่งฝ่าเทียนจุน (พาหนะ)",
    "白象": "หลิงหยาเซียน (ร่างเดิม), ผู่เสียนเจินเหริน (พาหนะ)",  # 084 普賢真人騎白象
    "金毛犼": "จินกวงเซียน (ร่างเดิม), ฉือหางเต้าเหริน (พาหนะ)",  # 084 慈航道人騎金毛犼
    "五岳": "หวงเฟยหู่, เหวินพิ่น, ชุยอิง, เจี่ยงสฺยง, ฉงเฮยหู่",
    "雙刀": "เติ้งฉานอวี้, ต๋าจี่", "繡鸞刀": "สนมหวัง",  # 053; 096 妲己用雙刀…王貴人用一口繡鸞刀
    "桃花馬": "เกาหลานอิง, ต๋าจี่, หูสี่เม่ย, สนมหวัง",  # 086; 096 俱乘桃花馬
    "斬將劍": "โจ้วหวัง",
    # ไล่ตรวจรายการที่เคยว่างกับต้นฉบับบทแรกที่ปรากฏ (ย่อหน้าที่ใช้ของนั้น)
    "金葫蘆": "หนี่ว์วา",  # 001 喚彩雲童兒把後宮中金葫蘆取來
    "畫杆戟": "ซูเฉวียนจง",  # 002 小將…畫杆戟 (บุตรซูฮู่)
    "火龍鎗": "ซูฮู่",  # 002 看蘇護…青驄馬，火龍鎗
    "湛金斧": "ฉงเฮยหู่",  # 003 用兩柄湛金斧。此人乃崇侯虎兄弟崇黑虎
    "豹尾鞭": "ซูฮู่", "鐵鞭": "ซูฮู่",  # 004 蘇護…將一根豹尾鞭; 乃手提鐵鞭
    "畫戟": "เอ๋าปิ่ง",  # 012 三太子叫做敖丙，持畫戟刺我
    "太阿劍": "เจ้าแม่สือจี",  # 013 石磯娘娘…手提太阿劍
    "靈符秘訣": "ไท่อี่เจินเหริน, เหนอจา",  # 014 另授靈符秘訣
    "六陳鞭": "หลี่จิ้ง",  # 014 李靖…提六陳鞭
    "仙天真氣": "ชิงซวีเต้าเต๋อเจินจวิน",  # 018 真人用仙天真氣吹在楊任面上
    "借水遁": "เจียงจื่อหยา",  # 018 子牙借水遁去了
    "鋼鞭": "ฉงอิ้งเปียว",  # 028 崇應彪粧束…虎尾鋼鞭
    "先天一氣": "ชิงซวีเต้าเต๋อเจินจวิน",  # 031 真君…倒出神砂…法去先天一氣
    "鋼鎗": "หวงเฟยหู่",  # 033 武成王展放鋼鎗
    "移山倒海": "เจียงจื่อหยา", "撒豆成兵": "เจียงจื่อหยา",  # 036 บทสรรเสริญจื่อหยา
    "五雷": "เจียงจื่อหยา",  # 037 子牙…把手一放，五雷響亮
    "九轉煉就元功": "หยางเจี่ยน",  # 040
    "五遁": "เหวินจ้ง", "三除五遁": "เหวินจ้ง",  # 041 聞太師自忖：「五遁之中…」; 042 บทสรรเสริญ
    "兩翅玄功": "หยุนจงจื่อ, เหลยเจิ้นจื่อ",  # 043 將雷震子請至…傳你兩翅玄功
    "黑旛": "ต่งเทียนจวิน",  # 046 董天君…將黑旛搖動
    "五遁三除": "เจ้ากงหมิง",  # 047 บทสรรเสริญผู้ขี่เสือดำ
    "箭書": "ลู่ยา, เจียงจื่อหยา", "桑枝弓": "ลู่ยา, เจียงจื่อหยา", "桃枝箭": "ลู่ยา, เจียงจื่อหยา",  # 048–049
    "縮地": "ถู่สิงซุน",  # 054 กวีหัวบท 土行孫立功顯耀
    "五形遁": "หลี่ว์เยว่",  # 058 呂岳…命四門人…借五形遁進西岐城
    "琉璃燈": "หยวนสื่อเทียนจุน",  # 063 (麒麟崖 วังอวี้ซวี) 老爺面前琉璃燈
    "紅砂馬": "เวินเหลียง", "點鋼槍": "หม่าซ่าน", "白龍馬": "หม่าซ่าน",  # 063 藍臉的…姓溫，名良；那白臉的姓馬，名善
    "杏黃戊己旗": "หยวนสื่อเทียนจุน, เจียงจื่อหยา, หรานเติงเต้าเหริน",  # ตาม 杏黃旗; 065 燃燈…中央用杏黃戊己旗
    "皂旛": "หงจิ่น",  # 066 洪錦依然去把皂旛如前用度
    "胭脂馬": "เติ้งจิ่วกง", "白龍駒": "ไป่เสี่ยนจง",  # 066 บทสรรเสริญ 鄧九公 (大紅袍 大刀) กับ 柏顯忠 (粉素征袍 長鎗)
    "魚腸": "จุ่นถีเต้าเหริน", "二六蓮臺": "จุ่นถีเต้าเหริน",  # 070 กวี 寶杵魚腸; 082 準提…二六蓮臺
    "托天叉": "เหวินพิ่น",  # 070 文聘使發托天叉
    "白氣": "ชิวอิ่น",  # 074 丘引依舊把頭上白氣昇出
    "天馬": "อวี้ชิงเต้าเหริน", "地吼": "ไท่ชิงเต้าเหริน",  # 077 騎天馬…吾乃玉清道人; 騎地吼…吾乃太清道人
    "靈符": "เปี้ยนจี๋",  # 085 卞吉忙畫了三道靈符
    "抓絨繩": "เจี่ยงสฺยง", "五爪抓": "เจี่ยงสฺยง", "八楞鎚": "ชุยอิง",  # 086 崔英八楞鎚; 蔣雄的抓絨繩
    "鐵棒": "หยวนหง",  # 090 袁洪…白猿使鐵棒
    "五雷之法": "หยางเจี่ยน",  # 090 楊戩，你可引戰，用五雷之法
    "虎眼鞭": "เจียงเหวินฮ่วน",  # 093 บทสรรเสริญ 姜文煥
    # บท 099 แต่งตั้งสี่ขุนพลตระกูลหมอ: 魔禮青掌青光寶劍 魔禮紅掌碧玉琵瑟 魔禮壽掌紫金龍花狐貂
    "青光寶劍": "หมอหลี่ชิง", "碧玉琵瑟": "หมอหลี่หง", "紫金龍花狐貂": "หมอหลี่โซ่ว",
}


def owner_names():
    names = dict((k, v) for k, v in OWNER_SHORT.items())
    for c in table_rows("CHARACTERS.md"):
        if re.fullmatch(r"C\d+", c[0]):
            forms = split_cell(c[2])
            for t in forms:
                if len(t) >= 3:
                    names.setdefault(t, forms[0] if c[0] in ALIAS_ROWS else t)
    return sorted(names.items(), key=lambda x: -len(x[0]))


def owner_text(cell, names, fallback=True):
    """ชื่อบุคคลในช่องเจ้าของตามลำดับที่เขียน ตัดคำอธิบายในวงเล็บและสังกัด (ศิษย์…) ถ้าไม่มีชื่อบุคคลใช้ข้อความสั้นเดิม"""
    out = []
    for seg in re.split(r"[;,/]", re.sub(r"\s*\(.*?\)", "", cell)):
        seg = re.sub(r"\s*ศิษย์.*", "", seg).strip()
        found, taken = [], [False] * len(seg)
        for form, name in names:
            for m in re.finditer(re.escape(form), seg):
                if not any(taken[m.start():m.end()]):
                    taken[m.start():m.end()] = [True] * len(form)
                    found.append((m.start(), name))
        if found:
            out += [n for _, n in sorted(found)]
        elif fallback and seg and seg not in ("—", "-") and len(seg) <= 40:
            out.append(seg)
    return out


def item_owners():
    """ชื่อจีน -> เจ้าของ/ผู้ใช้ เรียงตามบท จากช่องเจ้าของ/ผู้สังกัดของ WORLD.md"""
    names, owners = owner_names(), {}
    for c in table_rows("WORLD.md"):
        if len(c) < 8 or c[3] in ("—", "เจ้าของ", "เจ้าของ/ผู้สังกัด"):
            continue
        forms = [re.sub(r"\s*\(.*?\)", "", x).split() for x in c[0].split(" / ")]
        parts = [x.strip() for x in c[3].split(" / ")]
        refs = ref_chapters(c[6])
        for i, zs in enumerate(forms):
            cell = parts[i] if len(forms) > 1 and len(parts) == len(forms) else c[3]
            for z in zs:
                owners.setdefault(z, []).append((refs[0] if refs else 999, cell))
    result = {}
    for z, cells in owners.items():
        seen = []
        for _, cell in sorted(cells, key=lambda x: x[0]):
            seen += [n for n in owner_text(cell, names) if n not in seen]
        result[z] = seen
    # รายการที่ WORLD.md ไม่มีเจ้าของ ใช้ชื่อบุคคลในวงเล็บของช่องประเภทใน GLOSSARY.md เช่น "อาวุธ (ถู่สิงซุน)"
    # หรือคำว่า "ของ…" ในช่องประเภท (เช่น "พาหนะของเหล่าจื่อ") และในหมายเหตุที่ขึ้นต้นด้วย "ของ" (เช่น "; ของหมอหลี่หง")
    for c in table_rows("GLOSSARY.md"):
        if len(c) < 3:
            continue
        m = re.search(r"\((.*)\)", c[2])
        own = [x for x in re.split(r";\s*", c[-1]) if x.startswith("ของ")]
        kind = c[2].replace("ของวิเศษ", "")
        text = m.group(1) if m else (kind.split("ของ", 1)[1] if "ของ" in kind else (own[0] if own else ""))
        if not text:
            continue
        forms, parts = split_cell(c[0]), text.split(" / ")
        for i, z in enumerate(forms):
            part = parts[i] if len(parts) == len(forms) > 1 else text
            found = owner_text(part.replace("(", " ").replace(")", " "), names, fallback=False)
            if found and not result.get(z):
                result[z] = found
    return result


def appendix_items(src, th):
    rows, seen = [], set()
    for c in table_rows("GLOSSARY.md"):
        if len(c) < 3:
            continue
        zh_forms, th_forms = split_cell(c[0]), split_cell(c[1])
        kind = ITEM_ZH.get(zh_forms[0]) if zh_forms else None
        kind = kind or item_type(c[2])
        # แถวที่รวมคนกับของ (เช่น 火靈聖母 / 金霞冠 ประเภท "ผู้บำเพ็ญ / ของวิเศษ") แยกประเภทตามลำดับรูป
        part_kinds = [item_type(p.strip()) for p in c[2].split(" / ")]
        if not kind and not any(part_kinds):
            continue
        if len(zh_forms) != len(th_forms):
            zh_forms, th_forms = zh_forms[:1], th_forms[:1]
        if kind or len(part_kinds) != len(zh_forms):
            kinds = [kind or next(k for k in part_kinds if k)] * len(zh_forms)
        else:
            kinds = part_kinds
        for z, t, kind in zip(zh_forms, th_forms, kinds):
            if not kind or "…" in t or z in seen or not re.fullmatch(r"[㐀-鿿豈-﫿]{2,}", z):
                continue
            refs = ref_chapters(c[4]) if len(c) > 4 else []
            # แถวรายการเดียวที่มีตำแหน่งอ้างอิง ใช้บทแรกตามเอกสารกลาง (เช่น 金箍 ของหม่าซุ่ย 082 ไม่ใช่ห่วงคาดหัวใน 074)
            ch = refs[0] if refs and len(zh_forms) == 1 else first_chapter(z, t, src, th, refs)
            if ch:
                seen.add(z)
                rows.append((ch, t, z, kind))
    rows.sort()
    owners = item_owners()
    out = ["# ดัชนีของวิเศษ ค่ายกล และวิชา", "",
           "เรียงตามบทที่ปรากฏครั้งแรก คุณสมบัติของแต่ละรายการให้อ่านจากเนื้อเรื่องและเชิงอรรถ "
           "ช่องเจ้าของ/ผู้ใช้เรียงตามลำดับที่ปรากฏในเรื่อง รายการที่ต้นฉบับไม่ได้ระบุเจ้าของหรือเป็นวิชาทั่วไปเว้นเป็น —", ""]
    body = "".join(f"<tr><td>{esc(t)}</td><td>{esc(z)}</td><td>{esc(k)}</td>"
                   f"<td>{esc(OWNER_OVERRIDE.get(z) or ', '.join(owners.get(z, [])) or '—')}</td><td>{ch}</td></tr>"
                   for ch, t, z, k in rows)
    return out, (f"<table><tr><th>ชื่อไทย</th><th>ชื่อจีน</th><th>ประเภท</th><th>เจ้าของ/ผู้ใช้</th><th>บทแรก</th></tr>"
                 f"{body}</table>"), len(rows)


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
    for slug, fn in (("zz-characters", appendix_characters), ("zz-gods", appendix_gods), ("zz-items", appendix_items)):
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
            manifest.append(f'<item id="s-{slug}" href="{slug}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="s-{slug}"/>')
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
