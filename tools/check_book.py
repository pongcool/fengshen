"""ตรวจความสม่ำเสมอทั้งเล่ม (PLAN.md ระยะ 3) รวมการตรวจที่ใช้ใน reviews/BOOKCHECK.md

ใช้: python -X utf8 tools/check_book.py            (ทุกการตรวจ)
     python -X utf8 tools/check_book.py names      (เฉพาะชื่อ)
     python -X utf8 tools/check_book.py tones      (เฉพาะรูปแปรวรรณยุกต์)
     python -X utf8 tools/check_book.py formulas   (เฉพาะสูตรเกริ่นกวี)

1. names: แถว GLOSSARY ประเภทชื่อเฉพาะ (บุคคล สถานที่ ของวิเศษ ฯลฯ) ที่คำจีนอยู่ในต้นฉบับบทหนึ่ง
   แต่คำแปลบทนั้นไม่มีรูปไทยกลาง เรียงตามจำนวนบทที่ตรงรูปมากไปน้อย (คำที่ตรงเกือบทุกบทแต่หลุดไม่กี่บท
   มักเป็นข้อผิดจริง ส่วนคำจีนสั้นที่ซ้อนในคำอื่นมักเป็นผลเกิน)
2. tones: คำในคำแปลที่ต่างจากชื่อไทยที่ลงทะเบียน (GLOSSARY ช่องไทย, CHARACTERS ชื่อหลัก)
   เฉพาะวรรณยุกต์หรือไม้ไต่คู้ และไม่ใช่ชื่อที่ลงทะเบียนอื่น
3. formulas: เทียบจำนวน 有詩為證，詩曰 (รูปรวม “มีบทกวีกล่าวเป็นพยานไว้ว่า”) และ 有詩為證 เดี่ยว
   (“มีบทกวีเป็นพยานว่า”) ระหว่างต้นฉบับกับคำแปลรายบท (D021)
ผลทั้งหมดเป็นรายการให้คนตรวจ ไม่ใช่การยืนยันว่าผิด
"""
import collections
import re
import sys

from check_terms import split_forms
from term_stats import ROOT

CJK = r"[㐀-䶿一-鿿豈-﫿]"
NAME_TYPES = {"บุคคล", "นามเทพที่แต่งตั้ง (บท 099)", "สถานที่", "ผู้บำเพ็ญ", "ของวิเศษ", "ภูเขา",
              "ค่ายกล", "บุคคลในตำนาน", "พาหนะ", "อาวุธ", "วิชา", "สิ่งก่อสร้าง"}
TONES = "่้๊๋็"


def load():
    src = {p.name[:3]: p.read_text(encoding="utf-8") for p in (ROOT / "chapters").glob("[0-9]*.md")}
    th = {p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "translations" / "th").glob("[0-9]*.md")}
    return src, th


def glossary_rows():
    for line in (ROOT / "GLOSSARY.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| จีน"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3:
            yield cells


def check_names(src, th):
    pairs = []
    for cells in glossary_rows():
        if cells[2] not in NAME_TYPES:
            continue
        zh, ths = split_forms(cells[0]), split_forms(cells[1])
        mapping = list(zip(zh, [[t] for t in ths])) if len(zh) == len(ths) else [(z, ths) for z in zh]
        for z, t in mapping:
            if re.fullmatch(CJK + "{2,}", z) and t and all("…" not in x for x in t):
                pairs.append((z, t))
    hit = collections.Counter()
    miss = collections.defaultdict(list)
    for z, t in pairs:
        for n in sorted(src):
            if z in src[n] and n in th:
                if any(x in th[n] for x in t):
                    hit[z] += 1
                else:
                    miss[(z, "/".join(t))].append(n)
    print(f"== names: {len(miss)} รายการที่มีบทไม่ตรงรูปไทยกลาง")
    for (z, t), ns in sorted(miss.items(), key=lambda kv: (-hit[kv[0][0]], kv[0][0])):
        print(f"  {z} → {t}\tตรง {hit[z]} บท\tไม่พบใน {' '.join(ns)}")


def registered_names():
    names = set()

    def add(cell):
        for part in re.sub(r"\(.*?\)", "", cell).split("/"):
            p = part.strip()
            if re.fullmatch(r"[฀-๿]{4,}", p):
                names.add(p)

    for line in (ROOT / "CHARACTERS.md").read_text(encoding="utf-8").splitlines():
        if re.match(r"\| C\d", line):
            add(line.split("|")[3])
    for cells in glossary_rows():
        add(cells[1])
    return names


def check_tones(th):
    names = registered_names()
    res = collections.defaultdict(collections.Counter)
    for n in sorted(names):
        base = "".join(ch for ch in n if ch not in TONES)
        if len(base) < 4:
            continue
        rx = re.compile("".join(re.escape(ch) + f"[{TONES}]?" for ch in base))
        for k, t in th.items():
            for m in rx.finditer(t):
                s = m.group()
                if s != n and s not in names and not any(s in x for x in names if len(x) > len(s)):
                    res[(n, s)][k] += 1
    print(f"== tones: {len(res)} คู่รูปแปร (ส่วนใหญ่เป็นคำไทยทั่วไปที่บังเอิญคล้ายชื่อ)")
    for (n, s), c in sorted(res.items()):
        print(f"  {n} → {s}\t{sum(c.values())}\t{' '.join(sorted(c))}")


def check_formulas(src, th):
    merged_th, alone_th = "มีบทกวีกล่าวเป็นพยานไว้ว่า", "มีบทกวีเป็นพยานว่า"
    bad = []
    for n in sorted(src):
        if n not in th:
            continue
        total = len(re.findall("有詩為[證証]", src[n]))
        merged = len(re.findall("有詩為[證証][，。、：]?詩曰", src[n]))
        got = (th[n].count(merged_th), th[n].count(alone_th))
        if (merged, total - merged) != got:
            bad.append(f"  {n}: จีน รวม {merged} เดี่ยว {total - merged} / ไทย รวม {got[0]} เดี่ยว {got[1]}")
    print(f"== formulas: {len(bad)} บทที่จำนวนสูตรไม่ตรง (ดูบริบทก่อนแก้ เช่น 有請為證 ใน 001 ตาม S002)")
    print("\n".join(bad))


def main():
    which = set(sys.argv[1:]) or {"names", "tones", "formulas"}
    src, th = load()
    if "names" in which:
        check_names(src, th)
    if "tones" in which:
        check_tones(th)
    if "formulas" in which:
        check_formulas(src, th)


if __name__ == "__main__":
    main()
