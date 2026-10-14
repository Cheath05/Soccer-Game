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

## Friends: accounts and their own careers

Until accounts are on, everyone who reaches the server plays the same careers (yours). With accounts on, each person signs in and gets their own three career slots; yours stay exactly where they are.

**Once, to switch accounts on:**

1. Make your own account, the owner. It plays the careers already on the server:
   ```bash
   deploy/users.sh add Alex --owner
   ```
2. Switch accounts on. This restarts the game once, waiting until no match or sim is running:
   ```bash
   deploy/accounts.sh on
   ```
3. Open the game and sign in. Your browser keeps you signed in for 30 days from the last time you played.

**For each friend:**

1. **Tailscale:** in the admin console, go to Machines, then **cardinal**, then the "…" menu, then **Share…**, and send the friend the invite. Shared users are free, and they see this one machine only, not the rest of your tailnet.
2. **The friend** installs the Tailscale app (phone or computer), accepts the invite, and opens `https://cardinal.tailaf3b0c.ts.net:8443`. On a phone they can use Share, then **Add to Home Screen**, to get it as an app.
3. **Their account:**
   ```bash
   deploy/users.sh add Sam --generate
   ```
   This prints a password: send it to them. Their careers live in `saves/users/<folder>/`.

**Managing accounts:**

- `deploy/users.sh list`: every account, and on how many devices it's signed in.
- `deploy/users.sh reset-password Sam --generate`: a forgotten password. It signs them out everywhere.
- `deploy/users.sh rename Sam Samuel`: a new name to sign in with. Their careers and password stay, and they stay signed in.
- `deploy/users.sh disable Sam`: stop someone signing in. `disable Sam --enable` lets them back.
- `deploy/users.sh remove Sam`: delete the account. Their careers stay unless you add `--delete-saves`.
- `deploy/accounts.sh status`: whether accounts are on, and the list.
- `deploy/accounts.sh off`: everyone plays your careers again, as before. Nothing is deleted.

**What a dozen players cost:**

- **Disk:** about 80–150 MB per career slot including backups. Friends keep 2 backups to your 5 (`data/config/server.yaml`).
- **CPU:**
  - Continue, Instant play and Sim to… run in up to three worker processes (`sim_workers`), so two people simming at once each get a core. One person's sim is no faster than before.
  - A watched match costs very little.
- **Memory:** about 86 MB per worker.

**Updates still wait** while anyone is watching a match or running a sim (`in_use` in `/api/health` covers everyone).

## Versions

The game shows its version at the bottom of the menu as `v1.12 · 6 Oct`. On a phone, where the menu is folded away, it's under the club name at the top. It's on the start page too.

- **Tap the tag** to open **What's new and help**, a window with two tabs:
  - **What's new** lists every version, newest first, with what changed in it. The version the server is running is marked ("You're on this version"), and a version that isn't listed changed nothing a player would see.
  - **Help** explains what you can do in the game, topic by topic, with a search box.
- **The parts:** the version number, then the date of the commit the server runs. A `+` after the number means files were edited by hand on that machine.
- **The tag reads `v<major>.<minor>`.**
  - The minor number goes up with every update: it counts the commits since the latest `v<major>.0` tag, so `v1.12` is twelve commits after `v1.0`.
  - The major number goes up for big changes to the simulation (a git tag on the commit that starts it).
- **When you report something, tell me the version.** Tap the tag, then press **Copy version** at the top of the window. It copies a line such as `footsim v1.12 (70b9171, phase-1-match-believability) built 2026-10-06T20:05:00.000Z`; paste it into the message. **Build details**, under the button, shows the branch, the commit and when the page was built.
- **Orange text** such as `server v1.12 · page v1.10` means the page and the server are on different commits. Reload the page. The orange warning shows on the tag and in the window.
- **The patch notes** are `data/changelog.yaml`, and the help text is `frontend/src/lib/help.ts`.
  - Every update with something a player would notice adds an entry to the changelog in the same commit, under the version that commit ships in. The file's header says how to work the number out.
  - Update the help when what a player can do changes.
  - `backend/tests/unit/test_changelog.py` checks the changelog file, and `GET /api/changelog` serves it (behind the sign-in, like the rest of `/api` but health).
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
