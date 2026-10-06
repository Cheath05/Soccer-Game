# Running footsim in production (the Proxmox VM)

`deploy/` is only for the **production** install: the machine where footsim runs as a service
for playing, kept up to date from git by itself. Development and testing don't use it.

| | Where | Port |
|---|---|---|
| **Local, development and test** (the Mac, `just demo`, `just api`, the e2e and agent test servers) | `http://127.0.0.1:8000`, test servers on `8765` | **8000** stays as it is |
| **Production footsim** (the Proxmox Ubuntu VM) | `127.0.0.1:8001`, reached at **`https://cardinal.tailaf3b0c.ts.net:8443`** through Tailscale Serve | **8001** |
| **Cardinal** (another app on the same VM; never touched by footsim) | `127.0.0.1:8000`, reached at `https://cardinal.tailaf3b0c.ts.net` (Tailscale Serve, HTTPS 443) | 8000 |

## How production runs

- **`footsim.service`** is a systemd **user** service: the game on `127.0.0.1:8001`. It's the only footsim service on the VM.
- **`footsim-update.timer`** runs `footsim-update.service`, which is `deploy/update.sh`: two minutes after boot, then every ten minutes.
- **Lingering** keeps both running after you log out, and starts them at boot.
- **The VM's own settings** are in `~/.config/footsim/deploy.env`, written by `install.sh` and never in git:
  - `FOOTSIM_PORT=8001`, the port the game listens on;
  - `FOOTSIM_SERVE_PORT=8443`, the Tailscale HTTPS port, used for the checks;
  - `FOOTSIM_SAVES_DIR`, only if the careers aren't in the checkout's `saves/`.

  The service, the updater and the checks all read them, so they always agree.
- **Tailscale Serve** forwards `https://cardinal.tailaf3b0c.ts.net:8443` to `http://127.0.0.1:8001`. Cardinal keeps the normal HTTPS route (443 → 8000). The footsim scripts only *read* Tailscale's settings; they never change them.
- **Keep it on the tailnet only.** No `tailscale funnel`, and no port forwarding: the world contains EA's ratings.

## First-time setup, or moving to this setup

1. **Tools** (Ubuntu 22.04 or 24.04):

   ```bash
   sudo apt update && sudo apt install -y git curl build-essential
   curl -LsSf https://astral.sh/uv/install.sh | sh        # then open a new shell
   curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt install -y nodejs
   ```

2. **The code**, on the branch the game is being built on:

   ```bash
   git clone --branch phase-1-match-believability https://github.com/Cheath05/Soccer-Game.git ~/Soccer-Game
   ```

   If the repository is private, clone it with a read-only SSH deploy key instead: the timer can't type a password.

3. **The world, copied from the Mac.** It's built from the EA ratings and a Transfermarkt database, and it's never in git. Run this on the Mac:

   ```bash
   scp ~/Developer/Soccer-Game/data/worlds/base-2026-27.sqlite <user>@cardinal:Soccer-Game/data/worlds/
   ```

   - Careers live in `saves/` and aren't in git either. To carry one over, stop playing on the Mac and copy it (`scp -r ~/Developer/Soccer-Game/saves/slot_1 <user>@cardinal:Soccer-Game/saves/`).
   - From then on, play it on the VM only.

4. **Install, on the VM:**

   ```bash
   cd ~/Soccer-Game && git pull && ./deploy/install.sh
   ```

   It works through these steps in order:
   1. **Looks before touching anything.**
      - If a hand-made `/etc/systemd/system/footsim.service` exists, it shows it, checks it really runs footsim, and keeps its saves folder.
      - It refuses to start if something other than footsim holds port 8001.
   2. **Builds** while the running game keeps going.
   3. **Writes** the settings and the user units.
   4. **Retires the old system service,** if there was one, after asking:
      - it backs the unit up to `~/.config/footsim/footsim.system-service.backup`;
      - it stops it, disables it and removes it with `sudo`.
   5. **Starts the user service** and waits for it to answer on 8001.
      - If it doesn't answer, the old system service is put back as it was.
   6. **Prints the status check.**

   It never touches Cardinal, port 8000 or Tailscale. It's safe to run again: that rebuilds and restarts the game.

