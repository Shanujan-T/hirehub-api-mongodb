'use strict';
const http = require('node:http');
const express = require('express');
const cors = require('cors');
const fileUpload = require('express-fileupload');
const { Server } = require('socket.io');
const { connectDatabase } = require('./src/config/database');
const { port, clientUrl } = require('./src/config');
const routes = require('./src/routes');
const { notFound, errorHandler } = require('./src/middleware/errors');
const { registerSocket } = require('./src/socket');
const { startSchedulers } = require('./src/scheduler');
function createApp() {
  const app = express();
  app.disable('x-powered-by');
  app.use(cors({ origin: clientUrl === '*' ? true : clientUrl, credentials: true }));
  app.use(express.json({ limit: '2mb' }));
  app.use(express.urlencoded({ extended: true }));
  app.use(fileUpload({ limits: { fileSize: 10 * 1024 * 1024 }, abortOnLimit: true }));
  app.get('/', (_req, res) => res.json({ api: 'HireHub API', version: '1.0', database: 'MongoDB' }));
  app.get('/health', (_req, res) => res.json({ status: 'ok' }));
  app.use('/api', routes);
  app.use(notFound);
  app.use(errorHandler);
  return app;
}
async function start() {
  await connectDatabase();
  const app = createApp();
  const server = http.createServer(app);
  const io = new Server(server, { cors: { origin: clientUrl === '*' ? true : clientUrl } });
  app.set('io', io);
  registerSocket(io);
  startSchedulers();
  server.listen(port, '0.0.0.0', () => console.log(`HireHub API listening on http://localhost:${port}`));
  return server;
}
if (require.main === module) start().catch(error => { console.error(`Failed to start HireHub API: ${error.message}`); process.exit(1); });
module.exports = { createApp, start };
