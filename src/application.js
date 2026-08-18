'use strict';
const express = require('express');
const cors = require('cors');
const fileUpload = require('express-fileupload');
const { connectDatabase, databaseState } = require('./config/database');
const routes = require('./routes');
const { notFound, errorHandler } = require('./middleware/errors');

const defaultAllowedOrigins = [
  'http://localhost:5173',
  'https://hirehub-client-mongodb.vercel.app',
];
const allowedOrigins = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(',').map(origin => origin.trim()).filter(Boolean)
  : defaultAllowedOrigins;
const corsOptions = {
  origin(origin, callback) {
    if (!origin || allowedOrigins.includes(origin)) return callback(null, true);
    return callback(new Error('Not allowed by CORS'));
  },
  credentials: true,
};

function createApp() {
  const app = express();
  app.set('corsOptions', corsOptions);
  app.disable('x-powered-by');
  app.use(cors(corsOptions));
  app.use(express.json({ limit: '2mb' }));
  app.use(express.urlencoded({ extended: true }));
  app.use(fileUpload({ limits: { fileSize: 10 * 1024 * 1024 }, abortOnLimit: true }));
  app.get('/', (_req, res) => res.json({ api: 'HireHub API', version: '1.0', database: 'MongoDB' }));
  app.get('/health', (_req, res) => res.json({ status: 'ok' }));
  app.get('/ready', (_req, res) => {
    const database = databaseState();
    return res.status(database.ready ? 200 : 503).json({
      status: database.ready ? 'ready' : 'not_ready',
      database: database.state,
    });
  });
  app.use(async (_req, _res, next) => {
    try {
      await connectDatabase();
      next();
    } catch (error) {
      next(error);
    }
  });
  app.use('/api', routes);
  app.use(notFound);
  app.use(errorHandler);
  return app;
}
const app = createApp();

module.exports = app;
