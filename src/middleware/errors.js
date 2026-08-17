'use strict';
function notFound(_req, res) { res.status(404).json({ error: 'Not found.' }); }
function errorHandler(err, _req, res, _next) {
  if (err && err.code === 11000) return res.status(409).json({ error: 'Duplicate data.' });
  console.error(err);
  if (err && (err.name === 'MongoServerSelectionError' || err.name === 'MongoNetworkError')) return res.status(503).json({ error: 'Database connection error.', details: null });
  return res.status(err.status || 500).json({ error: err.publicMessage || 'Internal server error.' });
}
module.exports = { notFound, errorHandler };
