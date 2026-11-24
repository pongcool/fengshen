"""ตรวจว่าคำแปลใช้รูปไทยตามศัพท์กลาง เมื่อต้นฉบับบทนั้นมีคำจีนที่ลงทะเบียนไว้

ใช้: python -X utf8 tools/check_terms.py 001 002
     python -X utf8 tools/check_terms.py --all
     python -X utf8 tools/check_terms.py --all --show-known   (แสดงรายการที่คัดแยกแล้วด้วย)
     python -X utf8 tools/check_terms.py --all --scoped       (แสดงคำที่มีเฉพาะแถวกำกับบริบทในบทที่แถวไม่ได้อ้าง)

ตรวจเฉพาะคำจีนยาวตั้งแต่ 2 ตัวอักษร ถ้าช่องจีนและช่องไทยมีหลายรูปคั่นด้วย “ / ” จำนวนเท่ากัน
จะจับคู่ตามลำดับ ไม่เช่นนั้นถือว่ารูปไทยใดก็ได้ในช่องนั้น
- แถวที่ช่องจีนมีวงเล็บกำกับบริบท เช่น “老爺 (หมายถึงหยวนสื่อ)” ใช้เฉพาะบทที่ช่องอ้างอิงของแถวระบุ
  ในบทอื่นรูปไทยของแถวนี้ไม่นับ; คำจีนที่มีเฉพาะแถวแบบนี้ ในบทอื่นแสดงด้วย --scoped (ใช้เกณฑ์ ADDRESS_TERMS แทน)
- คำจีนที่มีหลายแถวให้รูปไทยต่างกัน (เช่น 異人 = ผู้วิเศษ / อี้เหริน) ตรวจรายย่อหน้า: ทุกย่อหน้าที่มีคำจีน
  ต้องมีรูปไทยของแถวใดแถวหนึ่งในย่อหน้าเดียวกันของคำแปล; คำที่มีรูปเดียวตรวจระดับบท
- คำจีนที่อยู่ในคำยาวกว่าซึ่งลงทะเบียนไว้ (神鞭 ใน 打神鞭) ไม่นับ เฉพาะเมื่อคำยาวนั้นถูกตรวจในบทนี้และผ่าน
- คู่ (คำจีน, บท) ที่คัดแยกแล้วว่าไม่ใช่ข้อผิดอยู่ใน tools/check_terms_known.tsv (BOOKCHECK รอบ 3)
  ซ่อนไว้โดยค่าเริ่มต้น รายการที่เหลือคือสิ่งที่ยังต้องเปิดดู
ผลเป็นรายการให้คนตรวจ คำบางคำแปลตามบริบทได้ เช่น คำนามทั่วไปหรือสูตรที่รวมกับสูตรอื่นตาม D021
"""
import argparse
import re

from check_translation import source_paragraphs
from term_stats import ROOT

CJK = r"[㐀-䶿一-鿿豈-﫿]"
KNOWN = ROOT / "tools" / "check_terms_known.tsv"


def split_forms(cell):
    cell = re.sub(r"\(.*?\)", "", cell)
    return [f.strip() for f in cell.split(" / ") if f.strip()]


def glossary_rows():
    """คืน dict คำจีน → รายการแถว (รูปไทย, กำกับบริบทหรือไม่, เลขบทที่แถวอ้าง)"""
    rows = {}
    for line in (ROOT / "GLOSSARY.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| จีน"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        scoped = "(" in cells[0]
        cited = {int(n) for n in re.findall(r"(?<!\d)(\d{3})(?!\d)", cells[-2])}
        zh_forms = split_forms(cells[0])
        th_forms = split_forms(cells[1])
        if len(zh_forms) == len(th_forms):
            mapping = [(z, [t]) for z, t in zip(zh_forms, th_forms)]
        else:
            mapping = [(z, th_forms) for z in zh_forms]
        for zh, ths in mapping:
            if re.fullmatch(CJK + "{2,}", zh) and ths and all("…" not in t for t in ths):
                rows.setdefault(zh, []).append((tuple(ths), scoped, cited))
    return rows


def glossary_pairs():
    """คำจีนที่มีแถวไม่กำกับบริบท → รูปไทยของแถวเหล่านั้น (ใช้ใน check_book และที่อื่น)"""
    out = {}
    for zh, rs in glossary_rows().items():
        forms = [t for ths, scoped, _ in rs if not scoped for t in ths]
        if forms:
            out[zh] = list(dict.fromkeys(forms))
    return out


def th_paragraphs(text):
    parts = re.split(r"<!-- ย(\d+) -->", text)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def load_known():
    known = {}
    if KNOWN.exists():
        for line in KNOWN.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            zh, chapters, reason = (line.split("\t") + ["", ""])[:3]
            for c in chapters.split():
                known[(zh, int(c))] = reason
    return known


def mask(text, names):
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, "＊" * len(name))
    return text


