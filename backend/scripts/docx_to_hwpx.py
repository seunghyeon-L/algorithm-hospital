# -*- coding: utf-8 -*-
"""docx -> hwpx 충실 변환기 (hop/한컴 호환).
   word/document.xml 의 문단·표를 순서대로 읽어 OWPML 로 재현.
   - 표 grid 너비(DXA) -> HWPUNIT, 콘텐츠폭에 맞춰 스케일
   - 셀 내 줄바꿈(여러 문단) 보존, 굵기/정렬 반영
   - hop 페이지네이션용 명시적 쪽나누기 삽입(표3/5/7/9/11 캡션 앞)
"""
import os, zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

SRC = r"C:\Users\lee60\Downloads\제주대병원_정보공개청구서_수정본.docx"
OUT = r"C:\Users\lee60\Downloads\제주대병원_정보공개청구서_수정본.hwpx"
FONT = "함초롬바탕"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CONTENT_W = 48192            # A4 세로, 좌우 여백 5668 제외
BREAK_PREFIX = ("【표3·", "【표5·", "【표7·", "【표9】", "【표11·")

# ---------- OWPML 헤더 부품 ----------
def char_pr(cid, height, bold=False):
    fr = ('<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
          '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
          '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
          '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
          '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>')
    b = "<hh:bold/>" if bold else ""
    return (f'<hh:charPr id="{cid}" height="{height}" textColor="#000000" shadeColor="none" '
            f'useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="2">{fr}{b}</hh:charPr>')

def para_pr(pid, align="LEFT", pbb=0):
    return (f'<hh:paraPr id="{pid}" tabPrIDRef="0" condense="0" fontLineHeight="0" '
            f'snapToGrid="1" suppressLineNumbers="0" checked="0">'
            f'<hh:align horizontal="{align}" vertical="BASELINE"/>'
            f'<hh:heading type="NONE" idRef="0" level="0"/>'
            f'<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD" '
            f'widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="{pbb}" lineWrap="BREAK"/>'
            f'<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
            f'<hh:lineSpacing type="PERCENT" value="150" unit="HWPUNIT"/>'
            f'<hh:border borderFillIDRef="2" offsetLeft="0" offsetRight="0" offsetTop="0" '
            f'offsetBottom="0" connect="0" ignoreMargin="0"/></hh:paraPr>')

def fontfaces():
    langs = ["HANGUL","LATIN","HANJA","JAPANESE","OTHER","SYMBOL","USER"]
    out = "".join(
        f'<hh:fontface lang="{lg}" fontCnt="1"><hh:font id="0" face="{FONT}" type="TTF" isEmbedded="0">'
        f'<hh:typeInfo familyType="FCAP_TYPE_UNKNOWN" weight="0" proportion="0" contrast="0" '
        f'strokeVariation="0" armStyle="0" letterform="0" midline="0" xHeight="0"/></hh:font></hh:fontface>'
        for lg in langs)
    return f'<hh:fontfaces itemCnt="{len(langs)}">{out}</hh:fontfaces>'

def border_fill(bid, solid=False):
    t = "SOLID" if solid else "NONE"
    e = f'type="{t}" width="0.12 mm" color="#000000"'
    return (f'<hh:borderFill id="{bid}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
            f'<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
            f'<hh:leftBorder {e}/><hh:rightBorder {e}/><hh:topBorder {e}/><hh:bottomBorder {e}/>'
            f'<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>')

HEADER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" version="1.4" secCnt="1">'
    '<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>'
    '<hh:refList>' + fontfaces()
    + '<hh:borderFills itemCnt="3">' + border_fill(1) + border_fill(2) + border_fill(3, True) + '</hh:borderFills>'
    + '<hh:charProperties itemCnt="4">' + char_pr(0,900) + char_pr(1,950,True) + char_pr(2,1700,True) + char_pr(3,820) + '</hh:charProperties>'
    + '<hh:tabProperties itemCnt="1"><hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/></hh:tabProperties>'
    + '<hh:numberings itemCnt="0"/>'
    + '<hh:paraProperties itemCnt="4">' + para_pr(0,"LEFT") + para_pr(1,"CENTER") + para_pr(2,"JUSTIFY") + para_pr(3,"LEFT",1) + '</hh:paraProperties>'
    + '<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" '
      'paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>'
    + '</hh:refList></hh:head>')

def P(text, ppr=0, cpr=0):
    return (f'<hp:p id="0" paraPrIDRef="{ppr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cpr}"><hp:t>{escape(text)}</hp:t></hp:run></hp:p>')

def cell(text, col, row, w, h, cpr=0, ppr=0):
    lines = text.split("\n") if text else [""]
    ps = "".join(P(ln, ppr, cpr) for ln in lines)
    return (f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="1" dirty="0" borderFillIDRef="3">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" '
            f'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'{ps}</hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{w}" height="{h}"/>'
            f'<hp:cellMargin left="142" right="142" top="99" bottom="99"/></hp:tc>')

