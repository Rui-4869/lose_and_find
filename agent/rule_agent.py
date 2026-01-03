from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Iterable, List, Optional

from models import FoundItem, LostItem, MatchLevel, MatchResult
from services import MatchService


@dataclass
class RuleOutcome:
    score: int
    level: str
    reason: str


class RuleBasedAgent:
    """Rule-driven agent handling perception, decision, and action phases."""

    def __init__(self, match_service: MatchService):
        self._service = match_service

    # Public orchestrators -------------------------------------------------
    def handle_new_lost(self, lost_item: LostItem) -> List[MatchResult]:
        candidates = self._perceive_found_items()
        decisions = self._evaluate_pairs(((lost_item, found) for found in candidates))
        return self._act(decisions)

    def handle_new_found(self, found_item: FoundItem) -> List[MatchResult]:
        candidates = self._perceive_lost_items()
        decisions = self._evaluate_pairs(((lost, found_item) for lost in candidates))
        return self._act(decisions)

    # Perception -----------------------------------------------------------
    def _perceive_found_items(self) -> Iterable[FoundItem]:
        return self._service.all_found_items()

    def _perceive_lost_items(self) -> Iterable[LostItem]:
        return self._service.all_lost_items()

    # Decision -------------------------------------------------------------
    def _evaluate_pairs(self, pairs: Iterable[tuple[LostItem, FoundItem]]):
        for lost_item, found_item in pairs:
            outcome = self._decide(lost_item, found_item)
            if outcome is None:
                continue
            yield lost_item, found_item, outcome

    def _decide(self, lost_item: LostItem, found_item: FoundItem) -> Optional[RuleOutcome]:
        """
        Enhanced decision strategy with weighted scoring:
        - Category match: 最关键因素 (weight: 40)
        - Location match: 重要因素 (weight: 30)
        - Time proximity: 时间相关性 (weight: 15)
        - Description similarity: 描述相似性 (weight: 15)
        """
        category_match = self._normalize(lost_item.category) == self._normalize(found_item.category)
        location_match = self._normalize(lost_item.location) == self._normalize(found_item.location)
        time_gap_days = self._time_difference_days(lost_item.occurred_at, found_item.occurred_at)
        description_similarity = self._description_similarity(lost_item.description, found_item.description)
        keyword_overlap = self._keyword_overlap(lost_item.description, found_item.description)
        
        # Rule 1: Perfect match - 类别 + 地点 + 时间接近
        if category_match and location_match and time_gap_days is not None and time_gap_days <= 2:
            return RuleOutcome(
                score=98,
                level=MatchLevel.HIGH,
                reason="类别完全匹配，地点相同，时间差不超过2天",
            )
        
        # Rule 2: Strong match - 类别 + 地点 + 描述相似
        if category_match and location_match and description_similarity >= 0.5:
            return RuleOutcome(
                score=90,
                level=MatchLevel.HIGH,
                reason="类别与地点完全匹配，描述相似度高",
            )
        
        # Rule 3: Category + description relevance
        if category_match and (description_similarity >= 0.65 or keyword_overlap >= 3):
            return RuleOutcome(
                score=80,
                level=MatchLevel.MEDIUM,
                reason="类别一致，描述相似或关键词重合度高",
            )
        
        # Rule 4: Category + location match
        if category_match and location_match and time_gap_days is not None and time_gap_days <= 7:
            return RuleOutcome(
                score=75,
                level=MatchLevel.MEDIUM,
                reason="类别与地点匹配，时间差在7天内",
            )
        
        # Rule 5: Category match with moderate time gap
        if category_match and time_gap_days is not None and time_gap_days <= 5 and keyword_overlap >= 1:
            return RuleOutcome(
                score=70,
                level=MatchLevel.MEDIUM,
                reason="类别相符，时间差合理，描述有关键词重合",
            )
        
        # Rule 6: Strong description match and location match
        if description_similarity >= 0.6 and location_match:
            return RuleOutcome(
                score=65,
                level=MatchLevel.MEDIUM,
                reason="描述相似度高，地点相同",
            )
        
        # Rule 7: Moderate matches - weak relevance
        if (category_match and description_similarity >= 0.4) or \
           (description_similarity >= 0.5 and keyword_overlap >= 2):
            return RuleOutcome(
                score=55,
                level=MatchLevel.LOW,
                reason="类别或描述存在相关性",
            )
        
        # Rule 8: Location alone is not enough
        if location_match and keyword_overlap >= 2 and description_similarity >= 0.35:
            return RuleOutcome(
                score=45,
                level=MatchLevel.LOW,
                reason="地点相同，描述有弱相关",
            )

        return None

    # Action ---------------------------------------------------------------
    def _act(self, decisions: Iterable[tuple[LostItem, FoundItem, RuleOutcome]]):
        persisted: List[MatchResult] = []
        for lost_item, found_item, outcome in decisions:
            match = self._service.upsert_match(
                lost_item=lost_item,
                found_item=found_item,
                score=outcome.score,
                level=outcome.level,
                reason=outcome.reason,
            )
            persisted.append(match)
        if persisted:
            self._service.bulk_persist(persisted)
        return persisted

    # Utility helpers ------------------------------------------------------
    @staticmethod
    def _normalize(value: Optional[str]) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def _time_difference_days(first: Optional[datetime], second: Optional[datetime]) -> Optional[int]:
        if not first or not second:
            return None
        return abs((first - second).days)

    @staticmethod
    def _description_similarity(first: str, second: str) -> float:
        return SequenceMatcher(a=first.lower(), b=second.lower()).ratio()

    @staticmethod
    def _keyword_overlap(first: str, second: str) -> int:
        import re
        def tokenize(text: str):
            if not text:
                return set()
            text = text.lower()
            # capture CJK character runs and alphanumeric tokens for broader language support
            tokens = set(re.findall(r'[\u4e00-\u9fff]+|[a-z0-9]+', text))
            # augment CJK runs with substrings (length 2..6) to catch multi-character keywords
            cjk_runs = re.findall(r'[\u4e00-\u9fff]+', text)
            for run in cjk_runs:
                length = len(run)
                maxlen = min(6, length)
                for i in range(length):
                    for l in range(2, maxlen + 1):
                        if i + l <= length:
                            tokens.add(run[i : i + l])
            return tokens
        return len(tokenize(first) & tokenize(second))
