# Running footsim on an Ubuntu VM

Footsim runs on the VM as a systemd user service. A timer pulls new commits of the checked-out
branch every ten minutes and redeploys them, so a push from the Mac reaches the VM by itself.
No root is needed except for the first-time steps marked `sudo`.

## First-time setup

1. **Install the tools** (Ubuntu 22.04 or 24.04):

   ```bash
   sudo apt update && sudo apt install -y git curl build-essential
   curl -LsSf https://astral.sh/uv/install.sh | sh        # then open a new shell
   curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash - && sudo apt install -y nodejs
   ```

   uv fetches Python 3.13 itself.

2. **Clone the repository**, on the branch the game is being built on:

   ```bash
   git clone --branch phase-1-match-believability https://github.com/Cheath05/Soccer-Game.git
   cd Soccer-Game
   ```

   If the repository is private, clone it with an SSH deploy key (read-only) instead: the
   update timer runs without a terminal and cannot type a password.

3. **Copy the world from the Mac.** `data/worlds/base-2026-27.sqlite` is the game's starting
   world, built from the EA ratings plus a Transfermarkt database. It is never in git, so it
   has to be copied. Run this on the Mac, with the VM's Tailscale name or address:

   ```bash
   scp ~/Developer/Soccer-Game/data/worlds/base-2026-27.sqlite <user>@<vm>:Soccer-Game/data/worlds/
   ```

   Copy the `.sqlite` file only, not the `-wal` and `-shm` files beside it. If the folder is
   missing on the VM, run `mkdir -p data/worlds` there first (`install.sh` does it too).

   Careers live in `saves/` and aren't in git either. To carry one over, stop the game on the
   Mac and copy the folder (`scp -r ~/Developer/Soccer-Game/saves/slot_1 <user>@<vm>:Soccer-Game/saves/`).
   From then on play it on the VM only, or the two copies diverge.

4. **Install and start the services:**

   ```bash
   ./deploy/install.sh
   ```

   It installs the dependencies, builds the frontend, writes `footsim.service`,
   `footsim-update.service` and `footsim-update.timer` under `~/.config/systemd/user/`, enables
   lingering (so the game runs at boot and after you log out; this may ask for `sudo`), and
   starts the game on `127.0.0.1:8000`. It is safe to run again; that restarts the game.

5. **Reach it over Tailscale**, once:

   ```bash
   sudo tailscale serve --bg 8000
   ```

   Then open `https://<vm-name>.<tailnet>.ts.net` from any device on your tailnet.
   `tailscale serve status` shows the exact address.

   **Keep it on the tailnet only.** Don't use `tailscale funnel` and don't forward a port: the
   world contains EA's ratings.

## Updates

- Every ten minutes (and two minutes after boot) `deploy/update.sh` fetches the branch. If
  there is a new commit it fast-forwards the checkout, installs the dependencies, builds the
  frontend beside the live one, swaps it in and restarts the game.
- **It never interrupts play.** While a browser is connected (a match being watched) or a
  sim-to-date is running, it logs "busy, will try again" and waits for the next round, before
  touching anything.
- It never discards work: it refuses if tracked files in the checkout have uncommitted changes,
  and only ever fast-forwards.
- If a build fails, the running game is left alone, and the same commit is tried again next time.
- To update now: `systemctl --user start footsim-update`.
- To see what happened: `journalctl --user -u footsim-update`. The game's own log is
  `journalctl --user -u footsim -f`.

## Which version am I on?

The bottom of the menu shows something like `v70b9171 · 6 Oct`: the commit the server runs and
its date, with `+` after it if files were edited by hand. On a phone, where the menu is folded
away, it is under the club name at the top. Hover for the branch and times; click to copy a line
to paste into a bug report. Orange text such as `server 70b9171 · page 44bdfe9` means the page
and the server are on different commits: reload the page, or if it stays, rebuild the frontend.
`curl http://127.0.0.1:8000/api/health` on the VM shows the same, as JSON.
