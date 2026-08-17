from app.extensions import db

from app.utils import utc_now





class Community(db.Model):

    __tablename__ = "communities"



    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    name = db.Column(db.String(255), unique=True, nullable=False)

    description = db.Column(db.Text, nullable=True)

    location = db.Column(db.String(255), nullable=True)

    image_url = db.Column(db.String(512), nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)

    experience_level = db.Column(

        db.Enum(

            "less_than_1_year",

            "1_to_3_years",

            "3_plus_years",

            name="community_experience_level",

        ),

        nullable=False,

    )

    specialization = db.Column(db.String(255), nullable=True)

    portfolio_links = db.Column(db.JSON, nullable=True)

    admin_bio = db.Column(db.Text, nullable=True)

    contact_phone = db.Column(db.String(64), nullable=True)

    status = db.Column(

        db.Enum("pending", "approved", "rejected", name="community_status"),

        nullable=False,

        default="pending",

    )

    rejection_reason = db.Column(db.Text, nullable=True)

    reputation_score = db.Column(db.Float, default=0.0, nullable=False)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)



    category = db.relationship("Category", back_populates="communities")

    members = db.relationship("CommunityMember", back_populates="community", lazy="dynamic")

    open_calls = db.relationship("OpenCall", back_populates="community", lazy="dynamic")

    applications = db.relationship(

        "CommunityApplication", back_populates="community", lazy="dynamic"

    )

    contracts = db.relationship("Contract", back_populates="community", lazy="dynamic")



    def approved_member_count(self):

        return self.members.filter_by(status="approved").count()



    def to_dict(self, include_member_count=False, include_category=False):

        data = {

            "id": self.id,

            "name": self.name,

            "description": self.description,

            "location": self.location,

            "image_url": self.image_url,

            "category_id": self.category_id,

            "experience_level": self.experience_level,

            "specialization": self.specialization,

            "portfolio_links": self.portfolio_links or [],

            "admin_bio": self.admin_bio,

            "contact_phone": self.contact_phone,

            "status": self.status,

            "rejection_reason": self.rejection_reason,

            "reputation_score": self.reputation_score,

            "created_at": self.created_at.isoformat() if self.created_at else None,

        }

        if include_member_count:

            data["member_count"] = self.approved_member_count()

        if include_category and self.category:

            data["category"] = self.category.to_dict()

        return data

