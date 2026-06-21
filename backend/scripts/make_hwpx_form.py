# -*- coding: utf-8 -*-
"""제주대병원 정보공개청구서 — 병원이 '수치를 채울 빈칸 응답표' + case-level 요청 양식.
   (집계통계 + 분위수 + 대기시간분포 + 취소사유 + case-level 비식별 데이터) hop·한컴오피스 .hwpx"""
import os, zipfile
from xml.sax.saxutils import escape

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__),
      "..", "..", "..", "..", "..", "제주대병원_정보공개청구서_양식.hwpx"))
FONT = "함초롬바탕"

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
            f'<hh:lineSpacing type="PERCENT" value="140" unit="HWPUNIT"/>'
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
    return (f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="1" dirty="0" borderFillIDRef="3">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" '
            f'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
            f'{P(text, ppr, cpr)}</hp:subList>'
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

def atable(headers, rowlabels, col_w, rh=1080):     # 빈칸 응답표
    rows = [[(h, 1, 1) for h in headers]]
    for rl in rowlabels:
        rows.append([(rl, 0, 0)] + [("", 0, 1)] * (len(headers) - 1))
    return make_table(rows, col_w, rh)

def dtable(headers, rows2, col_w, rh=1080):          # 설명형(양쪽 채움)
    rows = [[(h, 1, 1) for h in headers]]
    for a, b in rows2:
        rows.append([(a, 1, 0), (b, 3, 0)])
    return make_table(rows, col_w, rh)

# 너비
W5 = [12800, 8800, 8800, 8800, 8800]
W4 = [15000, 11000, 11000, 11000]
W3 = [22000, 13000, 13000]
W2 = [22000, 26000]
WMON = [8000] + [3333] * 12
WDOW = [10000] + [5428] * 7
W6 = [12000, 7200, 7200, 7200, 7200, 7200]
WD = [16000, 6400, 6400, 6400, 6400, 6400]
WCAN = [20000, 14000, 14000]
WSPEC = [16000, 32000]
DEPT = ["외과","정형외과","산부인과","안과","신경외과","이비인후과","비뇨의학과","흉부외과","성형외과"]
QHDR = ["평균","중앙값","25%분위","75%분위","90%분위"]

# 청구인 표
LW, VW = 9000, 39000
applicant = [
    [("성    명",1,0), ("________________  (소속: 제주대 컴퓨터공학과 ‘알고리즘’ 수업 팀·대표)",0,0)],
    [("연 락 처",1,0), ("전화 __________      전자우편 __________________",0,0)],
    [("주    소",1,0), ("________________________________________",0,0)],
    [("청구 목적",1,0), ("학술·연구(수업 팀 프로젝트 — 수술실·의료진 스케줄링 최적화 모델 파라미터)",0,0)],
    [("공개 방법",1,0), ("■ 전자파일(엑셀/한글)   □ 열람   □ 사본·출력물   □ 기타",0,0)],
    [("수령 방법",1,0), ("■ 정보통신망(open.go.kr)   □ 전자우편   □ 우편   □ 직접방문",0,0)],
    [("수 수 료",1,0), ("■ 학술·연구(비영리 교육) 목적 수수료 감면 신청",0,0)],
    [("청 구 일",1,0), ("20______ . ______ . ______ .",0,0)],
    [("청 구 인",1,0), ("________________________  (서명 또는 인)",0,0)],
]

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

body = []
body.append('<hp:p id="0" paraPrIDRef="1" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            + SECPR_RUN + '<hp:run charPrIDRef="2"><hp:t>정보공개 청구서</hp:t></hp:run></hp:p>')
body.append(P("", 0, 0))
body.append(make_table(applicant, [LW, VW], rh=1450))
body.append(P("받는 곳 : 제주대학교병원 정보공개 담당부서 귀하", 0, 1))
body.append(P("바쁘신 와중에 번거롭게 해 드려 죄송합니다. 아래 표 가운데 보유·제공이 가능하신 항목만, 가능한 범위에서 기재해 주시면 저희 수업 과제에 큰 도움이 되겠습니다. 환자 개인정보는 전혀 필요하지 않으며, 진료과·기관 단위의 집계 수치만으로 충분합니다. 제공이 어려운 항목은 비워 두셔도 괜찮습니다.", 2, 0))
body.append(P("· 연도는 평상시 2019·2023, 위기 2024, 회복 2025를 참고로 적어 두었으며, 인력은 각 연도 말 기준입니다. 시간·대기 분포는 최근 1년 기준이면 충분하고, 모든 항목은 보유·가능하신 범위에서만 주셔도 됩니다.", 2, 0))
body.append(P("", 0, 0))

def cap(t):  body.append(P(t, 0, 1))
def capb(t): body.append(P(t, 3, 1))   # 쪽 나누기

# === 1쪽 ===
cap("【표1·핵심】 수술실 운영 (개)")
body.append(atable(["구분","2019","2023","2024","2025"],
            ["전체 수술실 보유 개수","실가동 수술실 개수","수술실 평균 가동률(%)"], W5))
cap("【표2·핵심】 2024년 월별 추이 (의정갈등 위기)")
body.append(atable(["2024년","1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"],
            ["실가동 수술실 수","총 수술 건수","가동률(%)"], WMON))
cap("【표2-b】 요일별 평균 (최근 1년) ※요일 효과")
body.append(atable(["구분","월","화","수","목","금","토","일"],
            ["일평균 수술 건수","평균 실가동 수술실 수"], WDOW))

# === 2쪽 ===
capb("【표3·핵심】 진료과별 전문의 수 (각 연도 12.31, 명)")
body.append(atable(["진료과","2019","2023","2024","2025"], DEPT + ["마취통증의학과","수술실 근무 간호인력"], W5))
cap("【표4】 진료과별 전공의 수 (명)")
body.append(atable(["진료과","2019","2023","2024","2025"], DEPT, W5))

# === 3쪽 ===
capb("【표5·핵심】 진료과별 연간 수술 건수 (건)  ※2024년은 표2 월별 참조")
body.append(atable(["진료과","2019","2023","2024","2025"], DEPT + ["합계"], W5))
cap("【표6·핵심】 진료과별 수술 소요시간 분포 (집도시간, 분, 최근 1년)")
body.append(atable(["진료과"] + QHDR, DEPT, W6))

# === 4쪽 ===
capb("【표7·핵심】 수술 1건당 평균 투입 의료인력 (명)")
body.append(atable(["구분","2023","2024"],
            ["집도 전문의","보조 의사(전임의·전공의)","마취과 의사","수술 간호사(소독·순환)"], W3))
cap("【표8·핵심】 수술 전후·전환 시간 분포 (분, 최근 1년)")
body.append(atable(["구분"] + QHDR,
            ["수술 전 준비시간(입실~집도)","회복실 체류시간","퇴실 준비시간(회복~귀가)","전환시간(turnover)"], WD))
cap("【표8-b·핵심】 환자 대기시간 분포 (분, 최근 1년)  ※목적함수(총 대기) 검증용")
body.append(atable(["구분"] + QHDR,
            ["내원 ~ 수술 시작","수술 종료 ~ 퇴실"], WD))

# === 5쪽 ===
capb("【표9】 예정/응급 수술 및 대기")
body.append(atable(["구분","2023","2024","2025"],
            ["예정 수술 건수","응급·add-on 수술 건수","예약일~수술시행일 평균 일수(일)"], W4))
cap("【표9-b】 수술 지연·취소 사유별 건수")
body.append(atable(["사유 대분류","2023","2024","2025"],
            ["수술실 부족(OR unavailable)","인력 부족(staff)","회복실(PACU) 부족","환자 사유","기타"], W4))
cap("【표10】 현재 기준 시설·운영")
body.append(atable(["구분","현재(20__ . __ 기준)"],
            ["회복실(PACU) 병상 수","수술 후 중환자실(ICU) 병상 수","수술실 유형별 개수(일반/하이브리드/응급전용)",
             "정규 운영시간(평일 1일, 분)","진료과별 블록타임 운영 여부·배정 현황",
             "응급수술 대응용 여유 block 여부","수술실 초과운영(overtime) 발생 여부·정도",
             "시간대별 마취과 의사 평균 배치 수","시간대별 수술실 간호사 평균 배치 수"], W2, rh=1250))

# === 6쪽: case-level (옵션) ===
capb("【표11·선택】 수술 건별(행 단위) 운영 데이터 (보유·제공 가능하신 경우)")
body.append(P("혹시 수술 건별(한 행 = 수술 1건) 데이터를 제공해 주실 수 있다면, 귀원이 보관하고 계신 형식·항목 그대로 주셔도 저희에게 매우 큰 도움이 됩니다. 저희는 환자 개인정보가 전혀 필요하지 않습니다. 아래 목록은 ‘있으면 특히 도움이 되는’ 항목을 참고로 정리한 것일 뿐이니, 보유하신 범위에서 가능한 항목만 주셔도 충분합니다.", 2, 0))
body.append(dtable(["참고 : 도움이 되는 항목","비고 (보유하신 형식대로면 됩니다)"], [
    ("수술 건 구분", "수술 1건 구분용 임의 번호 (가명이면 됩니다)"),
    ("수술일 / 요일", "보유하신 형식대로 (상대일·월 단위 등도 좋습니다)"),
    ("진료과 또는 수술 유형", "대분류만으로 충분합니다"),
    ("수술 규모 / 유형", "예: 단시간·중간·장시간 등 구분이 있으면"),
    ("예정 / 응급 구분", "예정 / 응급·add-on"),
    ("주요 시각", "내원·준비 시작·집도 시작/종료·회복·퇴실 등 (보유 단위대로)"),
    ("수술실 / 집도의 구분", "가명·구분 기호면 됩니다 (실명 불필요)"),
    ("마취 구분", "유무 또는 종류 대분류 (있으면)"),
    ("지연·취소 사유", "있으면 사유 대분류"),
], WSPEC))

body.append(P("", 0, 0))
body.append(P("■ 부탁의 말씀", 0, 1))
body.append(P("· 정해진 통계로 보관하고 계시지 않은 항목은, 보유하신 가까운 자료나 대략적인 범위만 주셔도 정말 감사하겠습니다. 제공이 어려운 항목은 신경 쓰지 않으셔도 됩니다.", 2, 0))
body.append(P("· 제공 가능한 자료 범위나 문의드릴 담당 부서가 있으시면 안내해 주시면 감사하겠습니다. 바쁘신 와중에 검토해 주셔서 진심으로 감사드립니다.", 2, 0))

SECTION = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">' + "".join(body) + '</hs:sec>')

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
print("XML OK")
with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED) as z:
    zi=zipfile.ZipInfo("mimetype"); zi.compress_type=zipfile.ZIP_STORED
    z.writestr(zi,"application/hwp+zip")
    for n,c in files.items(): z.writestr(n,c.encode("utf-8"))
print("size", os.path.getsize(OUT))
