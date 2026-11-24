"""ตรวจว่าคำแปลใช้รูปไทยตามศัพท์กลาง เมื่อต้นฉบับบทนั้นมีคำจีนที่ลงทะเบียนไว้

ใช้: python -X utf8 tools/check_terms.py 001 002
     python -X utf8 tools/check_terms.py --all
     python -X utf8 tools/check_terms.py --all --show-known   (แสดงรายการที่คัดแยกแล้วด้วย)

ตรวจเฉพาะคำจีนยาวตั้งแต่ 2 ตัวอักษร ถ้าช่องจีนและช่องไทยมีหลายรูปคั่นด้วย “ / ” จำนวนเท่ากัน
จะจับคู่ตามลำดับ ไม่เช่นนั้นถือว่ารูปไทยใดก็ได้ในช่องนั้น
- คำจีนเดียวกันที่มีหลายแถว ถือว่าผ่านถ้าพบรูปไทยของแถวใดแถวหนึ่ง
- แถวที่ช่องจีนมีวงเล็บกำกับบริบท เช่น “老爺 (หมายถึงหยวนสื่อ)” ใช้เฉพาะบริบทนั้น: รูปไทยของแถวนี้นับเป็นรูปที่ยอมรับ
  แต่คำจีนที่มีเฉพาะแถวแบบนี้ไม่นำมาตรวจ
- ไม่นับคำจีนที่อยู่ในคำจีนที่ลงทะเบียนยาวกว่า เช่น 神鞭 ใน 打神鞭
- คู่ (คำจีน, บท) ที่คัดแยกแล้วว่าไม่ใช่ข้อผิดอยู่ใน tools/check_terms_known.tsv (BOOKCHECK รอบ 3)
  ซ่อนไว้โดยค่าเริ่มต้น รายการที่เหลือคือสิ่งที่ยังต้องเปิดดู
ผลเป็นรายการให้คนตรวจ คำบางคำแปลตามบริบทได้ เช่น คำนามทั่วไปหรือสูตรที่รวมกับสูตรอื่นตาม D021
"""
import argparse
import re

from term_stats import ROOT

CJK = r"[㐀-䶿一-鿿豈-﫿]"
KNOWN = ROOT / "tools" / "check_terms_known.tsv"


def split_forms(cell):
    cell = re.sub(r"\(.*?\)", "", cell)
    return [f.strip() for f in cell.split(" / ") if f.strip()]


def glossary_pairs():
    """คืน dict คำจีน → รายการรูปไทยรวมทุกแถว เฉพาะคำจีนที่มีแถวไม่กำกับบริบทอย่างน้อยหนึ่งแถว"""
    pairs, general = {}, set()
    for line in (ROOT / "GLOSSARY.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| จีน"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        scoped = "(" in cells[0]
        zh_forms = split_forms(cells[0])
        th_forms = split_forms(cells[1])
        if len(zh_forms) == len(th_forms):
            mapping = [(z, [t]) for z, t in zip(zh_forms, th_forms)]
        else:
            mapping = [(z, th_forms) for z in zh_forms]
        for zh, ths in mapping:
            if re.fullmatch(CJK + "{2,}", zh) and ths and all("…" not in t for t in ths):
                pairs.setdefault(zh, [])
                pairs[zh] += [t for t in ths if t not in pairs[zh]]
                if not scoped:
                    general.add(zh)
    return {zh: ths for zh, ths in pairs.items() if zh in general}


def all_registered():
    """คำจีนทุกรูปใน GLOSSARY (รวมแถวที่มีวงเล็บ) ใช้ตัดคำที่อยู่ในคำยาวกว่า"""
    names = set()
    for line in (ROOT / "GLOSSARY.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and not line.startswith("| จีน"):
            cell = line.strip().strip("|").split("|")[0]
            names.update(z for z in split_forms(cell) if re.fullmatch(CJK + "{2,}", z))
    return names


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


def bare_count(source, zh, longer):
    for name in sorted(longer, key=len, reverse=True):
        source = source.replace(name, "＊" * len(name))
    return source.count(zh)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("chapters", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--show-known", action="store_true")
    args = parser.parse_args()
    th_dir = ROOT / "translations" / "th"
    if args.all:
        nums = [int(p.stem) for p in sorted(th_dir.glob("[0-9][0-9][0-9].md"))]
    else:
        nums = [int(c) for c in args.chapters]
    pairs = glossary_pairs()
    registered = all_registered()
    longer = {zh: [n for n in registered if zh in n and n != zh] for zh in pairs}
    known = load_known()
    total_hidden = 0
    for num in nums:
        source = next((ROOT / "chapters").glob(f"{num:03d}-*.md")).read_text(encoding="utf-8")
        text = (th_dir / f"{num:03d}.md").read_text(encoding="utf-8")
        missing, hidden = [], []
        for zh, ths in pairs.items():
            if zh not in source or any(t in text for t in ths):
                continue
            count = bare_count(source, zh, longer[zh])
            if not count:
                continue
            (hidden if (zh, num) in known else missing).append((zh, ths, count))
        total_hidden += len(hidden)
        print(f"== บท {num:03d}: ไม่พบรูปไทยตามศัพท์กลาง {len(missing)} รายการ (คัดแยกแล้ว {len(hidden)})")
        for zh, ths, count in missing:
            print(f"  {zh} ({count} ครั้ง) → {' / '.join(ths)}")
        if args.show_known:
            for zh, ths, count in hidden:
                print(f"  [คัดแยกแล้ว: {known[(zh, num)]}] {zh} ({count} ครั้ง) → {' / '.join(ths)}")
    if len(nums) > 1:
        print(f"== รวมคัดแยกแล้ว {total_hidden} รายการ (ดู --show-known)")


if __name__ == "__main__":
    main()