def check_chapter(num, rows, scoped_only):
    """คืน (รายการที่ไม่พบรูปไทย, รายการคำที่มีเฉพาะแถวกำกับบริบทในบทที่แถวไม่อ้าง)"""
    source = next((ROOT / "chapters").glob(f"{num:03d}-*.md")).read_text(encoding="utf-8")
    text = (ROOT / "translations" / "th" / f"{num:03d}.md").read_text(encoding="utf-8")
    _, src_paras = source_paragraphs(num)
    th_paras = th_paragraphs(text)
    passed, missing, context = set(), [], []
    for zh in sorted((z for z in rows if z in source), key=len, reverse=True):
        usable = [ths for ths, scoped, cited in rows[zh] if not scoped or num in cited]
        longer = [n for n in passed if zh in n]
        if not usable:
            count = mask(source, longer).count(zh)
            if count and scoped_only:
                forms = [t for ths, _, _ in rows[zh] for t in ths]
                if not any(t in text for t in forms):
                    context.append((zh, forms, count, ""))
            continue
        forms = list(dict.fromkeys(t for ths in usable for t in ths))
        count = mask(source, longer).count(zh)
        if not count:
            continue
        if len(set(usable)) > 1 and th_paras:
            bad = [i for i, p in enumerate(src_paras, 1)
                   if zh in mask(p, longer) and not any(t in th_paras.get(i, "") for t in forms)]
            if bad:
                missing.append((zh, forms, count, " ".join(f"ย{i}" for i in bad)))
            else:
                passed.add(zh)
        elif any(t in text for t in forms):
            passed.add(zh)
        else:
            missing.append((zh, forms, count, ""))
    return sorted(missing), sorted(context)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("chapters", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--show-known", action="store_true")
    parser.add_argument("--scoped", action="store_true")
    args = parser.parse_args()
    th_dir = ROOT / "translations" / "th"
    if args.all:
        nums = [int(p.stem) for p in sorted(th_dir.glob("[0-9][0-9][0-9].md"))]
    else:
        nums = [int(c) for c in args.chapters]
    rows = glossary_rows()
    known = load_known()
    total_hidden = scoped_open = scoped_hidden = 0
    for num in nums:
        found, context = check_chapter(num, rows, args.scoped)
        shown = [m for m in found if (m[0], num) not in known]
        hidden = [m for m in found if (m[0], num) in known]
        total_hidden += len(hidden)
        print(f"== บท {num:03d}: ไม่พบรูปไทยตามศัพท์กลาง {len(shown)} รายการ (คัดแยกแล้ว {len(hidden)})")
        for zh, forms, count, where in shown:
            print(f"  {zh} ({count} ครั้ง{'; ' + where if where else ''}) → {' / '.join(forms)}")
        if args.show_known:
            for zh, forms, count, where in hidden:
                print(f"  [คัดแยกแล้ว: {known[(zh, num)]}] {zh} ({count} ครั้ง{'; ' + where if where else ''}) → {' / '.join(forms)}")
        scoped_hidden += sum((zh, num) in known for zh, *_ in context)
        scoped_open += sum((zh, num) not in known for zh, *_ in context)
        for zh, forms, count, _ in context:
            if (zh, num) in known and not args.show_known:
                continue
            tag = f"[บริบท; คัดแยกแล้ว: {known[(zh, num)]}]" if (zh, num) in known else "[บริบท]"
            print(f"  {tag} {zh} ({count} ครั้ง) → รูปของแถวกำกับบริบท: {' / '.join(forms)}")
    if len(nums) > 1:
        print(f"== รายการปกติ: รวมคัดแยกแล้ว {total_hidden} รายการ (ดู --show-known)")
        if args.scoped:
            print(f"== รายการบริบท (--scoped): ยังไม่คัด {scoped_open}, คัดแยกแล้ว {scoped_hidden}")


if __name__ == "__main__":
    main()
