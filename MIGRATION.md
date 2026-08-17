# Flask/MySQL to Express/MongoDB migration

The API entry point is `app.js`. Routes, controllers, middleware, models,
services, and utilities live under `src/`. Existing public numeric `id` fields
are retained alongside MongoDB `_id` values so client URLs and JSON contracts
remain compatible.

## Commands

```text
npm install
npm run seed
npm run dev
npm test
```

## Environment keys

Required: `MONGODB_URI`, `JWT_SECRET_KEY`.

Runtime: `PORT`, `CLIENT_URL`, `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`,
`MONGODB_DNS_SERVERS`, `OTP_PEPPER`.

Optional integrations: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`,
`OPENROUTER_APP_TITLE`, `OPENROUTER_HTTP_REFERER`, `CLOUDINARY_CLOUD_NAME`,
`CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, `BREVO_API_KEY`,
`BREVO_FROM_EMAIL` (or `BREVO_SENDER_EMAIL`), `BREVO_FROM_NAME`,
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`,
`TWILIO_FROM_NUMBER`, and `LOCAL_UPLOADS_ENABLED`.

No URI, credential, or API key is hardcoded. Existing Werkzeug password hashes
remain accepted during login; newly created passwords use bcrypt.

## Data-model note

SQL foreign keys are represented by indexed numeric compatibility IDs. This is
intentional: embedding would change update/delete behavior and public response
shapes. Compound unique indexes preserve join-table constraints.

## Behavioral differences

MongoDB cannot provide SQL foreign-key enforcement. Controllers validate
referenced records and perform dependent deletes explicitly. Multi-document
operations use ordered writes; deployments configured as replica sets can be
extended to wrap these operations in transactions without changing contracts.
