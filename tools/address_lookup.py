"""แสดงแถวใน docs/ADDRESS_TERMS_CASES.md ที่คำจีนปรากฏในต้นฉบับบท NNN (D045)

ใช้: python -X utf8 tools/address_lookup.py NNN
แถวที่มีคำพื้นฐานอย่าง 我 / 吾 จะขึ้นเกือบทุกบท เพราะแยกตามบริบทผู้พูด ให้เลือกใช้ตามฉาก
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "docs" / "ADDRESS_TERMS_CASES.md"
CJK = re.compile(r"[㐀-鿿\U00020000-\U0002ffff]+")


def chapter_text(num: str) -> str:
    files = sorted((ROOT / "chapters").glob(f"{num}-*.md"))
    if not files:
        sys.exit(f"ไม่พบต้นฉบับบท {num}")
    return files[0].read_text(encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("ใช้: python -X utf8 tools/address_lookup.py NNN")
    num = sys.argv[1].zfill(3)
    text = chapter_text(num)
    section = ""
    hits = 0
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:]
            continue
        if not line.startswith("| ") or line.startswith("| จีน"):
            continue
        first_cell = line.split(" | ")[0][2:]
        terms = [t for t in CJK.findall(first_cell) if t in text]
        if terms:
            hits += 1
            print(f"[{section}] {line}")
    print(f"\nพบ {hits} แถวที่เกี่ยวกับบท {num}")


if __name__ == "__main__":
    main()
