# -*- coding: utf-8 -*-
"""제주대병원 정보공개청구서를 .hwpx(OWPML, 개방표준)로 생성. hop·한컴오피스에서 열림."""
import os, zipfile
from xml.sax.saxutils import escape

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..",
                   "제주대병원_정보공개청구서.hwpx")
OUT = os.path.abspath(OUT)

# ---- 문서 내용: (kind, text) ----
# kind: title / h(섹션) / sub(소제목) / body / small
DOC = [
    ("title", "정보공개 청구서"),

    ("h", "■ 청구인"),
    ("body", "성명: ____________     소속: 제주대학교 컴퓨터공학과 (‘알고리즘’ 수업 팀 · 대표)"),
    ("body", "연락처(전화·이메일): ____________     주소: ____________"),
    ("small", "※ 집계통계 청구로 본인확인이 불필요하므로 주민등록번호는 기재하지 않습니다."),

    ("h", "■ 접수 기관"),
    ("body", "제주대학교병원 (정보공개 담당부서)"),

    ("h", "■ 청구 목적"),
    ("body", "학술·연구(제주대학교 ‘알고리즘’ 수업 팀 프로젝트 — 수술실·의료진 스케줄링 최적화 모델 파라미터). "
             "비영리 교육 목적 수수료 감면을 신청합니다."),

    ("h", "■ 청구 취지"),
    ("body", "모델 파라미터 검증을 위해 아래 집계·통계 자료(환자 개인정보·진료기록 및 개인 식별정보 일절 제외)의 "
             "공개를 청구합니다. 귀원이 보유·관리하는 범위 내에서, 부분공개로 제공해 주셔도 충분합니다."),

    ("h", "■ 연도·기준 정의"),
    ("body", "· 평상시 2019(코로나·의정갈등 이전 기준선) + 2023(최근 평상시) / "
             "2024(의정갈등 위기 — 가능하면 월별, 어려우면 분기·반기 대체 가능) / 2025(회복·현재)"),
    ("body", "· 인력은 각 연도 12월 31일 기준."),
    ("body", "· ‘현재’ = 청구 접수일 기준 최신 보유분(또는 2025.12.31)."),
    ("body", "· ‘실가동 수술실’ = 해당 연도 중 1일 이상 정규 수술에 사용된 수술실 수."),
    ("body", "· 2019년분이 보존기간 경과로 미보유 시 그 사실만 회신하시고, 나머지 연도는 정상 공개 바랍니다."),

    ("h", "■ [A] 핵심 항목 — 우선 공개 요청 (모델 직접 파라미터)"),
    ("body", "A1. 전체 수술실 보유 개수 + 연도별 실가동 수술실 개수 〔2019·2023·2024(월별)·2025〕"),
    ("body", "A2. 수술 시행 진료과별 전문의 수(외과·정형외과·산부인과·안과·신경외과·이비인후과·비뇨의학과·"
             "흉부외과·성형외과) 〔2019·2023·2024·2025, 각 12.31〕 ※과별 인원수만, 5명 미만 과는 구간 표기 가능."),
    ("body", "A2-b. 수술 1건당 평균 투입 의료 인력 구성 — 진료과별(또는 주요 수술 유형별) 1건당 평균: "
             "① 집도 전문의 수 ② 보조 의사(전임의·전공의) 수 ③ 마취과 의사 수 ④ 수술 간호사(소독·순환) 수 "
             "〔2023·2024, 보유분〕 ※평균 인원수만, 미보유 시 수술기록상 참여 인력 집계로 갈음 가능."),
    ("body", "A3. 마취통증의학과 전문의 수 〔2019·2023·2024·2025〕"),
    ("body", "A4. 수술실(마취·회복 포함) 근무 간호 인력 수 〔2019·2023·2024·2025, 전담 구분 없으면 배치 인원수〕"),
    ("body", "A5. 진료과별 연간 수술 건수 〔2019·2023·2024(월별)·2025〕"),
    ("body", "A6. 진료과별 평균 수술 소요시간(집도시간 기준, 가능 시 표준편차·분포) 〔2023·2024〕"),
    ("body", "A7. 수술 전 환자 준비시간(입실~집도 시작: 검사·마취유도·포지셔닝 포함) 및 평균 회복실 체류시간 "
             "〔2024·2025, 보유분〕"),
    ("body", "A8. 수술 간 평균 전환시간(turnover time) 〔2024·2025, 보유분〕"),

    ("h", "■ [B] 부가 항목 — 보유분만, 가능 범위 내 (검증·배경용)"),
    ("body", "B1. 위 진료과별 전공의 수 〔2019·2023·2024·2025〕"),
    ("body", "B2. 예정/응급 수술 비율(또는 각 건수) 〔2023·2024〕"),
    ("body", "B3. 수술실 평균 가동률 〔2019·2023·2024(월별)·2025〕 ※운영현황 통계"),
    ("body", "B4. 당일 수술 취소 건수 및 전체 예정 건수(비율 대신 분자·분모) + 예약일~수술시행일 평균 일수 "
             "〔2023·2024·2025〕"),
    ("body", "B5. 회복실(PACU) 병상 수 + 수술 후 중환자실(ICU) 병상 수 〔현재〕"),
    ("body", "B6. 수술실 유형별 개수(일반/하이브리드/응급전용, 분류 보유 시) + 정규 운영시간(평일 1일 운영 분 수 포함) "
             "+ 진료과별 블록타임(확정·시행 중) 배정 현황 〔현재〕"),

    ("h", "■ 대체공개·부분공개 요청 (거부 방지)"),
    ("body", "· 특정 항목을 표준 통계로 보유하지 않으시면 ‘부존재’로 종결하지 마시고, 산출의 기초가 되는 "
             "비식별 집계 원자료(예: 연간 총 수술시간 합계와 수술실 가동시간, 수술 종료~다음 수술 시작 간격, "
             "회복실 입·퇴실 시각 집계, 예약~수술 일자 집계)로 갈음 공개해 주시면 충분합니다."),
    ("body", "· 가동률·전환시간 등은 영리적 경쟁정보가 아니라 공공병원의 운영현황 통계이며, "
             "비영리 공공기관 성격상 비공개 대상이 아님을 확인 바랍니다."),

    ("h", "■ 처리 관련 요청"),
    ("body", "· 「공공기관의 정보공개에 관한 법률」 제11조에 따라 접수일부터 10일 이내(부득이 시 10일 연장) "
             "공개 여부 결정을 요청합니다."),
    ("body", "· 부존재·비공개 결정 시 그 사유와 근거 조문을 명시해 주시기 바랍니다."),

    ("h", "■ 공개·수령 방법"),
    ("body", "공개 방법: 전자파일(엑셀 또는 한글)     수령 방법: 정보통신망(정보공개포털 open.go.kr) 또는 이메일"),
]

