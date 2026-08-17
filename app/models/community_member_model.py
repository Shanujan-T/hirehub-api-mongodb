from app.extensions import db
from app.utils import utc_now


class CommunityMember(db.Model):
    __tablename__ = "community_members"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    community_id = db.Column(db.Integer, db.ForeignKey("communities.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(
        db.Enum("admin", "member", name="community_member_role"),
        nullable=False,
        default="member",
    )
    status = db.Column(
        db.Enum("pending", "approved", "rejected", name="community_member_status"),
        nullable=False,
        default="pending",
    )
    joined_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("community_id", "user_id"),)

    community = db.relationship("Community", back_populates="members")
    user = db.relationship("User", back_populates="community_memberships")

    def to_dict(self, include_user=False, include_user_skills=False):
        data = {
            "id": self.id,
            "community_id": self.community_id,
            "user_id": self.user_id,
            "role": self.role,
            "status": self.status,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }
        if self.community:
            data["community"] = {
                "id": self.community.id,
                "name": self.community.name,
                "status": self.community.status,
                "rejection_reason": self.community.rejection_reason,
                "experience_level": self.community.experience_level,
                "location": self.community.location,
                "image_url": self.community.image_url,
            }
        if include_user and self.user:
            data["user"] = self.user.to_dict(
                include_stats=True,
                include_skills=include_user_skills,
            )
        return data
