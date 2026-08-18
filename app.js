'use strict';
const http = require('node:http');
const express = require('express');
const cors = require('cors');
const fileUpload = require('express-fileupload');
const { Server } = require('socket.io');
const { connectDatabase, databaseState } = require('./src/config/database');
const { port, mongodbRetryDelayMs } = require('./src/config');
const routes = require('./src/routes');
const { notFound, errorHandler } = require('./src/middleware/errors');
const { registerSocket } = require('./src/socket');
const { startSchedulers } = require('./src/scheduler');

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
function start() {
  const app = createApp();
  const server = http.createServer(app);
  const io = new Server(server, { cors: corsOptions });
  app.set('io', io);
  registerSocket(io);
  server.on('error', error => {
    console.error(`HTTP server error (${error.code || 'unknown'}): ${error.message}`);
  });
  server.listen(port, '0.0.0.0', () => {
    console.log(`HireHub API listening on 0.0.0.0:${port}`);
  });

  let retryTimer = null;
  let schedulerStarted = false;
  const connectWithRetry = async () => {
    try {
      await connectDatabase();
      console.log('MongoDB connected.');
      if (!schedulerStarted) {
        startSchedulers();
        schedulerStarted = true;
      }
    } catch (error) {
      console.error(`MongoDB connection failed: ${error.message}`);
      console.error(`Retrying MongoDB connection in ${mongodbRetryDelayMs}ms.`);
      retryTimer = setTimeout(connectWithRetry, mongodbRetryDelayMs);
      retryTimer.unref();
    }
  };
  void connectWithRetry();

  const shutdown = signal => {
    console.log(`${signal} received; shutting down.`);
    if (retryTimer) clearTimeout(retryTimer);
    server.close(() => process.exit(0));
  };
  process.once('SIGTERM', () => shutdown('SIGTERM'));
  process.once('SIGINT', () => shutdown('SIGINT'));
  return server;
}
const app = createApp();

if (require.main === module) start();

module.exports = app;
module.exports.createApp = createApp;
module.exports.start = start;