# ---- OWPML 빌드 ----
FONT = "함초롬바탕"

def fontfaces():
    langs = ["HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"]
    out = []
    for lg in langs:
        out.append(
            f'<hh:fontface lang="{lg}" fontCnt="1">'
            f'<hh:font id="0" face="{FONT}" type="TTF" isEmbedded="0">'
            f'<hh:typeInfo familyType="FCAP_TYPE_UNKNOWN" weight="0" proportion="0" contrast="0" '
            f'strokeVariation="0" armStyle="0" letterform="0" midline="0" xHeight="0"/>'
            f'</hh:font></hh:fontface>'
        )
    return f'<hh:fontfaces itemCnt="{len(langs)}">' + "".join(out) + "</hh:fontfaces>"

def char_pr(cid, height, bold=False, color="000000"):
    fr = ('<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
          '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
          '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
          '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
          '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>')
    b = "<hh:bold/>" if bold else ""
    return (f'<hh:charPr id="{cid}" height="{height}" textColor="{color}" shadeColor="none" '
            f'useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="2">'
            f'{fr}{b}</hh:charPr>')

def para_pr(pid, align="LEFT"):
    return (f'<hh:paraPr id="{pid}" tabPrIDRef="0" condense="0" fontLineHeight="0" '
            f'snapToGrid="1" suppressLineNumbers="0" checked="0">'
            f'<hh:align horizontal="{align}" vertical="BASELINE"/>'
            f'<hh:heading type="NONE" idRef="0" level="0"/>'
            f'<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD" '
            f'widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>'
            f'<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
            f'<hh:lineSpacing type="PERCENT" value="160" unit="HWPUNIT"/>'
            f'<hh:border borderFillIDRef="2" offsetLeft="0" offsetRight="0" offsetTop="0" '
            f'offsetBottom="0" connect="0" ignoreMargin="0"/></hh:paraPr>')

HEADER = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" version="1.4" secCnt="1">'
    '<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>'
    '<hh:refList>'
    + fontfaces()
    + '<hh:borderFills itemCnt="2">'
      '<hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
      '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
      '<hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/><hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>'
      '<hh:topBorder type="NONE" width="0.1 mm" color="#000000"/><hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>'
      '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>'
      '<hh:borderFill id="2" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
      '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
      '<hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/><hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>'
      '<hh:topBorder type="NONE" width="0.1 mm" color="#000000"/><hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>'
      '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>'
      '</hh:borderFills>'
    + '<hh:charProperties itemCnt="3">'
      + char_pr(0, 1000) + char_pr(1, 1050, bold=True) + char_pr(2, 1600, bold=True)
      + '</hh:charProperties>'
    + '<hh:tabProperties itemCnt="1"><hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/></hh:tabProperties>'
    + '<hh:numberings itemCnt="0"/>'
    + '<hh:paraProperties itemCnt="2">' + para_pr(0, "LEFT") + para_pr(1, "CENTER") + '</hh:paraProperties>'
    + '<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" '
      'paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>'
    + '</hh:refList></hh:head>'
)

