'use strict';
const crypto = require('node:crypto');
const { VerificationOtp } = require('../models');
const { serializeUser } = require('./authController');
const { sendOtpEmail } = require('../services/emailService');

const PURPOSE = 'identity_email';
const TTL_MS = 10 * 60 * 1000;
const otpHash = code => crypto.createHash('sha256').update(`${process.env.OTP_PEPPER || process.env.JWT_SECRET_KEY || 'dev-secret-key'}:${String(code).trim()}`).digest('hex');
const safeEqual = (left, right) => {
  const a = Buffer.from(left || '', 'utf8'), b = Buffer.from(right || '', 'utf8');
  return a.length === b.length && crypto.timingSafeEqual(a, b);
};

async function sendEmailOtp(req, res, next) {
  try {
    if (req.user.identity_status === 'verified') return res.status(400).json({ error: 'Account is already verified.' });
    if (!process.env.BREVO_API_KEY) {
      return res.status(503).json({ error: 'Email verification delivery is not configured.' });
    }
    const code = crypto.randomInt(0, 1_000_000).toString().padStart(6, '0');
    await VerificationOtp.deleteMany({ user_id: req.userId, purpose: PURPOSE });
    const otp = await VerificationOtp.create({ user_id: req.userId, purpose: PURPOSE, code_hash: otpHash(code), expires_at: new Date(Date.now() + TTL_MS) });
    try {
      await sendOtpEmail(req.user.email, code);
    } catch (error) {
      await otp.deleteOne();
      if (error.code === 'EMAIL_NOT_CONFIGURED') return res.status(503).json({ error: 'Email verification delivery is not configured.' });
      console.error('Failed to send identity email OTP:', error.message);
      return res.status(502).json({ error: 'Failed to send email verification code.' });
    }
    return res.json({ message: 'Verification code sent to your email.' });
  } catch (error) { next(error); }
}

async function confirmEmailOtp(req, res, next) {
  try {
    if (req.user.identity_status === 'verified') return res.status(400).json({ error: 'Account is already verified.' });
    const code = String(req.body?.code || '').trim();
    if (!code) return res.status(400).json({ errors: ['code is required.'] });
    const otp = await VerificationOtp.findOne({ user_id: req.userId, purpose: PURPOSE }).sort({ created_at: -1 });
    if (!otp || otp.expires_at < new Date() || !safeEqual(otpHash(code), otp.code_hash)) {
      return res.status(400).json({ error: 'Invalid or expired verification code.' });
    }
    await VerificationOtp.deleteMany({ user_id: req.userId, purpose: PURPOSE });
    req.user.email_verified_at = new Date();
    req.user.identity_status = 'verified';
    req.user.identity_rejection_reason = null;
    await req.user.save();
    return res.json({ message: 'Account verification updated.', user: await serializeUser(req.user, { self: true, stats: true }) });
  } catch (error) { next(error); }
}

const normalizePhone=value=>{let phone=String(value||'').replace(/[\s\-()]/g,'');if(phone.startsWith('00'))phone=`+${phone.slice(2)}`;if(!phone.startsWith('+'))phone=`+${phone}`;return /^\+[0-9]{8,15}$/.test(phone)?phone:null;};
const twilioConfigured=()=>Boolean(process.env.TWILIO_ACCOUNT_SID&&process.env.TWILIO_AUTH_TOKEN&&process.env.TWILIO_VERIFY_SERVICE_SID);
async function twilio(path,body){const auth=Buffer.from(`${process.env.TWILIO_ACCOUNT_SID}:${process.env.TWILIO_AUTH_TOKEN}`).toString('base64'),response=await fetch(`https://verify.twilio.com/v2/Services/${process.env.TWILIO_VERIFY_SERVICE_SID}/${path}`,{method:'POST',headers:{Authorization:`Basic ${auth}`,'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(body),signal:AbortSignal.timeout(15000)});const data=await response.json();if(!response.ok)throw new Error(data.message||'Twilio request failed.');return data;}
async function sendPhoneOtp(req,res,next){try{if(req.user.identity_status==='verified')return res.status(400).json({error:'Account is already verified.'});const phone=normalizePhone(req.body.phone_number);if(!phone)return res.status(400).json({errors:['phone_number is invalid.']});if(!twilioConfigured())return res.status(503).json({error:'Phone verification delivery is not configured.'});await twilio('Verifications',{To:phone,Channel:'sms'});req.user.phone_number=phone;await req.user.save();res.json({message:'Verification code sent via SMS.'});}catch(e){console.error(e.message);res.status(400).json({error:"Couldn't send code, please check the number and try again."});}}
async function confirmPhoneOtp(req,res,next){try{if(req.user.identity_status==='verified')return res.status(400).json({error:'Account is already verified.'});const code=String(req.body.code||'').trim();if(!code)return res.status(400).json({errors:['code is required.']});if(!req.user.phone_number)return res.status(400).json({error:'No phone number associated with this request. Please send a code first.'});if(!twilioConfigured())return res.status(503).json({error:'Phone verification delivery is not configured.'});const result=await twilio('VerificationCheck',{To:req.user.phone_number,Code:code});if(result.status!=='approved')return res.status(400).json({error:'Invalid or expired verification code.'});req.user.phone_verified_at=new Date();req.user.identity_status='verified';req.user.identity_rejection_reason=null;await req.user.save();res.json({message:'Account verification updated.',user:await serializeUser(req.user,{self:true,stats:true})});}catch(e){console.error(e.message);res.status(400).json({error:'Failed to confirm phone verification, please try again.'});}}

module.exports = { sendEmailOtp, confirmEmailOtp, sendPhoneOtp, confirmPhoneOtp };
