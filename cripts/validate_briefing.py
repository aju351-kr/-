#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
회계팀 아침 브리핑 HTML 자동 검증기.

목적:
  모델이 제출 전에 HTML을 눈으로 다시 훑는 대신, 규칙 위반을
  코드로 잡아내 토큰을 아끼기 위한 스크립트.

사용법:
  python3 scripts/validate_briefing.py /tmp/accounting-briefing-YYYY-MM-DD.html

검사 항목:
  1) 핵심 지표 화살표(▲/▼/보합)와 class(up/down/flat) 일치 여부
  2) 개별 게시물이 아닌 '홈페이지 루트'로만 연결된 출처 링크
  3) note에 '기준/접속'만 있고 HH:MM 확인 시각이 빠진 경우
  4) .source / .note / .metric-detail 출처 문장에 <a href> 누락
  5) badge class 계열과 카드 data-category 불일치
  6) 3~8번 섹션(#finance, #industry, #competitors, #global, #ai, #coffee)
     카드 개수가 3~6 범위를 벗어난 경우

종료 코드:
  0 = ERROR 없음(WARN은 있을 수 있음)
  1 = ERROR 있음(제출 전 수정 필요)
  2 = 파일을 열 수 없음
"""

import re
import sys
from html.parser import HTMLParser
from urllib.parse import urlparse

# 3~8번 섹션 id (카드 개수 3~6 규칙 적용 대상)
CARD_SECTIONS = {"finance", "industry", "competitors", "global", "ai", "coffee"}
CATEGORY_WORDS = {"tax", "cash", "industry", "global", "light"}
TIME_RE = re.compile(r"\d{1,2}\s*:\s*\d{2}")
TIME_HINT_RE = re.compile(r"(기준|접속)")


class Frame:
    __slots__ = ("tag", "classes", "attrs", "entry_anchor", "text")

    def __init__(self, tag, classes, attrs, entry_anchor):
        self.tag = tag
        self.classes = classes
        self.attrs = attrs
        self.entry_anchor = entry_anchor
        self.text = []


class BriefingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.anchor_count = 0

        self.errors = []
        self.warns = []

        # 링크 검사용
        self.links = []  # (href, path_only_root: bool)
        # 섹션별 카드 개수
        self.section_cards = {}  # id -> count
        self._current_section = None

    # ---- 유틸 ----
    @staticmethod
    def _classes(attrs):
        d = dict(attrs)
        return set((d.get("class") or "").split())

    def _text_of(self, frame):
        return "".join(frame.text).strip()

    def _find_ancestor_data_category(self):
        for f in reversed(self.stack):
            dc = dict(f.attrs).get("data-category")
            if dc:
                return dc.strip()
        return None

    # ---- 파서 콜백 ----
    def handle_starttag(self, tag, attrs):
        classes = self._classes(attrs)

        # 섹션 진입
        if tag == "section":
            sid = dict(attrs).get("id")
            if sid:
                self._current_section = sid
                self.section_cards.setdefault(sid, 0)

        # 카드 카운트
        if tag == "article" and "card" in classes and self._current_section:
            self.section_cards[self._current_section] = (
                self.section_cards.get(self._current_section, 0) + 1
            )

        # 링크 수집
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.anchor_count += 1
                self._check_link(href)

        # data 접기 방지: 모든 스택 프레임에 텍스트 누적하기 위해 push
        self.stack.append(Frame(tag, classes, attrs, self.anchor_count))

    def handle_startendtag(self, tag, attrs):
        # 자기완결 태그(예: <img/>): 링크만 확인
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.anchor_count += 1
                self._check_link(href)

    def handle_data(self, data):
        if not data:
            return
        for f in self.stack:
            f.text.append(data)

    def handle_endtag(self, tag):
        # 스택에서 해당 태그까지 pop (엉킨 태그 보정)
        idx = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                idx = i
                break
        if idx is None:
            return
        # idx 위에 남은 프레임도 함께 정리
        popped = self.stack[idx:]
        self.stack = self.stack[:idx]

        for frame in popped:
            self._on_close(frame)

        if tag == "section":
            self._current_section = None

    # ---- 개별 규칙 ----
    def _on_close(self, frame):
        classes = frame.classes
        text = self._text_of(frame)
        had_anchor = self.anchor_count > frame.entry_anchor

        # (1) move 화살표/class 일치
        if frame.tag == "span" and "move" in classes:
            self._check_move(classes, text)

        # (4) 출처 문장에 <a> 누락
        target = {"source", "note", "metric-detail"} & classes
        if target and text:
            if not had_anchor:
                self.errors.append(
                    f"[출처링크 누락] class={sorted(classes)} 안에 <a href>가 없음 → \"{text[:40]}...\""
                )
            # (3) 시각 표기 검사 (note 계열에서만)
            if "note" in classes and TIME_HINT_RE.search(text) and not TIME_RE.search(text):
                self.warns.append(
                    f"[확인시각 누락] note에 '기준/접속'은 있으나 HH:MM 없음 → \"{text[:50]}\""
                )

        # (5) badge 계열 vs data-category
        if "badge" in classes:
            badge_cat = (CATEGORY_WORDS & classes)
            dc = self._find_ancestor_data_category()
            if badge_cat and dc and dc not in badge_cat:
                self.errors.append(
                    f"[배지 불일치] badge class={sorted(badge_cat)} 인데 data-category={dc}"
                )

    def _check_move(self, classes, text):
        up = "up" in classes
        down = "down" in classes
        flat = "flat" in classes
        has_up_arrow = "▲" in text
        has_down_arrow = "▼" in text

        if up and has_down_arrow:
            self.errors.append(f'[화살표 불일치] class="move up" 인데 ▼ 사용 → "{text[:30]}"')
        if down and has_up_arrow:
            self.errors.append(f'[화살표 불일치] class="move down" 인데 ▲ 사용 → "{text[:30]}"')
        if up and not has_up_arrow and not flat:
            self.warns.append(f'[화살표 확인] class="move up" 인데 ▲ 없음 → "{text[:30]}"')
        if down and not has_down_arrow and not flat:
            self.warns.append(f'[화살표 확인] class="move down" 인데 ▼ 없음 → "{text[:30]}"')
        if flat and ("보합" not in text and "확인 불가" not in text and "확인불가" not in text):
            self.warns.append(f'[보합 표기 확인] class="move flat" 인데 보합/확인 불가 문구 없음 → "{text[:30]}"')

    def _check_link(self, href):
        h = href.strip()
        if h.startswith("#") or h.startswith("mailto:") or h.startswith("javascript:"):
            return
        try:
            p = urlparse(h)
        except Exception:
            return
        if not p.scheme:
            return
        # 경로가 없거나 '/'뿐이고, 쿼리/프래그먼트도 없으면 홈페이지 루트로 간주
        path = (p.path or "").strip("/")
        if path == "" and not p.query and not p.fragment:
            self.errors.append(f"[홈페이지 링크] 개별 게시물이 아닌 루트 주소 → {h}")

    # ---- 파싱 후 카드 개수 검사 (6) ----
    def finalize(self):
        for sid, cnt in self.section_cards.items():
            if sid in CARD_SECTIONS:
                if cnt < 3:
                    self.errors.append(f"[카드 개수] #{sid} 섹션 카드 {cnt}개 (최소 3개)")
                elif cnt > 6:
                    self.errors.append(f"[카드 개수] #{sid} 섹션 카드 {cnt}개 (최대 6개)")


def main():
    if len(sys.argv) < 2:
        print("사용법: python3 scripts/validate_briefing.py <html파일경로>")
        sys.exit(2)

    path = sys.argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
    except OSError as e:
        print(f"파일을 열 수 없습니다: {e}")
        sys.exit(2)

    parser = BriefingParser()
    parser.feed(html)
    parser.finalize()

    print("=" * 60)
    print(f"검증 대상: {path}")
    print("=" * 60)

    if parser.section_cards:
        print("\n[섹션별 카드 개수]")
        for sid, cnt in parser.section_cards.items():
            mark = " (3~6 대상)" if sid in CARD_SECTIONS else ""
            print(f"  #{sid}: {cnt}개{mark}")

    if parser.errors:
        print(f"\n❌ ERROR {len(parser.errors)}건 — 제출 전 수정 필요")
        for e in parser.errors:
            print(f"  - {e}")
    else:
        print("\n✅ ERROR 없음")

    if parser.warns:
        print(f"\n⚠️  WARN {len(parser.warns)}건 — 확인 권장")
        for w in parser.warns:
            print(f"  - {w}")

    print()
    sys.exit(1 if parser.errors else 0)


if __name__ == "__main__":
    main()