def para(kind, text):
    if kind == "title":
        ppr, cpr = 1, 2
    elif kind == "h":
        ppr, cpr = 0, 1
    elif kind == "small":
        ppr, cpr = 0, 0
    else:
        ppr, cpr = 0, 0
    return (f'<hp:p id="0" paraPrIDRef="{ppr}" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cpr}"><hp:t>{escape(text)}</hp:t></hp:run></hp:p>')

SECPR = (
    '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
    '<hp:run charPrIDRef="0">'
    '<hp:secPr id="0" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" '
    'tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="0" memoShapeIDRef="0" '
    'textVerticalWidthHead="0" masterPageCnt="0">'
    '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0" strtnum="0"/>'
    '<hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>'
    '<hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" '
    'border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" '
    'showLineNumber="0"/>'
    '<hp:pagePr landscape="NARROWLY" width="59528" height="84188" gutterType="LEFT_ONLY">'
    '<hp:margin header="4252" footer="4252" gutter="0" left="8504" right="8504" '
    'top="5668" bottom="4252"/></hp:pagePr>'
    '<hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
    '<hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/>'
    '<hp:noteSpacing betweenNotes="850" belowLine="567" aboveLine="567"/>'
    '<hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="EACH_COLUMN" beneathText="0"/></hp:footNotePr>'
    '<hp:endNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/>'
    '<hp:noteLine length="14692344" type="SOLID" width="0.12 mm" color="#000000"/>'
    '<hp:noteSpacing betweenNotes="0" belowLine="567" aboveLine="850"/>'
    '<hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="END_OF_DOCUMENT" beneathText="0"/></hp:endNotePr>'
    '<hp:pageBorderFill type="BOTH" borderFillIDRef="1" textBorder="PAPER" headerInside="0" '
    'footerInside="0" fillArea="PAPER"><hp:offset left="1417" right="1417" top="1417" bottom="1417"/></hp:pageBorderFill>'
    '</hp:secPr></hp:run>'
    '<hp:run charPrIDRef="2"><hp:t></hp:t></hp:run></hp:p>'
)

SECTION = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
    + SECPR
    + "".join(para(k, t) for k, t in DOC)
    + '</hs:sec>'
)

VERSION = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
    'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="0" buildNumber="0" '
    'os="1" xmlVersion="1.4" application="Hancom Office Hangul" appVersion="11.0.0.0"/>')

SETTINGS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app">'
    '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/></ha:HWPApplicationSetting>')

CONTAINER = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<ocf:rootfiles>'
    '<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
    '</ocf:rootfiles></ocf:container>')

CONTENT_HPF = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" version="" unique-identifier="" id="">'
    '<opf:metadata>'
    '<opf:title>정보공개 청구서</opf:title>'
    '<opf:language>ko</opf:language>'
    '<opf:meta name="creator" content="hop/owpml"/>'
    '</opf:metadata>'
    '<opf:manifest>'
    '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
    '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
    '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>'
    '</opf:manifest>'
    '<opf:spine><opf:itemref idref="section0" linear="yes"/></opf:spine>'
    '</opf:package>')

MANIFEST = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" version="1.2">'
    '<odf:file-entry odf:full-path="/" odf:media-type="application/hwp+zip"/>'
    '<odf:file-entry odf:full-path="version.xml" odf:media-type="application/xml"/>'
    '<odf:file-entry odf:full-path="settings.xml" odf:media-type="application/xml"/>'
    '<odf:file-entry odf:full-path="Contents/content.hpf" odf:media-type="application/hwpml-package+xml"/>'
    '<odf:file-entry odf:full-path="Contents/header.xml" odf:media-type="application/xml"/>'
    '<odf:file-entry odf:full-path="Contents/section0.xml" odf:media-type="application/xml"/>'
    '</odf:manifest>')

files = {
    "version.xml": VERSION,
    "settings.xml": SETTINGS,
    "Contents/content.hpf": CONTENT_HPF,
    "Contents/header.xml": HEADER,
    "Contents/section0.xml": SECTION,
    "META-INF/container.xml": CONTAINER,
    "META-INF/manifest.xml": MANIFEST,
}

# 잘 형성됐는지 XML 검증
import xml.dom.minidom as M
for name, content in files.items():
    M.parseString(content.encode("utf-8"))
print("XML well-formed: OK (%d files)" % (len(files) + 1))

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    # mimetype must be first and STORED
    zi = zipfile.ZipInfo("mimetype")
    zi.compress_type = zipfile.ZIP_STORED
    z.writestr(zi, "application/hwp+zip")
    for name, content in files.items():
        z.writestr(name, content.encode("utf-8"))

print("WROTE:", OUT)
print("size:", os.path.getsize(OUT), "bytes")
