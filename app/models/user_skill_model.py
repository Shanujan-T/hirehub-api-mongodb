from app.extensions import db


class UserSkill(db.Model):
    __tablename__ = "user_skills"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skills.id"), nullable=False)
    level = db.Column(
        db.Enum("beginner", "intermediate", "advanced", "expert", name="skill_level"),
        nullable=False,
        default="intermediate",
    )

    __table_args__ = (db.UniqueConstraint("user_id", "skill_id"),)

    user = db.relationship("User", back_populates="user_skills")
    skill = db.relationship("Skill", back_populates="user_skills")
    work_samples = db.relationship(
        "WorkSample",
        back_populates="user_skill",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def has_ai_reviewed(self) -> bool:
        return self.work_samples.filter_by(verification_status="plausible").count() > 0

    def to_dict(self, include_samples=False):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "skill_id": self.skill_id,
            "level": self.level,
            "ai_reviewed": self.has_ai_reviewed(),
        }
        if self.skill:
            data["skill"] = self.skill.to_dict()
        if include_samples:
            samples = sorted(
                self.work_samples.all(),
                key=lambda x: x.created_at or x.id,
                reverse=True,
            )
            data["work_samples"] = [s.to_dict() for s in samples]
        return data
