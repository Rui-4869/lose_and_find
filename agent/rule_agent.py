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
        category_match = self._normalize(lost_item.category) == self._normalize(found_item.category)
        location_match = self._normalize(lost_item.location) == self._normalize(found_item.location)
        time_gap_days = self._time_difference_days(lost_item.occurred_at, found_item.occurred_at)
        description_similarity = self._description_similarity(lost_item.description, found_item.description)
        keyword_overlap = self._keyword_overlap(lost_item.description, found_item.description)

        if category_match and location_match and time_gap_days is not None and time_gap_days <= 3:
            return RuleOutcome(
                score=95,
                level=MatchLevel.HIGH,
                reason="类别、地点、时间高度匹配",
            )

        if category_match and (description_similarity >= 0.6 or keyword_overlap >= 2):
            return RuleOutcome(
                score=75,
                level=MatchLevel.MEDIUM,
                reason="类别一致，描述相似",
            )

        if description_similarity >= 0.45 or location_match:
            return RuleOutcome(
                score=55,
                level=MatchLevel.LOW,
                reason="描述或地点存在弱相关",
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
        tokenize = lambda text: {token for token in text.lower().replace("/", " ").split() if token}
        return len(tokenize(first) & tokenize(second))