5. **Tailscale Serve, if the status check doesn't already show it** (it leaves the HTTPS on 443 alone):

   ```bash
   sudo tailscale serve --bg --https=8443 http://127.0.0.1:8001
   ```

   Then open **https://cardinal.tailaf3b0c.ts.net:8443** from any device on the tailnet.

## Updates

- **What runs:** every ten minutes, and two minutes after boot, `deploy/update.sh` fetches the checked-out branch and its tags. If there's a new commit, it:
  1. fast-forwards the checkout;
  2. installs the dependencies;
  3. builds the frontend beside the live one, and swaps it in;
  4. restarts `footsim.service`;
  5. checks that 8001 answers with the new commit.
- **It never interrupts play.** While anything is connected to the game (a match being watched) or a sim-to-date is running, it logs "busy, will try again" and waits for the next round, before touching anything.
- **It never discards work:**
  - it refuses if tracked files in the checkout have uncommitted changes;
  - it only ever fast-forwards: no reset, rebase or force.
- **If a build fails,** the running game is left alone, and the same commit is tried again next time.
- **When nothing is new,** it logs "up to date: v1.12 on <branch>, port 8001" and stops.
- **After an update,** the game is restarted, so the browser goes back to the start page. Load your save again; it's autosaved.

## Versions

The game shows its version at the bottom of the menu as `v1.12 · 6 Oct`. On a phone, where the menu is folded away, it's under the club name at the top.

- **The parts:** the version number, then the date of the commit the server runs. A `+` after the number means files were edited by hand on that machine.
- **The tag reads `v<major>.<minor>`.**
  - The minor number goes up with every update: it counts the commits since the latest `v<major>.0` tag, so `v1.12` is twelve commits after `v1.0`.
  - The major number goes up for big changes to the simulation (a git tag on the commit that starts it).
- **When you report something, tell me the version.** Tap the tag to copy a line such as `footsim v1.12 (70b9171, phase-1-match-believability) built 6 Oct 2026, 16:05`, and paste it into the message.
- **Orange text** such as `server v1.12 · page v1.10` means the page and the server are on different commits. Reload the page.
- **On the VM,** `curl -s http://127.0.0.1:8001/api/health` shows the same as JSON (`version`, `commit`, `branch`, `dirty`).

## Proxmox VM commands

| What | Command |
|---|---|
| Deploy the newest Git update now | `systemctl --user start footsim-update && journalctl --user -u footsim-update -n 20 --no-pager` |
| Rebuild and restart even if nothing is new | `~/Soccer-Game/deploy/update.sh --force` |
| Everything at a glance (service, port, version, timer, lingering, Tailscale) | `~/Soccer-Game/deploy/status.sh` |
| Are automatic updates enabled? | `systemctl --user is-enabled footsim-update.timer && systemctl --user is-active footsim-update.timer` |
| When will the updater run next? | `systemctl --user list-timers footsim-update.timer` |
| Updater logs | `journalctl --user -u footsim-update -n 50 --no-pager` |
| Footsim logs (live) | `journalctl --user -u footsim -f` |
| Footsim status | `systemctl --user status footsim` |
| Restart footsim | `systemctl --user restart footsim` |
| Deployed version and commit | `curl -s http://127.0.0.1:8001/api/health` |
| Git checkout and branch | `git -C ~/Soccer-Game log -1 --oneline && git -C ~/Soccer-Game branch --show-current` |
| Tailscale Serve | `tailscale serve status` (or `sudo tailscale serve status`) |
| What listens on 8000 and 8001 | `ss -ltnp '( sport = :8000 or sport = :8001 )'` |

All `systemctl --user` and `journalctl --user` commands run as your normal user, without `sudo`.