_TID = [1000000000]
def make_table(rows, col_w, rh=1080):
    _TID[0] += 1; tid = _TID[0]
    total_w, total_h = sum(col_w), rh * len(rows)
    trs = ""
    for r, row in enumerate(rows):
        tcs = "".join(cell(t, c, r, col_w[c], rh, cpr=cp, ppr=pp) for c, (t, cp, pp) in enumerate(row))
        trs += f"<hp:tr>{tcs}</hp:tr>"
    tbl = (f'<hp:tbl id="{tid}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
           f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" '
           f'rowCnt="{len(rows)}" colCnt="{len(col_w)}" cellSpacing="0" borderFillIDRef="3" noAdjust="0">'
           f'<hp:sz width="{total_w}" widthRelTo="ABSOLUTE" height="{total_h}" heightRelTo="ABSOLUTE" protect="0"/>'
           f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
           f'vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
           f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
           f'<hp:inMargin left="142" right="142" top="99" bottom="99"/>{trs}</hp:tbl>')
    return (f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0">{tbl}</hp:run></hp:p>')

SECPR_RUN = (
    '<hp:run charPrIDRef="0"><hp:secPr id="0" textDirection="HORIZONTAL" spaceColumns="1134" '
    'tabStop="8000" tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="0" memoShapeIDRef="0" '
    'textVerticalWidthHead="0" masterPageCnt="0">'
    '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0" strtnum="0"/>'
    '<hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>'
    '<hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" '
    'border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>'
    '<hp:pagePr landscape="NARROWLY" width="59528" height="84188" gutterType="LEFT_ONLY">'
    '<hp:margin header="4252" footer="4252" gutter="0" left="5668" right="5668" top="5668" bottom="4252"/></hp:pagePr>'
    '<hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
    '<hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/>'
    '<hp:noteSpacing betweenNotes="850" belowLine="567" aboveLine="567"/>'
    '<hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="EACH_COLUMN" beneathText="0"/></hp:footNotePr>'
    '<hp:endNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
    '<hp:noteLine length="14692344" type="SOLID" width="0.12 mm" color="#000000"/>'
    '<hp:noteSpacing betweenNotes="0" belowLine="567" aboveLine="850"/>'
    '<hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="END_OF_DOCUMENT" beneathText="0"/></hp:endNotePr>'
    '<hp:pageBorderFill type="BOTH" borderFillIDRef="1" textBorder="PAPER" headerInside="0" footerInside="0" fillArea="PAPER">'
    '<hp:offset left="1417" right="1417" top="1417" bottom="1417"/></hp:pageBorderFill></hp:secPr></hp:run>')

# ---------- docx 읽기 ----------
def ptext(p):
    out = []
    for node in p.iter():
        if node.tag == f"{W}t":
            out.append(node.text or "")
        elif node.tag == f"{W}tab":
            out.append("\t")
        elif node.tag == f"{W}br":
            out.append("\n")
    return "".join(out)

def is_bold_run(r):
    rpr = r.find(f"{W}rPr")
    if rpr is None: return False
    b = rpr.find(f"{W}b")
    if b is None: return False
    return b.get(f"{W}val", "true") not in ("false", "0", "none")

def para_bold(p):
    runs = p.findall(f"{W}r")
    runs = [r for r in runs if (r.find(f"{W}t") is not None and (r.find(f'{W}t').text or '').strip())]
    return bool(runs) and all(is_bold_run(r) for r in runs)

def para_align(p):
    jc = p.find(f"{W}pPr/{W}jc")
    return jc.get(f"{W}val") if jc is not None else "left"

def cell_text(tc):
    parts = [ptext(p) for p in tc.findall(f"{W}p")]
    return "\n".join(parts).strip("\n")

def cell_bold(tc):
    ps = tc.findall(f"{W}p")
    txt = "".join(ptext(p) for p in ps).strip()
    return bool(txt) and all(para_bold(p) for p in ps if ptext(p).strip())

def scale_widths(grid):
    if not grid or sum(grid) == 0:
        n = max(len(grid), 1)
        return [CONTENT_W // n] * n
    s = sum(grid)
    w = [round(g / s * CONTENT_W) for g in grid]
    w[-1] += CONTENT_W - sum(w)      # 합 보정
    return w

# ---------- 본문 조립 ----------
root = ET.fromstring(zipfile.ZipFile(SRC).read("word/document.xml").decode("utf-8"))
body = root.find(f"{W}body")

elements = []
for ch in list(body):
    if ch.tag == f"{W}p":
        elements.append(("p", ptext(ch), para_bold(ch), para_align(ch)))
    elif ch.tag == f"{W}tbl":
        grid = ch.find(f"{W}tblGrid")
        widths = [int(gc.get(f'{W}w') or 0) for gc in (grid.findall(f"{W}gridCol") if grid is not None else [])]
        rows = []
        for tr in ch.findall(f"{W}tr"):
            tcs = tr.findall(f"{W}tc")
            rows.append([(cell_text(tc), cell_bold(tc)) for tc in tcs])
        elements.append(("tbl", rows, widths))

body_xml, first_done, prev_empty = [], False, False
n_tbl = n_break = 0
for el in elements:
    if el[0] == "p":
        _, text, bold, align = el
        t = text.strip()
        if not first_done:                       # 제목 + secPr
            body_xml.append('<hp:p id="0" paraPrIDRef="1" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
                            + SECPR_RUN + f'<hp:run charPrIDRef="2"><hp:t>{escape(t)}</hp:t></hp:run></hp:p>')
            first_done = True; prev_empty = False
            continue
        if not t:                                 # 빈 문단(연속 1개로 축약)
            if not prev_empty: body_xml.append(P("", 0, 0))
            prev_empty = True
            continue
        prev_empty = False
        is_cap = t.startswith("【") or t.startswith("■")
        cpr = 1 if (bold or is_cap) else 0
        brk = any(t.startswith(pfx) for pfx in BREAK_PREFIX)
        if brk:
            ppr = 3; n_break += 1               # LEFT + pageBreakBefore
        elif is_cap:
            ppr = 0
        elif align == "center":
            ppr = 1
        elif align in ("both", "distribute"):
            ppr = 2
        else:
            ppr = 2 if t.startswith("·") or len(t) > 40 else 0
        body_xml.append(P(t, ppr, cpr))
    else:
        _, rows, widths = el
        n_tbl += 1
        ncol = max(len(r) for r in rows)
        col_w = scale_widths(widths) if len(widths) == ncol else [CONTENT_W // ncol] * ncol
        rh = 1350 if ncol == 2 else 1080
        out_rows = []
        for ri, row in enumerate(rows):
            cells = []
            for ci in range(ncol):
                txt, cb = row[ci] if ci < len(row) else ("", False)
                if ri == 0:
                    cp, pp = 1, 1                # 헤더: 굵게·가운데
                else:
                    cp = 1 if cb else 0
                    pp = 0 if (ci == 0 or len(txt) > 10) else 1
                cells.append((txt, cp, pp))
            out_rows.append(cells)
        body_xml.append(make_table(out_rows, col_w, rh))

SECTION = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">' + "".join(body_xml) + '</hs:sec>')

VERSION = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" tagetApplication="WORDPROCESSOR" '
    'major="5" minor="1" micro="0" buildNumber="0" os="1" xmlVersion="1.4" application="Hancom Office Hangul" appVersion="11.0.0.0"/>')
SETTINGS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app">'
    '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/></ha:HWPApplicationSetting>')
CONTAINER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"><ocf:rootfiles>'
    '<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>')
