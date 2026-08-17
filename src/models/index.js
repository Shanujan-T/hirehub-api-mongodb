'use strict';
const mongoose = require('mongoose');

const { Schema } = mongoose;
const counterSchema = new Schema({ name: { type: String, unique: true }, value: { type: Number, default: 0 } });
const Counter = mongoose.models.Counter || mongoose.model('Counter', counterSchema);

function numericId(schema, name) {
  schema.add({ id: { type: Number, unique: true, index: true } });
  schema.pre('save', async function setId() {
    if (this.id != null) return;
    const counter = await Counter.findOneAndUpdate(
      { name }, { $inc: { value: 1 } }, { upsert: true, new: true, setDefaultsOnInsert: true }
    );
    this.id = counter.value;
  });
}

const options = { versionKey: false, timestamps: { createdAt: 'created_at', updatedAt: false }, strict: false };
const schema = (fields, name, indexes = []) => {
  const s = new Schema(fields, options);
  numericId(s, name);
  indexes.forEach(([keys, opts]) => s.index(keys, opts));
  return s;
};
const date = v => (v ? new Date(v).toISOString() : null);
function publicDoc(doc) {
  if (!doc) return null;
  const value = doc.toObject ? doc.toObject() : { ...doc };
  delete value._id; delete value.password; delete value.__v;
  for (const [key, val] of Object.entries(value)) if (val instanceof Date) value[key] = date(val);
  return value;
}

const User = mongoose.model('User', schema({
  email: { type: String, required: true, lowercase: true, trim: true, unique: true },
  password: { type: String, required: true }, role: { type: String, enum: ['admin', 'user', 'employer'], default: 'user' },
  full_name: { type: String, required: true, trim: true }, bio: String, location: String,
  address_line1: String, address_line2: String, address_city: String, address_region: String, address_postal_code: String,
  avatar_url: String, phone_number: String, phone_verified_at: Date, email_verified_at: Date,
  nic_number: String, nic_document_url: String,
  identity_status: { type: String, enum: ['unverified', 'pending', 'verified', 'rejected'], default: 'unverified' },
  identity_rejection_reason: String, is_active: { type: Boolean, default: true },
}, 'users'));

