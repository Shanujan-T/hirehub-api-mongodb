'use strict';
const jwt = require('jsonwebtoken');
const passwordUtil = require('../utils/password');
const { User, UserSkill, Skill, WorkSample, Contract, Review, publicDoc } = require('../models');
const { jwtSecret, jwtExpiresMinutes } = require('../config');

const tokenFor = id => jwt.sign({}, jwtSecret, { subject: String(id), expiresIn: `${jwtExpiresMinutes}m` });
async function serializeUser(user, { self = false, stats = false, skills = false } = {}) {
  const data = publicDoc(user);
  if (!self) for (const key of ['phone_number','phone_verified_at','email_verified_at','address_line1','address_line2','address_city','address_region','address_postal_code','identity_rejection_reason']) delete data[key];
  if (self) {
    data.email_verified_for_identity = Boolean(user.email_verified_at);
    data.phone_verified_for_identity = Boolean(user.phone_verified_at);
  }
  if (skills) {
    const links = await UserSkill.find({ user_id: user.id }).lean();
    data.user_skills = await Promise.all(links.map(async link => ({ ...publicDoc(link), skill: publicDoc(await Skill.findOne({ id: link.skill_id })), ai_reviewed: Boolean(await WorkSample.exists({ user_skill_id: link.id, verification_status: 'plausible' })) })));
  }
  if (stats) {
    data.completed_project_count = await Contract.countDocuments({ assigned_member_id: user.id, status: 'completed' });
    const rating = await Review.aggregate([{ $match: { member_id: user.id } }, { $group: { _id: null, avg: { $avg: '$rating' } } }]);
    data.rating = rating[0] ? Math.round(rating[0].avg * 100) / 100 : 0;
  }
  return data;
}
async function register(req, res, next) {
  try {
    const data = req.body || {}, errors = [];
    if (!data.email) errors.push('email is required.'); if (!data.password) errors.push('password is required.');
    if (!data.full_name) errors.push('full_name is required.'); if (!['user','employer'].includes(data.role)) errors.push('role is required and must be either user or employer.');
    if (errors.length) return res.status(400).json({ errors });
    const email = String(data.email).trim().toLowerCase(), full_name = String(data.full_name).trim();
    if (!email || !full_name) return res.status(400).json({ errors: ['email and full_name cannot be blank.'] });
    if (await User.exists({ email })) return res.status(409).json({ error: 'Email already registered.' });
    const user = await User.create({ email, full_name, role: data.role, password: await passwordUtil.hash(data.password) });
    return res.status(201).json({ message: 'Registered successfully.', access_token: tokenFor(user.id), user: await serializeUser(user, { self: true, skills: true }) });
  } catch (e) { if (e.code === 11000) return res.status(409).json({ error: 'Email already registered.' }); next(e); }
}
async function login(req, res, next) {
  try {
    const data = req.body || {}, errors = [];
    if (!data.email) errors.push('email is required.'); if (!data.password) errors.push('password is required.');
    if (errors.length) return res.status(400).json({ errors });
    const user = await User.findOne({ email: String(data.email).trim().toLowerCase() });
    if (!user || !(await passwordUtil.verify(data.password, user.password))) return res.status(401).json({ error: 'Invalid email or password.' });
    if (!user.is_active) return res.status(403).json({ error: 'Account suspended.' });
    return res.json({ access_token: tokenFor(user.id), user: await serializeUser(user, { self: true, skills: true }) });
  } catch (e) { next(e); }
}
async function me(req, res, next) { try { if (!req.user.is_active) return res.status(403).json({ error: 'Account suspended.' }); res.json({ user: await serializeUser(req.user, { self: true, stats: true, skills: true }) }); } catch (e) { next(e); } }
module.exports = { register, login, me, serializeUser };
