const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');

let backendProcess;
const BACKEND_TOKEN = process.env.BACKEND_TOKEN || 'dev-token';
const BACKEND_PREFERRED_PORT = process.env.BACKEND_PORT || '8137';
let resolvedPort = BACKEND_PREFERRED_PORT;

function startBackend() {
  return new Promise((resolve, reject) => {
    const pythonExe = process.env.PYTHON || 'python';
    backendProcess = spawn(pythonExe, [path.join(__dirname, '..', 'backend', 'main.py')], {
      env: { ...process.env, BACKEND_TOKEN, BACKEND_PORT: BACKEND_PREFERRED_PORT },
      stdio: ['ignore', 'pipe', 'pipe']
    });
    let detected = false;
    backendProcess.stdout.on('data', (data) => {
      const text = data.toString();
      process.stdout.write('[backend] ' + text);
      const m = text.match(/Listening on 127\.0\.0\.1:(\d+)/);
      if (m) {
        resolvedPort = m[1];
        process.env.ACTUAL_BACKEND_PORT = resolvedPort;
        detected = true;
        resolve(resolvedPort);
      }
    });
    backendProcess.stderr.on('data', (data) => {
      process.stderr.write('[backend-err] ' + data.toString());
    });
    backendProcess.on('exit', (code) => {
      console.log('Backend exited with code', code);
      if (!detected) reject(new Error('Backend exited before port detected'));
    });
    // Fallback timeout if not detected within 3s
    setTimeout(() => {
      if (!detected) {
        console.warn('Port not detected; falling back to preferred', BACKEND_PREFERRED_PORT);
        resolve(BACKEND_PREFERRED_PORT);
      }
    }, 3000);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1000,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      additionalArguments: [`--backend-port=${resolvedPort}`]
    }
  });
  win.loadFile(path.join(__dirname, 'index.html'));
  // Minimize on blur
  win.on('blur', () => {
    if (!win.isDestroyed()) {
      try { win.minimize(); } catch {}
    }
  });
}

app.whenReady().then(() => {
  startBackend()
    .then(() => {
      createWindow();
    })
    .catch(err => {
      console.error('Failed to start backend:', err);
      // still attempt window with preferred port
      createWindow();
    });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});