const Skill = mongoose.model('Skill', schema({ name: { type: String, required: true, unique: true, trim: true }, category: String }, 'skills'));
const UserSkill = mongoose.model('UserSkill', schema({ user_id: { type: Number, required: true }, skill_id: { type: Number, required: true }, level: { type: String, enum: ['beginner','intermediate','advanced','expert'], default: 'intermediate' } }, 'user_skills', [[{ user_id: 1, skill_id: 1 }, { unique: true }]]));
const WorkSample = mongoose.model('WorkSample', schema({ user_skill_id: { type: Number, required: true }, sample_type: { type: String, enum: ['text','image'], required: true }, content: { type: String, required: true }, ai_assessment: String, verification_status: { type: String, enum: ['unreviewed','plausible','unclear'], default: 'unreviewed' } }, 'work_samples'));
const Category = mongoose.model('Category', schema({ name: { type: String, required: true, unique: true }, description: String, status: { type: String, enum: ['pending','approved','rejected'], default: 'approved' }, requested_by_id: Number, rejection_reason: String, scope_schema: Schema.Types.Mixed, baseline_price: Number, baseline_scope_key: String }, 'categories'));
const CategoryPricing = mongoose.model('CategoryPricing', schema({ category_id: { type: Number, required: true }, location: String, min_price: Number, max_price: Number, average_price: Number, currency: { type: String, default: 'LKR' }, unit: String }, 'category_pricing'));
const PricingReference = mongoose.model('PricingReference', schema({ category: { type: String, required: true }, scope: { type: String, required: true }, unit: { type: String, required: true }, quantity: { type: Number, required: true }, base_price: { type: Number, required: true }, district_prices: { type: Schema.Types.Mixed, default: {} } }, 'pricing_references'));
const Community = mongoose.model('Community', schema({ admin_id: { type: Number, required: true }, name: { type: String, required: true }, description: String, category_id: Number, location: String, image_url: String, status: { type: String, default: 'pending' }, verification_status: { type: String, default: 'unverified' }, reputation_score: { type: Number, default: 0 }, weekly_digest: String }, 'communities'));
const CommunityMember = mongoose.model('CommunityMember', schema({ community_id: { type: Number, required: true }, user_id: { type: Number, required: true }, role: { type: String, default: 'member' }, status: { type: String, default: 'pending' } }, 'community_members', [[{ community_id: 1, user_id: 1 }, { unique: true }]]));
const Job = mongoose.model('Job', schema({ posted_by_id: { type: Number, required: true }, category_id: { type: Number, required: true }, title: { type: String, required: true }, description: { type: String, required: true }, location: String, deadline: Date, event_time: String, suggested_price: Number, final_price: Number, status: { type: String, default: 'open' }, scope_data: Schema.Types.Mixed }, 'jobs'));
const CommunityApplication = mongoose.model('CommunityApplication', schema({ job_id: Number, community_id: Number, applied_by_id: Number, status: { type: String, default: 'pending' }, source: { type: String, default: 'application' }, bid_amount: Number, proposal: String, commission_percent: Number }, 'community_applications', [[{ job_id: 1, community_id: 1 }, { unique: true }]]));
const Contract = mongoose.model('Contract', schema({ job_id: Number, community_id: Number, assigned_member_id: Number, status: { type: String, default: 'pending' }, agreed_price: Number, commission_percent: Number, deliverable_url: String, deliverable_notes: String, submitted_at: Date, admin_approved_at: Date, poster_approved_at: Date, health_status: String, health_reason: String, health_scored_at: Date }, 'contracts'));
const ContractApplication = mongoose.model('ContractApplication', schema({ contract_id: Number, member_id: Number, status: { type: String, default: 'pending' }, proposal: String, requested_payout: Number, origin: String }, 'contract_applications', [[{ contract_id: 1, member_id: 1 }, { unique: true }]]));
const Conversation = mongoose.model('Conversation', schema({ contract_id: { type: Number, unique: true }, created_by_id: Number }, 'conversations'));
const Message = mongoose.model('Message', schema({ conversation_id: Number, sender_id: Number, content: String, deleted_for: { type: [Number], default: [] }, deleted_for_everyone: { type: Boolean, default: false }, deleted_at: Date }, 'messages'));
const Notification = mongoose.model('Notification', schema({ user_id: Number, type: String, title: String, message: String, body: String, related_entity_type: String, related_entity_id: Number, link_href: String, read_at: Date }, 'notifications'));
const OpenCall = mongoose.model('OpenCall', schema({ community_id: Number, title: String, description: String, status: { type: String, default: 'open' } }, 'open_calls'));
const OpenCallSkill = mongoose.model('OpenCallSkill', schema({ open_call_id: Number, skill_id: Number }, 'open_call_skills', [[{ open_call_id: 1, skill_id: 1 }, { unique: true }]]));
const Payment = mongoose.model('Payment', schema({ contract_id: { type: Number, unique: true }, total_amount: Number, commission_amount: Number, commission_recipient: { type: String, default: 'admin' }, member_payout: Number, status: { type: String, default: 'pending' }, released_at: Date }, 'payments'));
const Review = mongoose.model('Review', schema({ contract_id: { type: Number, unique: true }, reviewer_id: Number, community_id: Number, member_id: Number, rating: Number, comment: String }, 'reviews'));
const Report = mongoose.model('Report', schema({ reporter_id: Number, reporter_role: String, target_type: { type: String, enum: ['user','employer','community'] }, target_id: Number, reason: String, description: String, evidence_url: String, status: { type: String, default: 'open' }, resolution_notes: String, resolved_by: Number, resolved_at: Date }, 'reports', [[{ status: 1, target_type: 1, reason: 1 }, {}]]));
const VerificationOtp = mongoose.model('VerificationOtp', schema({ user_id: Number, purpose: String, code_hash: String, expires_at: Date }, 'verification_otps'));
const AiMatchBlurb = mongoose.model('AiMatchBlurb', schema({ job_id: Number, community_id: Number, text: String, score: Number }, 'ai_match_blurbs'));
const AiReviewDigest = mongoose.model('AiReviewDigest', schema({ community_id: { type: Number, unique: true }, digest: Schema.Types.Mixed }, 'ai_review_digests'));

module.exports = { Counter, User, Skill, UserSkill, WorkSample, Category, CategoryPricing, PricingReference, Community, CommunityMember, Job, CommunityApplication, Contract, ContractApplication, Conversation, Message, Notification, OpenCall, OpenCallSkill, Payment, Review, Report, VerificationOtp, AiMatchBlurb, AiReviewDigest, publicDoc };
