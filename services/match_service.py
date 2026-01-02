from datetime import UTC, datetime
from typing import Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models import FoundItem, LostItem, MatchLevel, MatchResult


class MatchService:
    def __init__(self, session: Session):
        self._session = session

    # Data access helpers
    def all_found_items(self, user_id: Optional[int] = None, include_all: bool = False) -> List[FoundItem]:
        query = FoundItem.query.order_by(FoundItem.occurred_at.desc())
        if user_id is not None and not include_all:
            query = query.filter_by(user_id=user_id)
        return query.all()

    def all_lost_items(self, user_id: Optional[int] = None, include_all: bool = False) -> List[LostItem]:
        query = LostItem.query.order_by(LostItem.occurred_at.desc())
        if user_id is not None and not include_all:
            query = query.filter_by(user_id=user_id)
        return query.all()

    def matches_for_lost(self, lost_id: int) -> List[MatchResult]:
        return (
            MatchResult.query.filter_by(lost_item_id=lost_id)
            .order_by(MatchResult.is_completed.asc(), MatchResult.score.desc(), MatchResult.updated_at.desc())
            .all()
        )

    def matches_for_found(self, found_id: int) -> List[MatchResult]:
        return (
            MatchResult.query.filter_by(found_item_id=found_id)
            .order_by(MatchResult.is_completed.asc(), MatchResult.score.desc(), MatchResult.updated_at.desc())
            .all()
        )

    def recent_matches(self, limit: int = 10) -> List[MatchResult]:
        return (
            MatchResult.query.order_by(MatchResult.is_completed.asc(), MatchResult.score.desc(), MatchResult.updated_at.desc())
            .limit(limit)
            .all()
        )

    def matches_for_user(self, user_id: int, limit: int = 10) -> List[MatchResult]:
        return (
            MatchResult.query.join(MatchResult.lost_item)
            .join(MatchResult.found_item)
            .filter(or_(LostItem.user_id == user_id, FoundItem.user_id == user_id))
            .order_by(MatchResult.is_completed.asc(), MatchResult.score.desc(), MatchResult.updated_at.desc())
            .limit(limit)
            .all()
        )

    def upsert_match(
        self,
        lost_item: LostItem,
        found_item: FoundItem,
        score: int,
        level: str,
        reason: Optional[str] = None,
    ) -> MatchResult:
        match = (
            MatchResult.query.filter_by(
                lost_item_id=lost_item.id,
                found_item_id=found_item.id,
            ).first()
        )
        if match is None:
            match = MatchResult(
                lost_item=lost_item,
                found_item=found_item,
                score=score,
                level=level,
                reason=reason,
            )
            self._session.add(match)
        elif match.is_completed:
            return match
        else:
            match.score = score
            match.level = level
            match.reason = reason
        return match

    def bulk_persist(self, matches: Iterable[MatchResult]) -> List[MatchResult]:
        # SQLAlchemy will flush on commit; returning list for caller convenience.
        persisted = list(matches)
        self._session.commit()
        return persisted

    def clear_matches_for_lost(self, lost_id: int) -> None:
        MatchResult.query.filter_by(lost_item_id=lost_id).delete()
        self._session.commit()

    def clear_matches_for_found(self, found_id: int) -> None:
        MatchResult.query.filter_by(found_item_id=found_id).delete()
        self._session.commit()

    def delete_lost_item(self, lost_id: int) -> None:
        item = self._session.get(LostItem, lost_id)
        if item:
            self._session.delete(item)
            self._session.commit()

    def delete_found_item(self, found_id: int) -> None:
        item = self._session.get(FoundItem, found_id)
        if item:
            self._session.delete(item)
            self._session.commit()

    def mark_match_completed(self, match_id: int) -> Optional[MatchResult]:
        match = self._session.get(MatchResult, match_id)
        if match is None:
            return None
        if not match.is_completed:
            match.is_completed = True
            match.completed_at = datetime.now(UTC)
            self._session.commit()
        return match

    def owns_lost_item(self, lost_id: int, user_id: int) -> bool:
        item = self._session.get(LostItem, lost_id)
        return bool(item and item.user_id == user_id)

    def owns_found_item(self, found_id: int, user_id: int) -> bool:
        item = self._session.get(FoundItem, found_id)
        return bool(item and item.user_id == user_id)
