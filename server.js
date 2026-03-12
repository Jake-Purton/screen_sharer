/**
 * screen-share relay server
 *
 * HTTP routes
 *   GET /          → index.html (broadcaster / sender UI)
 *   GET /viewer    → viewer.html
 *   GET /healthz   → JSON health check
 *
 * WebSocket routes
 *   /ws/broadcast  → one active broadcaster
 *   /ws/viewer     → many viewers
 *
 * Stream format
 * ─────────────
 * The sender uses webm-muxer (StreamTarget, chunked:true) which emits one
 * complete WebM Cluster per callback, each cluster beginning on a keyframe.
 *
 * The FIRST binary message received from the broadcaster is the WebM
 * initialisation segment: EBML header + Segment + Info + Tracks + first
 * Cluster.  This is stored as `initChunk` and replayed to every viewer that
 * joins after the stream has already started, so they can start decoding
 * without waiting for the next keyframe.
 *
 * Subsequent binary messages are media segments (individual Clusters) and
 * are kept in a small rolling buffer (`recentChunks`) for fast catch-up.
 */

import { createServer } from 'http';
import { readFileSync } from 'fs';
import { WebSocketServer } from 'ws';

const PORT = parseInt(process.env.PORT ?? '30003', 10);
const HOST = process.env.HOST ?? '0.0.0.0';

const indexHtml    = readFileSync(new URL('./index.html',  import.meta.url));
const viewerHtml   = readFileSync(new URL('./viewer.html', import.meta.url));
const webmMuxerMjs = readFileSync(new URL('./node_modules/webm-muxer/build/webm-muxer.mjs', import.meta.url));

// ── Relay state ──────────────────────────────────────────────────────────────

/** The currently active broadcaster WebSocket (null when nobody is sharing). */
let broadcasterWs = null;

/** All connected viewer WebSockets. */
const viewerSockets = new Set();

/**
 * The first binary frame from the broadcaster: EBML header + Tracks + first
 * Cluster.  Sent to late-joining viewers so they can start decoding cleanly.
 */
let initChunk = null;

/** Rolling buffer of the most recent media chunks for viewer catch-up. */
const recentChunks = [];
const MAX_RECENT   = 10;   // ~1.7 s of video at 167 ms / cluster

// ── HTTP ─────────────────────────────────────────────────────────────────────

const server = createServer((req, res) => {
  if (req.url === '/' || req.url === '/index.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(indexHtml);
  } else if (req.url === '/viewer' || req.url === '/viewer.html') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(viewerHtml);
  } else if (req.url === '/webm-muxer.mjs') {
    res.writeHead(200, { 'Content-Type': 'text/javascript; charset=utf-8', 'Cache-Control': 'public, max-age=86400' });
    res.end(webmMuxerMjs);
  } else if (req.url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ ok: true, viewers: viewerSockets.size }));
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

// ── WebSocket ─────────────────────────────────────────────────────────────────

const wss = new WebSocketServer({ server });

wss.on('connection', (ws, req) => {
  if (req.url === '/ws/broadcast') {
    handleBroadcaster(ws);
  } else if (req.url === '/ws/viewer') {
    handleViewer(ws);
  } else {
    ws.close(4004, 'Unknown path');
  }
});

// ── Broadcaster ───────────────────────────────────────────────────────────────

function handleBroadcaster(ws) {
  // Only one broadcaster allowed; evict any previous one.
  if (broadcasterWs !== null && broadcasterWs.readyState === broadcasterWs.OPEN) {
    broadcasterWs.close(4000, 'Replaced by new broadcaster');
  }
  broadcasterWs = ws;
  initChunk = null;
  recentChunks.length = 0;

  ws.send(JSON.stringify({ type: 'ready', viewers: viewerSockets.size }));
  console.log('Broadcaster connected');

  ws.on('message', (data, isBinary) => {
    if (!isBinary) {
      if (data.toString() === 'ping') ws.send('pong');
      return;
    }

    // Copy to an owned Buffer so the ws receive buffer can be released.
    const chunk = Buffer.from(data);
    console.log(`[Server] Broadcaster sent ${chunk.byteLength} bytes, ${viewerSockets.size} viewer(s) connected`);

    if (!initChunk) {
      // First binary message: WebM init segment + first Cluster.
      console.log('[Server] Storing init chunk');
      initChunk = chunk;
    } else {
      recentChunks.push(chunk);
      if (recentChunks.length > MAX_RECENT) recentChunks.shift();
    }

    // Fan-out to all connected viewers.
    const stale = [];
    for (const viewer of viewerSockets) {
      if (viewer.readyState !== viewer.OPEN) {
        stale.push(viewer);
        continue;
      }
      try {
        viewer.send(chunk, { binary: true });
      } catch (err) {
        console.error('Send to viewer failed:', err.message);
        stale.push(viewer);
      }
    }
    for (const s of stale) viewerSockets.delete(s);
    if (stale.length > 0) {
      console.log(`Removed ${stale.length} stale viewer(s). Remaining: ${viewerSockets.size}`);
    }
  });

  ws.on('close', () => {
    if (broadcasterWs === ws) broadcasterWs = null;
    console.log('Broadcaster disconnected');
  });

  ws.on('error', (err) => console.error('Broadcaster socket error:', err.message));
}

// ── Viewer ────────────────────────────────────────────────────────────────────

function handleViewer(ws) {
  viewerSockets.add(ws);
  console.log(`[Server] Viewer connected. Total: ${viewerSockets.size}`);

  // Replay cached stream data so the viewer can start decoding immediately
  // without waiting for the next keyframe to arrive from the broadcaster.
  if (initChunk && ws.readyState === ws.OPEN) {
    console.log(`[Server] Replaying init chunk (${initChunk.byteLength} bytes) to new viewer`);
    ws.send(initChunk, { binary: true });
    console.log(`[Server] Replaying ${recentChunks.length} recent chunks to new viewer`);
    for (const chunk of recentChunks) {
      if (ws.readyState !== ws.OPEN) break;
      ws.send(chunk, { binary: true });
    }
  } else {
    console.log(`[Server] No init chunk yet (${initChunk ? 'exists' : 'missing'}), viewer will wait`);
  }

  ws.send(JSON.stringify({
    type: 'status',
    broadcasterConnected:
      broadcasterWs !== null && broadcasterWs.readyState === broadcasterWs.OPEN,
  }));

  ws.on('message', (data, isBinary) => {
    if (!isBinary && data.toString() === 'ping') ws.send('pong');
  });

  ws.on('close', () => {
    viewerSockets.delete(ws);
    console.log(`Viewer disconnected. Total: ${viewerSockets.size}`);
  });

  ws.on('error', (err) => console.error('Viewer socket error:', err.message));
}

// ── Start ─────────────────────────────────────────────────────────────────────

server.listen(PORT, HOST, () => {
  const host = HOST === '0.0.0.0' ? 'localhost' : HOST;
  console.log(`Screen-share relay listening on http://${HOST}:${PORT}`);
  console.log(`  Sender : http://${host}:${PORT}/`);
  console.log(`  Viewer : http://${host}:${PORT}/viewer`);
});
