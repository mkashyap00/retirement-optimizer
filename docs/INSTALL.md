# Installation Guide

This guide walks you through installing and running Retirement Optimizer on your personal computer. No programming experience is required.

---

## What you will install

| Software | Purpose | Where to get it |
|----------|---------|-----------------|
| Python 3.12 | Runs the backend calculation engine | [python.org/downloads](https://www.python.org/downloads/) |
| Node.js 20 | Runs the web interface | [nodejs.org](https://nodejs.org/) |
| Git (optional) | Keeps your copy up to date | [git-scm.com](https://git-scm.com/) |

---

## Step 1 — Install Python 3.12

1. Go to [python.org/downloads](https://www.python.org/downloads/).
2. Click **Download Python 3.12.x** (the big yellow button — pick the latest 3.12 release).
3. Run the installer.
   - **Windows:** On the first screen, check **"Add Python to PATH"** before clicking Install Now. This is easy to miss; without it, the start script will not find Python.
   - **macOS:** Follow the prompts. The installer adds Python to your PATH automatically.
   - **Linux:** Python 3.12 is available via your package manager (`sudo apt install python3.12 python3.12-venv` on Ubuntu/Debian).

**Verify:** Open a new terminal (Command Prompt on Windows, Terminal on Mac/Linux) and run:
```
python --version
```
You should see `Python 3.12.x`. If you see an older version, try `python3 --version`.

---

## Step 2 — Install Node.js 20

1. Go to [nodejs.org](https://nodejs.org/).
2. Download the **LTS** version (currently 20.x). LTS stands for "Long-Term Support" — it is the stable, recommended version.
3. Run the installer and follow the prompts (defaults are fine on all platforms).

**Verify:**
```
node --version
```
You should see `v20.x.x` or higher.

---

## Step 3 — Download the project

**Option A — with Git (recommended for keeping up to date):**
```
git clone https://github.com/mkashyap00/retirement-optimizer.git
cd retirement-optimizer
```

**Option B — ZIP download:**
1. Open the GitHub repository page.
2. Click the green **Code** button → **Download ZIP**.
3. Extract the ZIP to a folder you will remember (e.g. `Documents/retirement-optimizer`).

---

## Step 4 — Start the application

### Windows

1. Open the `retirement-optimizer` folder in File Explorer.
2. Navigate into the `scripts` subfolder.
3. Right-click `start.ps1` → **Run with PowerShell**.

> **"Running scripts is disabled"?** This is a Windows security default.  
> Open PowerShell as Administrator and run once:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then try step 3 again. This setting only affects your user account.

> **Firewall prompt?** Click **Allow access** when Windows asks about network access — the app needs to listen on localhost (your own computer only, not the internet).

### macOS and Linux

Open Terminal, navigate to the project folder, and run:
```bash
bash scripts/start.sh
```

---

## Step 5 — Open the app

Once the start script finishes setting up (first run takes 1–2 minutes for dependency installation), it will print:

```
Starting backend  → http://localhost:8000
Starting frontend → http://localhost:3000
```

Open your web browser and go to: **http://localhost:3000**

The wizard will guide you through entering your household details.

Press **Ctrl+C** in the terminal to stop the servers when you are done.

---

## Troubleshooting

### Port already in use

If you see an error like `address already in use` or `EADDRINUSE`:

- Another program is using port 8000 or 3000 (possibly a previous run that was not shut down cleanly).
- On Windows: open Task Manager → Details tab → look for `python.exe` or `node.exe` → End task.
- On Mac/Linux: run `lsof -ti:8000 | xargs kill -9` and `lsof -ti:3000 | xargs kill -9`.

### "python not found" or "python3 not found"

- Restart your terminal after installing Python (the PATH update requires a new session).
- On Windows, verify you checked "Add Python to PATH" during installation. If you missed it, re-run the installer and choose **Modify** → check the PATH box.

### "node not found" or "npm not found"

- Restart your terminal after installing Node.js.
- Re-download from [nodejs.org](https://nodejs.org/) and run the installer again.

### The browser shows "This site can't be reached"

- The backend may still be starting up. Wait 10–15 seconds and refresh.
- Check the terminal window for error messages.

### Firewall blocks the connection (Windows)

When prompted, click **Allow access**. The app communicates only on localhost (127.0.0.1) — it does not send data to the internet.

### Page looks unstyled / plain text

If the page appears unstyled (plain text, no colors or layout):
- Stop the app (press Ctrl+C in the terminal).
- Delete the `.next` cache folder: run `rm -rf frontend/.next` (macOS/Linux) or manually delete the `frontend\.next` folder (Windows).
- Restart the app with `bash scripts/start.sh` (or `.\scripts\start.ps1` on Windows).
