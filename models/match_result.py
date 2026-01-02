from datetime import UTC, datetime

from database import db


class MatchLevel:
    HIGH = "高匹配"
    MEDIUM = "中匹配"
    LOW = "低匹配"

    @classmethod
    def ordered_levels(cls):
        return [cls.HIGH, cls.MEDIUM, cls.LOW]


def _now_utc():
    return datetime.now(UTC)


class MatchResult(db.Model):
    __tablename__ = "match_results"
    __table_args__ = (
        db.UniqueConstraint("lost_item_id", "found_item_id", name="uq_match_pair"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lost_item_id = db.Column(db.Integer, db.ForeignKey("lost_items.id"), nullable=False)
    found_item_id = db.Column(db.Integer, db.ForeignKey("found_items.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    level = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    is_completed = db.Column(db.Boolean, nullable=False, default=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False)

    lost_item = db.relationship("LostItem", back_populates="matches")
    found_item = db.relationship("FoundItem", back_populates="matches")

    def to_dict(self):
        return {
            "id": self.id,
            "lost_item": self.lost_item,
            "found_item": self.found_item,
            "score": self.score,
            "level": self.level,
            "reason": self.reason,
            "is_completed": self.is_completed,
            "completed_at": self.completed_at,
        }