CONTENT_HPF = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'version="" unique-identifier="" id=""><opf:metadata><opf:title>정보공개 청구서</opf:title>'
    '<opf:language>ko</opf:language></opf:metadata><opf:manifest>'
    '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>'
    '</opf:manifest><opf:spine><opf:itemref idref="section0" linear="yes"/></opf:spine></opf:package>')
MANIFEST = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" version="1.2">'
    '<odf:file-entry odf:full-path="/" odf:media-type="application/hwp+zip"/>'
    '<odf:file-entry odf:full-path="version.xml" odf:media-type="application/xml"/>'
    '<odf:file-entry odf:full-path="settings.xml" odf:media-type="application/xml"/>'
    '<odf:file-entry odf:full-path="Contents/content.hpf" odf:media-type="application/hwpml-package+xml"/>'
    '<odf:file-entry odf:full-path="Contents/header.xml" odf:media-type="application/xml"/>'
    '<odf:file-entry odf:full-path="Contents/section0.xml" odf:media-type="application/xml"/></odf:manifest>')

files = {"version.xml":VERSION,"settings.xml":SETTINGS,"Contents/content.hpf":CONTENT_HPF,
         "Contents/header.xml":HEADER,"Contents/section0.xml":SECTION,
         "META-INF/container.xml":CONTAINER,"META-INF/manifest.xml":MANIFEST}
import xml.dom.minidom as M
for c in files.values(): M.parseString(c.encode("utf-8"))
print("XML OK | 표:", n_tbl, "| 쪽나누기:", n_break, "| 문단요소:", sum(1 for e in elements if e[0]=='p'))
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    zi=zipfile.ZipInfo("mimetype"); zi.compress_type=zipfile.ZIP_STORED
    z.writestr(zi,"application/hwp+zip")
    for n,c in files.items(): z.writestr(n,c.encode("utf-8"))
print("size", os.path.getsize(OUT), "->", OUT)
