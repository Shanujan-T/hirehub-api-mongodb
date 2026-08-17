import json

from app.extensions import db
from app.utils import utc_now
from app.utils.scope_utils import format_scope_display, parse_json_value


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(255), nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    # Photography jobs use deadline as the event date and retain this separate
    # local event time without changing delivery-deadline behavior elsewhere.
    event_time = db.Column(db.Time, nullable=True)
    suggested_price = db.Column(db.Numeric(10, 2), nullable=True)
    final_price = db.Column(db.Numeric(10, 2), nullable=False)
    scope_data = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("open", "assigned", "closed", name="job_status"),
        nullable=False,
        default="open",
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    poster = db.relationship("User", back_populates="jobs")
    category = db.relationship("Category", back_populates="jobs")
    applications = db.relationship(
        "CommunityApplication", back_populates="job", lazy="dynamic"
    )
    contract = db.relationship("Contract", back_populates="job", uselist=False)

    def get_scope_data(self):
        data = parse_json_value(self.scope_data)
        return data if isinstance(data, dict) else None

    def set_scope_data(self, value):
        if value is None:
            self.scope_data = None
        else:
            self.scope_data = json.dumps(value, ensure_ascii=False)

    def to_dict(self, include_poster=False, strip_poster=False, application_count=None):
        scope_data = self.get_scope_data()
        schema = self.category.get_scope_schema() if self.category else None
        if application_count is None:
            application_count = self.applications.count()
        data = {
            "id": self.id,
            "category_id": self.category_id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "event_time": self.event_time.strftime("%H:%M") if self.event_time else None,
            "suggested_price": float(self.suggested_price) if self.suggested_price else None,
            "final_price": float(self.final_price) if self.final_price else 0,
            "scope_data": scope_data,
            "scope_display": format_scope_display(schema, scope_data),
            "status": self.status,
            "application_count": int(application_count or 0),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if not strip_poster:
            data["posted_by_id"] = self.posted_by_id
        if include_poster and self.poster and not strip_poster:
            data["poster"] = {
                "id": self.poster.id,
                "full_name": self.poster.full_name,
                "location": self.poster.location,
            }
        if self.category:
            data["category"] = self.category.to_dict()
        return data
