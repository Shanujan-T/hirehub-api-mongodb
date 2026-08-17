'use strict';

async function resolveSenderEmail(apiKey) {
  const configured = String(process.env.BREVO_FROM_EMAIL || process.env.BREVO_SENDER_EMAIL || '').trim();
  if (configured) return configured;
  const response = await fetch('https://api.brevo.com/v3/senders', {
    headers: { accept: 'application/json', 'api-key': apiKey },
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) return null;
  const payload = await response.json();
  const sender = (payload.senders || []).find(item => item.active !== false && item.email);
  return sender?.email || null;
}

async function sendOtpEmail(to, code) {
  const apiKey = String(process.env.BREVO_API_KEY || '').trim();
  const senderName = String(process.env.BREVO_FROM_NAME || 'HireHub').trim() || 'HireHub';
  if (!apiKey) {
    const error = new Error('Email verification delivery is not configured.');
    error.code = 'EMAIL_NOT_CONFIGURED';
    throw error;
  }
  const senderEmail = await resolveSenderEmail(apiKey);
  if (!senderEmail) {
    const error = new Error('No active Brevo sender is configured.');
    error.code = 'EMAIL_NOT_CONFIGURED';
    throw error;
  }
  const response = await fetch('https://api.brevo.com/v3/smtp/email', {
    method: 'POST',
    headers: { accept: 'application/json', 'api-key': apiKey, 'content-type': 'application/json' },
    body: JSON.stringify({
      sender: { email: senderEmail, name: senderName },
      to: [{ email: to }],
      subject: 'Your HireHub account verification code',
      htmlContent: `Your HireHub account verification code is: <strong>${code}</strong><br><br>It expires in 10 minutes. If you did not request this, you can ignore this email.`,
    }),
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok) {
    const details = await response.text();
    const error = new Error(`Brevo email send failed (${response.status}): ${details.slice(0, 300)}`);
    error.code = 'EMAIL_DELIVERY_FAILED';
    throw error;
  }
}

module.exports = { sendOtpEmail };
