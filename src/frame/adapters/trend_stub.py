"""공식 데이터 API를 연결하려면 TrendSource.fetch를 구현해 교체하세요."""


class StubTrendSource:
    def fetch(self, region: str, keywords: list[str]) -> list[dict]:
        print("N1/N2 모듈은 비어 있습니다 — modules/N1-trend.md를 보고 맡아 주세요 (네이버 데이터랩 API 등)")
        return []
