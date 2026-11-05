# Commercial iOS release: free on the App Store, with ads and fair purchases (approved 4 Nov; not built)

**Status: approved 4 Nov; nothing built yet.** Written on 4 Nov at Opus 5.5 Max, from a read-only study of the code, web research dated 3–4 Nov 2026, and a review of the draft against the code. Nothing here starts until you place it in the order of work in `progress.md`.
- **The legal points are research notes, not legal advice.** Anything marked **(lawyer)** needs confirming in the consult (ST2).
- **Step names have a prefix (I, PW, MO, ST).** That keeps them apart from W3/W4 (finances), Track M (phone layout) and U1/U2, which already appear in `progress.md`.

## Context

**What you asked for (4 Nov):**
- **A free iOS app.** footsim runs entirely on the phone and earns from three things:
  - an interstitial ad every few matches;
  - a one-time **Remove Ads** purchase ($5–10);
  - a small set of **fair, optional boosts**.
- **One codebase.** The same repo keeps serving the Tailscale server and your personal EA build. Neither has ads or a store, and both have everything unlocked.
- **The store build ships no EA data.** It gets a **PES-style names layer** with three name sets (fictional, "inspired", or imported by the player) and an in-game editor. Its realism comes from real-world structure and from ratings built only from free, commercially usable data.

**Your answers (4 Nov):**
- **The store world launches with everything in the game today:** all 54 countries and the UEFA competitions.
- **You're based in the US.**

**What the code does today (read 3–4 Nov):**
- **Runtime:**
  - The FastAPI app is built when its module is imported (`api/app.py:86`). It serves `frontend/dist` with an SPA fallback. uvicorn is started from the command line; no code launches it.
  - Paths come from `core/paths.py`: `REPO_ROOT` is four folders above that file, and `FOOTSIM_CONFIG_DIR`, `FOOTSIM_DATA_DIR` and `FOOTSIM_SAVES_DIR` override it.
  - Single-user is the default. Accounts switch on only with `FOOTSIM_AUTH=1`.
  - Heavy simulation goes to a spawned process pool when `sim_workers > 0`. `server.yaml:15` sets 3, but `create_app(session=…)` keeps the default of 0, which runs inline (`api/session.py:48`).
  - Startup tries `git` up to six times. On iOS that raises `OSError`, which `core/build_info.py:33` already catches before falling back to env values.
  - The base world is a WAL-mode SQLite file that is opened read-write (`api/queries.py:254`, `persistence/saves.py:66`).
- **Dependencies:**
  - SciPy is used at runtime only for `linear_sum_assignment` (`match/engine/engine.py:797`, `match/teams.py:134`) and `erf` (`match/engine/actions.py:775-776`). The `erf` call runs only when `passing.estimate.honest` is on, and that's off (`passing.yaml:47`).
  - Alembic is declared but never imported. Migrations are hand-written (`persistence/migrations.py`, schema v21; tests stop at `STEPS[19]`).
- **World:**
  - Every player and rating, and most club names, come from EA's file, either directly or through numbers fitted to it.
  - Every engine calibration so far ran on EA-rated squads.
  - Config fitted to EA or Transfermarkt, or naming trademarks, loads at runtime from one shared tree.
  - Saves are self-contained copies of the world (`persistence/saves.py:119-128`). Rules and calibration still load from YAML at runtime.
- **Game systems for boosts mostly don't exist yet:** no scouts or scouting reports, no facilities, no staff, no youth preview and no settings page. What does exist:
  - potential-range estimates, which only the UI reads (`scouting/estimates.py`; consumers `api/queries.py:939`, `api/market_overview.py:105`, `api/season_review.py:341`);
  - the yearly youth intake, tiered by club reputation (`world/lifecycle.py:143-234`, `rules/lifecycle.yaml:31-52`);
  - finances with an append-only ledger (`world/finance.py`).
- **Golden values are stored per platform** (`tests/unit/test_engine_golden.py:84`; only `darwin-arm64` exists). The engine is deterministic on a given machine type, not across machine types. The Mac's numpy uses Accelerate, and some queries have no `ORDER BY`.
- **A determinism bug exists today.** `world/market.py:85-124` caches every player's ratings, keyed only by month and player count. Viewing the market on the 1st of a month therefore makes that day's AI market (`world/season.py:206`) use the ratings from before that day's development (`:190`). I2a fixes it.
- **The phone layout is built** (`frontend/src/lib/device.ts`, plus safe-area meta tags in `index.html`).

**The intended outcome:**
- an App Store app that plays offline on iPhones running iOS 17 or later;
- the whole world, renamed, with no EA, SoFIFA or Transfermarkt data;
- polite monetization;
- the same repo as the server;
- three gates, so you can stop cheaply if the numbers or the law say no.

## Decided before planning (not reopened)

- **Architecture:** embedded CPython in an iOS app. The existing FastAPI backend runs on 127.0.0.1 inside the app, and the React build loads in a WKWebView. A thin Swift layer handles StoreKit 2 and the ad SDK, bridged to the web UI. No Swift rewrite and no Pyodide.
- **Differences sit behind settings** (phone mode, plus an entitlements flag that only the App Store build turns on): no accounts, the sim in one process, saves in the app container.
- **CPU, not GPU.**
- **No EA data in the store build.** Ratings are clean-room, a test proves the public build never reads EA or SoFIFA data, and the overall scaling is refitted against non-EA targets.
- **World data is chosen by a world file and a names file.**
- **Names:**
  - three sets: (a) fictional, (b) PES-style "inspired", (c) imported by the player;
  - plus an editor;
  - the default player-name set waits on the lawyer.
- **Monetization as specified:**
  - an interstitial every N matches;
  - Remove Ads as a $5–10 non-consumable;
  - a small, fair catalogue;
  - purchases recorded as deterministic events;
  - an entitlements module;
  - everything driven by data.
- **The full world at launch** (your answer).
- **US-based** (your answer).

## 1. What the research found (3–4 Nov 2026)

### 1.1 Running Python on iOS

**CPython supports iOS** (PEP 730, tier 3, since 3.13). The official guide, "Using Python on iOS" [S1], documents how to embed it in an Xcode app:
- add `Python.xcframework` with **Embed & Sign**;
- add a **"Process Python libraries"** run-script build phase:
  - it runs `source $PROJECT_DIR/Python.xcframework/build/build_utils.sh`, then `install_python Python.xcframework app`, followed by any extra package folders;
  - it turns every `.so` into a framework under `Frameworks/`, which the App Store requires;
- initialise the interpreter in embedded mode:
  - UTF-8 mode on, unbuffered stdio, **no bytecode writing**, system logger on;
  - `PYTHONHOME` is the bundle's `python/` folder;
  - `PYTHONPATH` is the stdlib, `lib-dynload` and the app folders.
- The default deployment target is iOS 13.
- There's no `python` executable and no REPL.
- Processes are unavailable. On iOS, `subprocess.Popen` raises `OSError` ("ios does not support processes"). `multiprocessing` imports, but creating a pool fails.

**App Store compliance:**
- CPython applies its `app-store-compliance.patch` automatically when building for iOS.
- Since April 2025, some binary libraries need a privacy manifest; OpenSSL is the one named [S1].

**Where the framework comes from:**
- python.org publishes official iOS XCframeworks starting with **3.15** (3.15.0–3.15.2, Oct 2026) [S2].
- For 3.13 and 3.14, BeeWare's **Python-Apple-support** provides them [S3].

**Briefcase** 0.4.6 supports Xcode 27 and uses the official packages on 3.15 [S4]. It generates its Xcode project from a template built around Toga.

**Decision: a hand-written Swift host** that embeds Python the official way, not a Briefcase-generated project.
- StoreKit 2 is Swift-only.
- AdMob, UMP, ATT and the WKWebView bridge are the native core of this app.
- Briefcase regenerates its project, which fights hand-kept Swift.
- Briefcase's iOS template stays the working reference, and the fallback if I0 stalls.

**Python 3.13 on the phone.** That matches your Mac (3.13.12), the server and `requires-python <3.15`. Moving every build to 3.15 and the official framework is a separate change for later.

### 1.2 Wheels for our locked versions

I ran a dry-run resolution on 4 Nov:
- command: `pip install --dry-run --only-binary=:all: --platform ios_{13,15,17}_0_arm64_iphoneos --python-version 3.13`;
- indexes: PyPI plus BeeWare's `https://pypi.anaconda.org/beeware/simple`;
- versions: those locked in `backend/uv.lock`.

| Package (locked) | Installable on iOS? | Plan |
|---|---|---|
| numpy 2.5.3 | **No.** BeeWare has 1.26.2, 2.3.5.post1, 2.5.0.post1 and **2.5.2.post1**. PyPI's 2.5.4 files have no iOS tags. Upstream NumPy now has tier 3 iOS support [S5] | Pin **numpy 2.5.2** in every build (one tested version), or build 2.5.3 with cibuildwheel's iOS platform |
| pydantic-core 2.46.5 (Rust) | **No, nowhere.** pydantic's request for mobile wheels is open and marked "deferred" [S6] | **Build it ourselves** with maturin for `aarch64-apple-ios` and `aarch64-apple-ios-sim`. maturin has supported iOS since 1.7, with fixes in 1.10–1.11, and BeeWare contributed iOS support to PyO3 and maturin [S7][S8]. **This is Phase 0's critical path: FastAPI can't run without it** |
| PyYAML 6.0.3 | **No.** Only an sdist and platform wheels | Build a pure-Python wheel without libyaml (we only use `safe_load`; loading the definitions takes 0.26 s on the M3) |
| scipy 1.18.1 | No | Removed from the runtime (I0/I1) |
| alembic 1.20.0 (with mako, markupsafe) | Not needed | Never imported, so drop it from the runtime dependencies |
| uvicorn's `standard` extras: uvloop, httptools, watchfiles, python-dotenv | No / not needed | Plain uvicorn on h11 and asyncio, **plus websockets**, which the live match needs |
| sqlalchemy 2.1.1, fastapi 0.141.1, starlette 1.7.0, pydantic 2.13.5, uvicorn 0.54.0, h11, anyio, websockets 17.1 | **Yes** (pure wheels) | As they are |

### 1.3 The minimum iOS version

- Vite 8.3.1's default build target includes `safari16.4` and `ios16.4`, and `vite.config.ts` doesn't override it.
- Mantine needs Safari 15.4+ [S9].
- StoreKit 2 needs iOS 15.
- **Plan: deployment target iOS 17.0** (iPhone XS/XR and newer).
- Which phones are fast enough is decided at G3, from what TestFlight testers measure.

### 1.4 Background, heat and memory

- **Suspension:**
  - After the player leaves the app, `beginBackgroundTask` buys a little extra time, then the app is suspended.
  - A suspended app can lose its **listening socket** without being told. Apple's advice is to close listeners before suspension and reopen them on return [S10].
  - Sockets that are already connected aren't closed by closing the listener.
- **iOS 26's `BGContinuedProcessingTask`** lets work that starts with a tap carry on in the background, with a Live Activity. The system ends tasks that show little progress first [S11][S12]. **Later:** v1 pauses in the background and resumes on return.
- **Heat:** `ProcessInfo.thermalState` and Low Power Mode can be observed. The sim can slow itself down without affecting results, because timing never changes outcomes.
- **Saves location:** always the app's own container (Application Support). Never a shared App Group container, where iOS kills suspended apps that hold SQLite locks.

### 1.5 App Store rules that shape the design

Read from the guidelines on 4 Nov [S34]:
- **2.5.2:** apps must be self-contained, and may not download or run code that changes features. So everything ships inside the bundle (interpreter, our code, wheels, world, config), and there's no remote config.
- **3.1.1:** unlocking features needs in-app purchase. Loot boxes must disclose their odds; we sell none.
- **2.5.18 (ads):**
  - ads only in the main app;
  - appropriate for the age rating;
  - interstitials clearly marked, with visible close buttons;
  - a way for people to report inappropriate ads.
- **4.2:** an app must be more than a repackaged website, so the offline, native feel matters: no browser chrome, native share and files, native purchases.
- **5.1.1 / 5.1.2:** a privacy policy in the listing and in the app; tracking needs ATT permission.
- **5.2.1 / 5.2.2:** no protected third-party material (trademarks, copyrighted works) without permission, and third-party services only within their terms.
- **1.3:** stay out of the Kids category, which bans third-party ads.
- **Also current:**
  - New age ratings (4+, 9+, 13+, 16+, 18+) with a mandatory questionnaire. Apps distributed in Texas may need extra consent for updates after 1 Jan 2026, under SB2420 [S13].
  - The EU DSA trader requirement: an individual developer's address, phone and email are shown on EU product pages [S14].
  - Google's consent form (UMP) before personalized ads in the EEA and UK, and Google's IDFA explainer before Apple's ATT prompt [S15].
  - AdMob's privacy manifest and data-disclosure guidance [S16].
  - US storefront apps may now link to outside purchases (3.1.1(a)). Not used here.

### 1.6 Data sources for the store world

Read on 3–4 Nov. The "Commercial?" column is my reading of the published terms, not legal advice **(lawyer)**.

| Source | Used today for | Terms found | Commercial? | Store build |
|---|---|---|---|---|
| EA FC 27 (Kaggle) | roster, ratings, most club names | EA-owned; personal use | No | **Never.** Personal build only |
| transfermarkt-datasets (dcaribou) | heights, values, contracts, names, birth dates; the 408 extra-league clubs | Repo is CC0 but "built from Transfermarkt data"; paused since 6 Jul 2026 [S17]. Transfermarkt's own terms and the EU database right aren't addressed | Unclear, and it's real people's personal data | **Drop** |
| StatsBomb Open Data | `fit-shots` → `shooting.yaml`; the `duels`, `passing` and `defending` YAML | Custom "StatsBomb Public Data User Agreement". README: for "research projects and genuine interest in football analytics", with credit and logo [S18]. Secondary readings: no commercial exploitation of the data or analysis derived from it [S19] | **Probably not** | Ask Hudl StatsBomb in writing; otherwise **refit** (PW7) |
| Metrica sample data | part of `passing.yaml` | No licence; "be responsible… acknowledge the source" [S20] | Unclear | Ask, or refit |
| Wyscout public dataset (Pappalardo et al. 2019) | nothing yet | CC BY 4.0 [S21] | Yes, with a citation | **Keep:** the refit source |
| SkillCorner Open Data | nothing yet | MIT; asks for credit [S22] | Yes | **Keep** |
| PFF/Gradient WC 2022 | nothing yet | Sign-up plus Terms of Use; tracking comes from a Sportlogiq partnership [S23] | Unclear | Don't use |
| ClubElo | design priors only | No terms on the API page [S24] | Unclear | Replace with our own Elo |
| football-data.co.uk | `match_targets.yaml`, home-advantage targets | No licence stated [S25] | Unclear | The targets are aggregate facts; ask for permission anyway |
| openfootball | nothing yet | Public domain (CC0): "use as you please" [S26] | Yes | **Keep:** fixtures and results where it covers a league |
| Wikidata | nothing yet | CC0 [S27] (CC0 can't promise no other rights exist) | Yes | **Keep:** name frequencies, clubs' towns and colours, real-shaped rosters if cleared |
| UEFA coefficients, real 2025-26 tables and winners, league memberships, matchday dates (all already in config) | Europe access, `season_before.yaml`, calendars | Published facts; we generate our own pairings | Facts | Keep, mapped to renamed clubs **(lawyer)** |
| Opta Analyst, premierleague.com (cited for targets) | `restarts.yaml`, `tactics.yaml`, targets | Site terms; these are published aggregate figures | Facts | Keep as cited facts **(lawyer)** |

### 1.7 Names, real people and the law (input for a US lawyer)

**Relevant cases:**
- **US:** fantasy games may use players' names and statistics without a licence under the First Amendment (C.B.C. v. MLB Advanced Media, 8th Cir. 2007; cert. denied 2008) [S28]. Games that recreated players' likenesses as avatars lost (Keller v. EA and Hart v. EA, 2013) [S29]. Publicity rights vary by state. Club names and crests are trademarks that the clubs register in the US too.
- **Germany:** Oliver Kahn stopped sales of an EA game over his unlicensed image (Hamburg, 2003–04). EA's workaround was a fictional keeper [S30].
- **UK/EU** (if you sell there): the "Project Red Card" claims argue that using players' data without consent breaches UK GDPR. The reports found say it's still pre-litigation [S31]. A real roster under altered names is still **identifiable personal data**.

**What this means for the design: names and roster structure are two separate choices.**
- **Generated squads:** the players are invented from distributions, and the clubs and leagues are real in structure but renamed. No real person is involved. This is the safe default, and the fallback in every case.
- **Real-shaped squads:** one player per real person, with that person's position, age, nationality and club. This is what makes PES-style option files work, and what (b)'s altered player names need. **Both wait on the lawyer.**
- **(c), names imported by the player, works with either:** a names file applied on the player's own device. The app never ships, hosts or links to one.

### 1.8 What it might earn

**Inputs found:**
- iOS interstitial eCPMs of about **$14 (US) and $10 (UK)** in Appodeal-based Q4 2024 data, $5–15 in other 2026 summaries, and $23 (US) in a Q2 2024 Tenjin report [S32];
- **1–5%** of players pay in freemium games [S33];
- Apple's Small Business Program takes **15%**;
- AdMob pays out only above a payment threshold, about $100 (check in AdMob).

**Model assumptions:**
- a player plays for an average of 3 months in the year;
- 40 matches a month, with an interstitial every 3 matches and 90% fill;
- ads at a blended $6 eCPM (3 months × 13.3 impressions × 0.9 × $6/1,000 ≈ $0.22 a player);
- 3% buy Remove Ads at $6.99, about $5.50 net after commission and taxes;
- 2% buy one $1.99 boost.
- The low case uses a $3 eCPM and 1% conversions; the high case $10 and 5%.

| Players in a year | Ads | Remove Ads | Boosts | Total (low–high) | After the $99 fee |
|---|---|---|---|---|---|
| 50 | $11 | $8 | $2 | **≈ $21** ($9–34) | **−$78** (and AdMob never pays out) |
| 500 | $108 | $83 | $17 | **≈ $208** ($90–343) | **≈ +$109** |
| 5,000 | $1,080 | $825 | $170 | **≈ $2,075** ($900–3,425) | **≈ +$1,976** |

- **One-off costs:** the lawyer (a few hundred dollars; get a quote) and, optionally, a domain.
- **Break-even:**
  - on the developer fee alone, about 240 players a year at the middle numbers;
  - with a $400 consult in the first year, about 1,200.
- **Income is taxable.** Ask an accountant how to report it as an individual.

## 2. Architecture

### Three builds from one repo

| | Server (Tailscale) | Personal | Store (TestFlight / App Store) |
|---|---|---|---|
| Runs on | the VM, your Mac | your Mac; your own iPhone (free provisioning, re-signed every 7 days) | iPhones |
| World and config | EA world, shared config | EA world, shared config | **Public world**, public config overlay |
| Names | real (from the EA file) | real | fictional by default; (b) only after the lawyer; (c) by the player |
| Entitlements | `unlocked` | `unlocked` | `store` |
| Ads / store | none | none | AdMob + StoreKit 2 |
| Sim | worker processes | in-process | in-process |
| Bundle id | — | its own id (can't be uploaded by mistake) | the store id |

- **Config per world:**
  - The loader reads the shared engine and rules tree plus **one world overlay**: names, league and club files, fitted ratings files, wage and value models.
  - An overlay file replaces the shared file at the same relative path, through a single `config_file(rel)` helper that replaces the direct `config_dir() / …` joins.
  - The default overlay is personal, so the server and your Mac need no new step, and the golden values don't move.
  - Bundling flattens the shared tree and the chosen overlay into one tree.
- **Every fitted config file carries a `# provenance:` header.**
- **The guards run as an Xcode Release/Archive build phase,** so they check exactly the archive that's uploaded. A store archive is refused when any of these is true:
  - the world manifest lists a source not marked commercial;
  - a config file's provenance header names one;
  - the bundled config, changelog, help text or frontend build contains a term from the trademark list.
- **The store build ships its own changelog and help text.**
- **Calibration and tests** run with entitlements set to `off`.

### Inside the app

```
iPhone app (Swift)                                 Python thread (embedded CPython 3.13)
┌────────────────────────────────┐                 ┌───────────────────────────────────┐
│ WKWebView → http://127.0.0.1:P ├────────────────▶│ uvicorn (h11, asyncio, websockets)│
│   React build (bundled)        │ REST + live WS  │ FastAPI app in phone mode         │
│   bridge: postMessage ⇄ JS     │                 │ CareerSession, sim in-process     │
│ StoreKit 2 · AdMob · UMP/ATT   ├── verified ────▶│ entitlements (device state)       │
│ lifecycle · thermal            │   entitlements, │ saves: Application Support/saves  │
│ Files / share (save export)    │   lifecycle     │ world + config: read-only bundle  │
└────────────────────────────────┘                 └───────────────────────────────────┘
```

- **Swift sets every `FOOTSIM_*` variable before Python starts:** the saves folder, the config tree and the baked build info.
- **Loopback hardening:**
  - A pure ASGI middleware covers both HTTP and WebSocket. It's on only in phone mode. Today's middleware is HTTP-only, and WebSockets pass straight through it.
  - The server binds to 127.0.0.1 only, on a fixed port (with a fallback scan), so `localStorage` survives between launches.
  - Each launch gets a new secret. Swift puts it in the web view's cookie store before the first load. Every request and WebSocket must carry it, with the right `Host` and, for the WebSocket, the right `Origin`.
  - Refusals answer **403**, never 401, because `api/client.ts:20` treats 401 as signed out.
  - `/api/health` stays open but leaves out `saves_dir`.
- **The bundle layout mirrors the repo** (`app/backend/src/footsim`, `app/data/config`, `app/data/worlds/<world>.sqlite`, `app/data/changelog.yaml`, `app/frontend/dist`). That way `core/paths.py`'s `REPO_ROOT` resolves inside the bundle. `PYTHONPATH` includes `app/backend/src`.
  - Bytecode is precompiled at bundle time (`compileall --invalidation-mode unchecked-hash`). Importing the app takes 0.90 s with bytecode and 1.62 s without on the M3, and the bundle is read-only.
- **Left out of the bundle:**
  - `calibration/` and `cli.py`;
  - the pipeline-only importers (keep `importers/__init__.py` and `generate.py`);
  - `data/raw`, `reports/` and `saves/`;
  - the pre-W7 world.

### New places in the repo

- **`ios/`:** the Xcode project (the Swift host) and `ios/scripts/` (wheel builds, bundle assembly, guards). `ios/wheelhouse/` and the assembled `ios/Footsim/app/` are both git-ignored.
- **`backend/src/footsim/phone/`:** the embedded entry point (`main(port, secret)`), the lifecycle and thermal endpoints, and the bench endpoint.
- **`backend/src/footsim/bench.py`:** called by both the CLI and the phone.
- **`backend/src/footsim/store/`:** entitlements, the catalogue and boost effects.
- **`data/config/store/`:** `catalogue.yaml` and `ads.yaml`.
- **`data/config-worlds/public/`:** the public world's overlay.
- **`data/sources/`:** the source registry (PW1).
- **`frontend/src/native/`:** the bridge client, plus a new Settings route.
- **`docs/store-rules.md`:** what we will never sell.

## 3. Track I: the iOS app

**Before I0 (you):**
- accept the Xcode licence (`sudo xcodebuild -license accept`);
- install the iOS platform and a simulator in Xcode (Settings → Components);
- turn on Developer Mode on the iPhone and connect it once by cable.

I'll install Rust's iOS targets (`rustup`) when I0 starts.

### I0. Phase 0: the test build (main session, Opus High; free, no developer account)

- **I0a. Dependency audit (Mac only).**
  - Create `ios/requirements-phone.txt`: the runtime dependencies minus scipy, alembic and uvicorn's extras, plus websockets.
  - A script repeats 1.2's dry run for the device and simulator tags and records what's missing. Expected: pydantic-core, PyYAML, and numpy 2.5.3.
- **I0b. Build the missing wheels** into `ios/wheelhouse/`, from a committed recipe (`ios/scripts/build_wheels.sh`):
  - pydantic-core 2.46.5 with maturin, for device and simulator, deployment target 17.0, against the support package's Python;
  - a pure-Python PyYAML wheel;
  - numpy 2.5.2.post1 from BeeWare, with numpy pinned to 2.5.2 in `uv.lock` as well, after checking the golden values don't move. The alternative is to build 2.5.3.
- **I0c. The exact SciPy replacements, straight away** (they're small, and a review already checked them):
  - **`linear_sum_assignment`:** a literal port of SciPy's `rectangular_lsap.cpp`. It keeps:
    - the reverse-ordered `remaining` list;
    - the tie rule (`== lowest && row4col[j] == -1`);
    - the dual updates in the same order;
    - the transpose for tall matrices;
    - the final argsort.
    - Ties are routine here: identical CB columns in a 4-4-2, fixed slots at exactly `1e6`, and familiarity bands × 100. A different exact solver would pick another tied optimum and move the golden values. A ~45-line port matched SciPy 1.18.1 on 20,000 tie-heavy cases, at 0.06 ms per 30×11 call.
  - **`erf`:** the Cephes `erf`/`erfc` with `math.fma` at each step, applied element by element. `math.erf` differs from SciPy's on 55% of inputs in [0, 1), but the FMA Cephes port matched 800k samples exactly on darwin-arm64.
- **I0d. A minimal Swift host** (`ios/Footsim.xcodeproj`):
  - It embeds BeeWare's Python 3.13 support package as [S1] describes.
  - Swift sets the `FOOTSIM_*` variables, then the Python thread runs `footsim.phone.main`. That builds `CareerSession(saves_dir(), <world>, keep_backups=2)` and `create_app(session=…)`, and starts uvicorn in code (`http="h11"`, `loop="asyncio"`).
  - For the spike, Swift copies the world into the container on first launch (I2 replaces this with a read-only open).
  - The web view loads once `/api/health` answers.
- **I0e. Simulator first, then your iPhone 17 Pro Max** with free provisioning.
  - The benchmark uses synthetic teams.
  - A real career day uses your personal world: personal use, on your own device.
- **I0f. Measure with `footsim.bench`,** run through the CLI on the M3 and on the i5-9500T VM, and through a bench endpoint on the phone. It uses the same fixture and seed everywhere and writes JSON (to `reports/bench/` on the computers). It measures:
  - cold start to a usable screen;
  - one agent match on a fixed synthetic fixture;
  - one in-game week of sim-to-date;
  - peak memory (the app's `phys_footprint`, read in Swift);
  - the event log's sha256 against the Mac's for the same seed. This is recorded, not required.
- **Done when:** a match plays in the app on the phone, the numbers are in `progress.md`, and G1 is decided.

### I1. SciPy out of the runtime (Opus High; engine-reviewer)

- **Tests:**
  - a property test against SciPy (dev-only) on 100,000 random matrices, covering engine shapes, picker shapes, integer and constant costs, and ties. The assignment itself must match, not just the cost;
  - the `erf` equality test, on darwin-arm64 only;
  - the golden values unchanged;
  - a subprocess import test with `sys.modules['scipy'] = None`, proving `footsim.api.app` loads and plays a match without SciPy.
- **SciPy moves to the `dev` and `data` groups** (calibration's `minimize` keeps it), and `uv.lock` is updated.

### I2a. Fix the market cache's stale ratings (Opus High; engine-reviewer). This is a bug in today's game

- **The fix:** key `world/market.py`'s `_CACHE` on a save-level epoch, which every writer of the cached columns bumps: development, position training, intake, retirement and value premiums.
- **Tests:**
  - viewing the market overview on a transfer window's 1st, then advancing, gives the same database as advancing without the view;
  - the same holds across a process restart.
- **Must land before I2's equality tests,** and before I3 drops caches on a memory warning.

### I2. Phone mode in the backend (Opus High)

- **`footsim/phone/main.py`.** In `api/app.py`, `app` becomes lazy through a module `__getattr__`. uvicorn resolves the app with `getattr`, so `footsim.api.app:app` keeps working in `justfile`, `deploy/install.sh` and `test_smoke.py`.
- **The base world opens read-only. Saves don't change.**
  - `new_career` copies the world with `_copy_database(…, immutable_source=True)` (`file:…?mode=ro&immutable=1`).
  - `world_leagues` uses a new `persistence/database.py:open_readonly`, moved out of `calibration/engine_batch.py:92-96`, without the WAL pragma.
  - Save, autosave and load keep today's opens. Applying `immutable` there would miss commits that haven't been checkpointed, and corrupt saves.
  - `build-world` and the bundle step write the world checkpointed and in rollback-journal mode (`wal_checkpoint(TRUNCATE)`, `journal_mode=DELETE`, `VACUUM`).
  - **Test:** a save taken straight after a commit, before any checkpoint, contains that commit.
- **A day-capped sim step (also `performance.md` §4 step 1, built once):**
  - `sim_step(…, max_days=None)`. When capped, after the `until` check it first plays today's remaining computer fixtures (`_play_day` is idempotent), then advances at most `max_days`. Stopping at the cap carries on unless `until` is reached.
  - The server passes `None`, so its path is untouched.
  - Continue goes through the same stepper in phone mode.
  - **Tests:** `iterdump` equality for `max_days=1` against an uncapped run over 40 days, covering a window's 1st and a user match; then the same with a fresh process between steps.
- **Lifecycle (secret only):**
  - `background` pauses every live match under its own lock and sets a pause flag that the sim job checks between steps, then acknowledges at once (the last commit is already durable). It autosaves only when no step is running.
  - On launch, phone mode resumes the working copy if it's intact and at a later game date than the autosave.
  - An Instant match is indivisible, so a pause can wait up to one match.
- **The loopback middleware** (section 2) and **thermal pacing** from YAML: at `serious`, a short sleep between day-steps; at `critical`, a pause with a notice.
- **Tests:**
  - a phone-mode API smoke test on the `test_api_flow.py` pattern (new career → advance → instant play → live match over the WebSocket);
  - the process pool is never constructed;
  - the secret, `Host` and `Origin` rejections;
  - **a sim paused and resumed gives the same save as one never paused.**

### I3. The host app in full (Opus High; Swift)

- **Lifecycle:**
  - Going to the background: `beginBackgroundTask`, `background`, wait a few seconds at most, then stop uvicorn (`should_exit`).
  - Coming back: start a new `Server` on the same app and check `/api/health`.
  - If WebKit's content process is terminated, reload the web view.
- **While a sim or live match runs:** the idle timer is off. Thermal state and Low Power Mode are passed to Python, and memory warnings make Python drop its caches (after I2a).
- **Info.plist:** ATS `NSAllowsLocalNetworking`, plus a privacy manifest for the app and Python's binary modules. It covers required-reason APIs such as file timestamps; confirm the list in I0.
- **Backups:** save backups, `working.sqlite` and its `-wal`/`-shm` are excluded from iCloud backup. The main save stays included.
- **The rest:** launch screen, icon and safe areas.
- **Known limit:** if iOS closes the app during a live match, that match restarts from kickoff next time, with the same seed.

### I4. The web UI inside the app (Sonnet High, with an Opus review)

- **`frontend/src/native/bridge.ts`:** typed calls over `window.webkit.messageHandlers.footsim`, with feature detection. With no bridge (the web), everything is unlocked and there are no ads.
- **A new Settings route** holds:
  - the privacy policy and terms, opened natively;
  - privacy choices (UMP);
  - restore purchases;
  - report an ad;
  - attributions and the disclaimer;
  - the names editor.
  - Currency and board stay on Finances: they're per-career settings.
- **The live match reconnects** when the app comes back. Today `useLiveMatch.ts` only shows "Lost connection", even though the server keeps the match.
- **Small fixes:**
  - no pinch-zoom or long-press callouts;
  - external links open in an in-app Safari sheet;
  - in the store build, VersionTag shows the marketing version, and What's New uses the store changelog.
- **e2e:**
  - the scripts pick the first club instead of hard-coded EA-world clubs (`phone.mjs:36`, `smoke.mjs:25,48`, `live.mjs:23`, `season.mjs:22`, `debug.mjs:22`);
  - add a WebKit run of `phone.mjs`, which uses Chromium today.

### I5. Moving saves (Sonnet High)

- **A `.footsim` file:** the save (a SQLite backup) plus `manifest.json` (schema version, world id and hash, config tree id, app version, sha256).
  - Export through the share sheet or Files.
  - Import runs the integrity check and then any migrations.
- **v1 moves saves between builds that share a world:** your personal phone and the server; the store app and a Files backup.
- **Store-world saves on the server are Later.** The server would need to carry the public config tree, because for example `world/market.py:253` looks up wage levels by league name.

### I6. Bundle assembly and builds (Sonnet High)

- **`just ios-bundle profile=store|personal`:**
  - assembles `ios/Footsim/app/` in the mirrored layout;
  - flattens the shared config and the chosen overlay into one tree;
  - installs the wheels for device and simulator;
  - copies the world (checkpointed, DELETE journal) and the right changelog and help text;
  - precompiles bytecode;
  - bakes in the build info.
- **The guards** (section 2) run as a Release/Archive build phase.
- **`just ios-build`** builds for the simulator, followed by an XCUITest smoke test: launch, the web view loads, a match starts.

### I7. TestFlight (needs ST1: the $99 account)

- Internal testers first, then an external group with a public link, which goes through Beta App Review.
- **An in-app bench screen** lets testers report their phone's numbers. They decide the minimum device at G3.

### I8. App Store submission (after G3)

## 4. Track PW: the public world (the whole world, England first)

**The scale, from your answer:**
- about **1,078 clubs** to rename;
- about **27,800 players** to generate;
- **54 countries' leagues**, their cups and the UEFA competitions to name and validate.

**England first means:** every public world build generates everything (generation is quick), but validation and tuning start with England, where the targets are. The other countries follow before launch. Nothing launches until the whole world passes.

### PW1. The source registry and the clean-room boundary (Opus High)

- **`data/sources/<id>.yaml` for each source:**
  - licence;
  - `commercial: allowed | non_commercial | unclear`;
  - attribution text, URL, snapshot date and sha256.
  - Filled from 1.6.
- **Every fitted config file gets a `# provenance:` header** naming its sources.
- **`build-world --profile public|personal`.** The manifest that design §32 planned goes into `game_meta`: sources, hashes, profile and config tree.
- **The clean-room test** builds a small public world in a temp folder. Every read under `data/raw/ea_fc27`, any SoFIFA set and `data/raw/transfermarkt` is made to fail. It then asserts:
  - no such read happened;
  - no `ea_fc27` or `transfermarkt` rows exist in `external_id`;
  - the manifest and the provenance headers list only commercial sources;
  - the public pipeline doesn't import the EA import profile.

### PW2. Config per world (Opus High; Sonnet High for the moves)

- **Add the overlay loading** described in section 2 (`config_file(rel)`, with the personal overlay as the default).
- **Split today's one tree** into shared engine and rules files plus a **personal overlay**. The personal overlay holds the EA- and Transfermarkt-fitted and real-named files, including:
  - `overall.yaml`, `calibration/overall_scaling.yaml`, `synthetic_attributes.yaml`;
  - `valuation.yaml`, `wage_levels.yaml`, `world_build.yaml`, `new_clubs.yaml`;
  - the competition, cup and Europe names, `season_before.yaml`, `nations.yaml`.
- **Create the public overlay next to it.**
- **Code that hard-codes real names gets a world-neutral form:**
  - `LeaguePicker.tsx:25` strips "EFL ";
  - `Rankings.tsx:22`;
  - the real league keys in reports;
  - `help.ts` and the changelog text (the store build gets its own).
- **Done when:** the personal world, rebuilt **into a temp path**, has the same content as today's, and the golden values and the full suite are unchanged.
  - Never rebuild over `data/worlds/base-2026-27.sqlite`: your :8000 game reads it.

### PW3. The real-world structure from CC0 and public facts (Sonnet High)

- **League membership** comes from the existing competition YAML and club lists. These are facts; the public overlay renames the clubs.
- **Club strength:**
  - **Our own Elo,** computed from openfootball results wherever it covers a league.
  - Elsewhere, league strength comes from UEFA association coefficients (published facts), with spreads by last season's table where known.
- **Clubs' towns and colours** come from Wikidata, with generated colours where they're missing.

### PW4. The clean-room squad generator (Opus High)

- **Generated squads** (the safe default) for every club:
  - squad shape, ages and foreign-player mix come from `world_build.yaml`'s structure, with the public overlay's hand-set values and aggregate shares from CC0 data;
  - club strength maps onto league-level targets.
- **Position templates are written by hand in YAML,** not copied from EA vectors.
- **Reused machinery:**
  - `match/synthetic.py`'s quality model, refitted on the clean world (public `synthetic_attributes.yaml`);
  - feet, heights and traits drawn from distributions;
  - potential, personality, contracts and wages through `importers/generate.py`;
  - derived attributes through `importers/derive.py`.
- Real-shaped squads, for (b), are PW10.

### PW5. A rating scale and models without EA (Opus High)

- **`calibrate-overall --reference elo`** fits the public per-group scale so that squad strength follows the club strength from PW3. League means are set by hand in YAML, as documented design choices.
- **Refit the public overlay's models on the clean world:**
  - `synthetic_attributes.yaml`;
  - `shooting.yaml`'s reference ratings;
  - `calibration/responses.py`'s slopes;
  - `valuation.yaml` (and the `ea_fc27` filter in `value_fit.py`);
  - the wage reference overalls.
- The personal world keeps all of its own.

### PW6. Names, clubs, competitions and badges (Sonnet High; Opus review of the club list)

- **The names layer:**
  - overlays applied when the world is built and when a career is created;
  - a `footsim-names/1` JSON format covering players, clubs and competitions;
  - the editor writes into the save through the API.
- **(a) Fictional players:**
  - First and last names are drawn by nationality from CC0 or public-domain frequency tables: Wikidata footballers' given and family names by citizenship, ONS baby names (Open Government Licence), and US SSA names.
  - They're seeded by the world.
  - No generated name may equal a real footballer's full name; it's checked against a CC0 list. A blocklist catches offensive results.
  - The youth intake already recombines the save's own people, so it stays fictional.
  - Their home is `data/config/name_pools/`, which is empty today.
- **Clubs (about 1,078):**
  - **Proposed descriptive names** from a town plus a generic suffix or colour ("Manchester Blue", "North London"). Each proposal must not equal or nearly equal any real club's name, nickname or mark in that country.
  - **Curated by hand for the top divisions**; the rest come from the generator, with a review CSV.
  - No near-misspellings **(lawyer)**.
- **Competitions** get generic names ("English First Division", "National Cup", "European Champions' Cup"…), checked against the trademark list, and so do the European terms in the UI (for example "European Performance Spots").
- **Badges:**
  - generated SVGs from a small set of plain shapes, the club's colours and its initials;
  - the club's colours become new `club` columns in the next schema version;
  - the match viewer's kits use them too. Today every match is blue v orange (`match-viewer/draw.ts:29-32`).
- **(c) Names import and export:** names-only `footsim-names/1` files through Files or the share sheet, applied to the current save, with size and content validation; plus export of the current names.
- **Later:** whole database packs, which need `build_world` and rapidfuzz on the phone, and neutral nation spellings.

### PW7. Engine parameters with commercial provenance (Opus High; engine-calibrator for batches)

- **Ask Hudl StatsBomb, and Metrica, for written permission** to ship parameters fitted on their open data in an app that earns money. Send the requests now: they cost nothing.
- **Without permission:**
  - refit the parameters derived from StatsBomb and Metrica data (`shooting.yaml`'s chance model, `duels`, `passing`, `defending`) from the Wyscout public dataset (CC BY 4.0) and SkillCorner (MIT);
  - the refit values replace the shared match YAML **for every build**, so there's one parameter set;
  - record the provenance in each header.

### PW8. The engine on the public world (engine-calibrator runs; Opus High decides)

- **The calibration principles apply:** one engine, ratings first.
- **Batch sizes:** 200 paired fixtures for each tuning decision, then 1,000 for acceptance.
- **Misses are fixed in the world generator,** never with league-specific engine changes.
- **The other countries** are checked with the existing reports (`market-report`, `europe-report`, `sim-season`): league strength order, goals and draws in range, European results by country, market churn.
- **Heavy:** one batch at a time.

### PW9. A quality comparison that keeps the clean room clean (Opus High)

- **Compare outcomes, not per-player ratings.** Run season sims of the public and personal worlds against the same real targets:
  - table spreads, goals, home advantage;
  - upsets by strength gap;
  - age and position profiles;
  - promotion churn;
  - European results.
- **Add a blind play-test:** you and two friends.
- **Never compare public ratings to EA's player by player.** Tuning the generator to those numbers would fit it to EA indirectly.

### PW10. Real-shaped squads and (b) inspired names, only if the lawyer clears them

- **Roster facts from Wikidata**, only the minimum needed: position, birth year rather than full date, nationality, club.
- **Ratings** come from the same clean generator, using those facts and club strength.
- **Inspired player names** come from a deterministic alteration. Switching between (a) and (b) is just a different names file.

## 5. Track MO: monetization

### MO1. The rules and the catalogue (Opus High)

**`docs/store-rules.md`, what we will never sell:**
- player attributes, ratings or results;
- in-game money, or transfer or wage relief;
- anything random;
- anything time-limited or pressured;
- anything aimed at children.

**What a boost may be:** information, convenience, or a step that the free game can also reach, capped at that step.

**The data files:**
- `data/config/store/catalogue.yaml` with `defs/store.py`: a `DefModel` that forbids extra keys, effect types enumerated in code, and capped magnitudes;
- `ads.yaml`: an interstitial every N completed matches, a minimum gap in minutes, and a grace period for new players.

**The v1 catalogue, on systems that exist:**
- **Remove Ads:** a non-consumable at a price tier between $5 and $10; default $6.99.
- **Sharper scouting:** narrower potential ranges for other clubs' players. Only the UI reads them, so results can't change.
  - First, `scouting/estimates.py`'s knowledge constants move to YAML, as CLAUDE.md requires.
- **Academy step (the "nice bump in progression"):** your youth intakes are drawn **one reputation tier higher**, capped at the top tier (`rules/lifecycle.yaml:31-52`).
  - `youth_intake` reads the claim from the save.
  - The per-club random stream is unchanged.
  - Free play reaches the same tier by raising the club's reputation.

**Later, once the systems exist:**
- the youth intake preview (with its optional rewarded ad). Done properly it needs a pending-intake table filled on a fixed earlier date, a migration, and handling for saves already mid-season. Inserting youngsters early would put them into monthly development, the market and squad trims;
- an extra scout slot and faster reports (design §18);
- a one-off training-facility step.
- Never build a system just to sell it.

**Every item is non-consumable,** so it's restorable and can't be hoarded. Per-career items are claimed once per career.

### MO2. Entitlements (Opus High)

- **`footsim/store/entitlements.py` has three providers:**
  - `store`: verified purchases, from Swift;
  - `unlocked`: server and personal builds. No ads, and every item can be claimed free; claims are still recorded;
  - `off`: calibration and tests.
- **Device-wide state lives in the container** (`app_state.sqlite`): owned products, the last verification, the ad counter. Never in a save.
- **Endpoints:**
  - `GET /api/entitlements`;
  - `POST /api/phone/entitlements` (secret only, called by Swift);
  - `POST /api/career/boosts/{item}/claim`.

### MO3. Boosts as recorded events (Opus High; engine-reviewer)

- **A `career_boost` table,** append-only like `finance_ledger`: item, effect, magnitude, the game date it was claimed on, and a sequence number.
  - It's added by `_to_v22` (`STEPS[22]`, `SCHEMA_VERSION = 22`).
  - The migration tests for v20, v21 and v22 build a tiny world in a temp folder. Today's migration tests skip without the EA base world.
- **Effects are read only from the save,** by the systems they touch (`scouting/estimates.py`, `world/lifecycle.py`), never from entitlements. That also suits the server's worker processes.
- **Tests:**
  - `footsim.match` never imports `footsim.store` (an import test);
  - a season with Sharper scouting claimed gives the same fixtures, results and player data as one without (only the claim row differs);
  - the academy step changes only the user's intakes;
  - calibration asserts the provider is `off`;
  - a seed plus the same claims reproduces the same save.

### MO4. StoreKit 2 (Opus High; Swift)

- Product ids are generated from `catalogue.yaml` at bundle time.
- **The purchase flow:**
  - purchase, plus a `Transaction.updates` listener;
  - `currentEntitlements` at launch;
  - verified transactions only;
  - **Restore Purchases** (`AppStore.sync()`);
  - the verified set is posted to Python.
- **Testing:** an Xcode StoreKit configuration file for local tests (no account needed), then sandbox testers after ST1.

### MO5. Ads (Opus High; Swift plus backend)

- **Google Mobile Ads and UMP,** through Swift Package Manager:
  - consent at first launch, then Google's IDFA explainer, then Apple's ATT prompt;
  - non-personalized ads when there's no consent;
  - a low maximum ad content rating;
  - the SDK's privacy manifest.
- **Cadence:**
  - A **device counter** goes up at the safe points: +1 when a match ends, and +`len(results)` when a sim finishes.
  - The save's own count resets with a new career and falls when an older save loads, so it isn't used.
  - An ad is offered at most once per safe point.
  - Never during the live viewer, a sim, or a new player's first matches.
  - Offline means no ad and no penalty.
  - Remove Ads stops them at once.

### MO6. Tests and the ad-free builds (Sonnet High)

- **Provider tests,** including that `unlocked` reports no ads.
- **A frontend build without the bridge never requests an ad.** The e2e run on :8765 checks that no ad calls happen and that `GET /api/entitlements` reports unlocked.

### MO7. The store page and its copy (Sonnet High)

- Prices come from StoreKit, localized.
- Each item says what it does in one line.
- No countdowns and no "limited" offers.

## 6. Track ST: store and legal (US-based)

### ST1. Accounts and business set-up (you)

- **Join the Apple Developer Program ($99/yr) only after G1.** Then:
  - the Paid Applications Agreement;
  - the US tax form (W-9) and banking;
  - the Small Business Program (15%);
  - an AdMob account with its payments profile.
- **Decide:**
  - **An individual or an LLC.** A paid or ad-supported app makes you a "trader" in the EU, so as an individual your address, phone and email appear on EU product pages. An LLC with a business address avoids showing your home address.
  - **Storefronts:** the US only, or US + UK + EU at launch. The UK and EU add GDPR, the UK Children's Code and the DSA.

### ST2. The lawyer consult (you; questions drafted at Opus High)

A US IP or entertainment lawyer, for one hour, before PW10 and before submission. The questions:
1. **(b) altered real-player names on real-shaped rosters, in an app with ads and purchases.**
   - state right-of-publicity laws: the C.B.C. fantasy precedent against Keller and Hart;
   - Lanham Act false endorsement;
   - if you sell abroad: UK passing off and German personality rights (Kahn).
2. **Real-shaped rosters with fictional names.** Any publicity or privacy exposure in the US? Is it personal data under UK/EU GDPR if you sell there?
3. **Descriptive club names** ("Manchester Blue") for about 1,078 clubs, with real towns, real colours and generic league and European competition names: trademark and false-endorsement risk, and the review process to use.
4. **Facts in the game:** real past tables, winners, coefficients, league memberships and matchday dates, mapped to renamed clubs.
5. **The names editor and names-file import:** any exposure for enabling user-supplied real names.
6. **Data provenance:**
   - the CC0 Transfermarkt-derived set (dropped, but confirm);
   - StatsBomb's agreement and the parameters fitted on it;
   - football-data.co.uk, Metrica and the Opta-cited aggregates.
7. **Ads to a football game's audience:**
   - COPPA and US state privacy laws;
   - app-store age laws such as Texas SB2420;
   - the right age rating and defaults;
   - if UK: the Children's Code.
8. **Business set-up:** individual or LLC; liability; the DSA trader disclosure.
9. **Wording and trademarks:** the disclaimer's wording, and which trademarks to keep out of the listing ("Football Manager", "FIFA", "Premier League", "EFL", "Champions League", "UEFA", "PES", club names).

### ST3. Policies and pages (Sonnet High; drafts marked for the lawyer)

- **A privacy policy** covering:
  - game data stays on the device;
  - what AdMob collects, from Google's disclosure;
  - consent and ATT;
  - children;
  - contact.
- **Apple's standard EULA,** and a support page.
- Both hosted as static pages outside this repo.

### ST4. The listing (Sonnet High)

- A name, subtitle and keywords free of trademarks.
- Screenshots from the public world only.
- The age-rating questionnaire (ads and purchases; not the Kids category), plus any state age-consent requirements Apple applies.
- The App Privacy answers and the content-rights declaration.
- `ITSAppUsesNonExemptEncryption = NO`.
- Review notes explaining the offline engine and where the purchases are.

### ST5. Disclaimer and attributions (Sonnet High)

- **The disclaimer,** in About and in the listing: "An independent game. Not affiliated with, endorsed by or licensed by any club, league, governing body, player or players' association…".
- **`docs/ATTRIBUTION.md`, rewritten for the store build:** Wyscout's citation, SkillCorner's credit, openfootball and Wikidata. StatsBomb only with permission.

### ST6. Prices (you)

- Remove Ads at $6.99, between $5 and $10.
- Boosts at $0.99–$2.99.

### ST7. Launch and after (you, with help)

- Crash reports in Xcode Organizer.
- Every update goes through review.
- **A takedown process:** comply quickly, and swap the names file in an update.

## 7. Gates

**G1, after I0 and I1** (free; before paying Apple). Passes when:
- every dependency loads on the device, including the pydantic-core we built;
- cold start takes 6 s or less;
- an agent match takes 8 s or less on the 17 Pro Max (Phase D's budget);
- a sim week takes no more than twice as long as on the M3;
- peak memory is 1.2 GB or less;
- there's no crash in a 30-minute session.

If it fails:
- a missing wheel → its fallback from 1.2;
- too slow → `performance.md`'s P1–P2 first;
- neither works → stop here, having spent nothing.

**G2, after PW8 and PW9.** Passes when:
- on 1,000 paired fixtures, the public world passes every **rate** and **volume** target in `match_targets.yaml` that the personal world passes at the same commit, on ENG1 and EFL;
- misses on **reference** targets (all of ENG4's) are diagnosed, not gated;
- the other countries' reports show no league out of range;
- the blind play-test says it feels like real football.

If it fails: fix the generator, then measure again.

**G3, before submission.** Passes when:
- the lawyer's answers are recorded and the default name set is decided;
- PW7 is resolved (permission given, or the refits are in);
- ST3–ST5 are done;
- the guards pass on the archive that's uploaded;
- a TestFlight round with at least three outside testers finds no serious bugs, and the minimum device is set from their bench numbers;
- you accept the costs in 1.8.

## 8. Order, parallel work and models

| Step | Needs | Can run alongside | Model |
|---|---|---|---|
| I0 | the Xcode set-up | PW1, PW2, PW7's emails, ST2's questions | Opus High |
| I1 | I0 | PW2 | Opus High + engine-reviewer |
| I2a | — (any time; it's a bug today) | anything | Opus High + engine-reviewer |
| I2 | I2a (for its equality tests) | PW3–PW6, MO1–MO3 | Opus High |
| I3 | I2 | I4, MO1–MO3 | Opus High |
| I4 | I2 | I3 | Sonnet High, Opus review |
| I5, I6 | I2 (I6 also PW1's manifest) | I3, I4 | Sonnet High |
| PW1 | — | I0 | Opus High |
| PW2 | PW1 | I0, I1 | Opus High; Sonnet High for the moves |
| PW3, PW6 | PW1, PW2 | Track I | Sonnet High (Opus review of the club list) |
| PW4, PW5 | PW1, PW2 | Track I | Opus High |
| PW7 | — | anything | Opus High |
| PW8, PW9 | PW3–PW7 | never beside another heavy batch | engine-calibrator + Opus High |
| PW10 | ST2's answer | — | Opus High |
| MO1–MO3 | — | Track I | Opus High + engine-reviewer |
| MO4, MO5 | I3 | — | Opus High |
| MO6, MO7 | MO1–MO5 | — | Sonnet High |
| ST1 | G1 | — | you |
| ST2 | before PW10 and G3 | — | you (questions at Opus High) |
| ST3–ST6 | ST2's answers | — | Sonnet High |
| I7 | I6, ST1 | — | Sonnet High |
| I8 | G3 | — | you |

- **Every step follows the usual loop:**
  1. focused tests, then the full suite;
  2. the reviewer;
  3. update `progress.md`;
  4. commit with explicit paths, and push.
  - The repo stays runnable at every checkpoint.
- **This plan was written at Max; every step builds at High.** Use Max only if a gate fails and needs a redesign.

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| pydantic-core won't build for iOS | Medium | Blocks the app | maturin's iOS support and BeeWare's PyO3 work; ask on pydantic#12739; worst case, an older pydantic-core someone has built, then retest |
| Golden values move when SciPy goes | Low (port checked) | Days | Literal port; 100k-case property test; goldens checked |
| The phone's numbers differ from the Mac's | **High** | Low | Golden values are already per platform; saves are state, not replays; record iOS goldens under an explicit key (`platform.machine()` returns the model id on a device) |
| Slow or memory-starved older iPhones | Medium | Fewer devices | Measure on the 17 Pro Max in I0 and on testers' phones in I7; the increased-memory-limit entitlement; set the minimum device at G3 |
| Saves corrupted by read-only opens | Low after the fix | Severe | Only the base world opens immutable; the save-after-commit test (I2) |
| The existing market-cache bug skews equality tests | Certain until I2a | Confusing failures | I2a first |
| App Review rejects it over IP | Medium with (b), low with (a) | Delay | Fictional default; the lawyer; guards; no trademarks in the listing |
| A club name too close to a real one, among about 1,078 | Medium | Takedown or rejection | Collision checks; top divisions curated by hand; the lawyer's review process |
| App Review calls it "a website in a wrapper" (4.2) | Low to medium | Delay | Offline engine; native share, files and purchases; explained in the review notes |
| App Review or consent friction from ATT | Low to medium | Delay | Fallback: non-personalized ads only, with no ATT prompt (lower eCPM) |
| A data source forbids commercial use | Medium (StatsBomb) | Refits | PW7's emails now; Wyscout and SkillCorner refits; one parameter set |
| A takedown over altered names | Low to medium with (b) | Removal | (b) waits on the lawyer; swap the names in an update |
| The public world feels flat | Medium | Fewer players | G2; (c) names import; play-tests |
| Validating the full world takes long | High | Later launch | England first; the existing reports for the rest; one batch at a time |
| Ad revenue is tiny | High at small scale | Little money | Expected (1.8); keep spending at $99 until G2 |
| The engine gets tuned twice (EA world, then public) | High | Wasted batches | From PW8 on, acceptance runs on both worlds (section 11) |
| A store bundle ships EA data or trademarks | Low | Severe | Archive-phase guards; the clean-room test; a separate personal bundle id |
| The engine work in flight gets interrupted | — | Delay | This plan starts only when you place it |

## 10. Verification

- **I0:** bench numbers from the M3, the VM and the phone in `progress.md`, plus a screen recording of a live match on the phone.
- **I1:** the property and `erf` tests; the golden values; the subprocess import test without SciPy. (`uv run pytest` alone can't show this, because the dev group installs SciPy.)
- **I2a:** the view-then-advance equality test, also across a restart.
- **I2–I6:**
  - the save-after-commit test;
  - the capped-stepper `iterdump` tests and the pause/resume equality test;
  - the phone-mode API smoke test and the middleware rejection tests;
  - the XCUITest on the simulator (`just ios-build`);
  - `just e2e` still passing on a :8765 server, showing the web build is unchanged;
  - the guards refusing an EA world, an EA-provenance config file and a trademark string.
- **PW:**
  - the clean-room test;
  - the personal world rebuilt into a temp path, unchanged;
  - 1,000-fixture acceptance reports in `reports/engine/`;
  - the other countries' reports;
  - the outcome comparison table and the play-test notes.
- **MO:**
  - the boost tests and the import-boundary test;
  - StoreKit local tests (purchase, refund, restore);
  - AdMob test ads;
  - the e2e check that the web build makes no ad calls.
- **ST:** the pre-submission checklist ticked in `progress.md`, with a summary of the lawyer's answers.

## 11. Where it goes in the roadmap

- **It starts only when you place it in the order of work.** Three parts can start any time and cost nothing:
  - **I2a,** a bug fix that helps today's game too;
  - **I0** (a few sessions);
  - **PW7's permission emails.**
- **PW8 shouldn't run while the match-believability tuning is still moving.**
  1. Tune the engine once, on the EA world, and finish its phase acceptance.
  2. From then on, run every acceptance batch on both worlds, so the engine stays right for both.
- **If G1 says the phone is too slow,** the performance phase (P1–P2) comes first. The day-capped stepper (I2) is already its step 1.

## Later (after launch)

- `BGContinuedProcessingTask` (sims that carry on in the background, iOS 26+).
- The youth intake preview and its rewarded ad.
- Database packs on the phone.
- Store-world saves on the server.
- Neutral nation spellings.
- An extra scout slot, faster reports and a facility step, once those systems exist.
- Python 3.15 everywhere.
- (b) inspired names, if the lawyer says not yet.

## Sources (read 3–4 Nov 2026)

- [S1] Python docs, "Using Python on iOS": https://docs.python.org/3/using/ios.html
- [S2] python.org, Python releases for iOS: https://www.python.org/downloads/ios/
- [S3] BeeWare, Python-Apple-support: https://github.com/beeware/Python-Apple-support
- [S4] Briefcase v0.4.6 release notes: https://github.com/beeware/briefcase/releases/tag/v0.4.6. BeeWare 2026 Q3 roadmap: https://beeware.org/news/buzz/2026/2026q3-roadmap/
- [S5] NumPy iOS support PR: https://github.com/numpy/numpy/pull/28759. BeeWare's wheel index: https://pypi.anaconda.org/beeware/simple
- [S6] pydantic issue #12739, "Publish wheels for Android and iOS on PyPI": https://github.com/pydantic/pydantic/issues/12739
- [S7] maturin iOS support: https://github.com/PyO3/maturin/pull/2102 and https://github.com/PyO3/maturin/releases/tag/v1.10.2
- [S8] BeeWare 2026 Q1 roadmap (iOS support contributed to PyO3 and maturin): https://beeware.org/news/buzz/2026/2026q1-roadmap/
- [S9] Mantine browser support: https://mantine.dev/browser-support
- [S10] Apple TN2277, "Networking and Multitasking": https://developer.apple.com/library/archive/technotes/tn2277/_index.html. Forum: https://developer.apple.com/forums/thread/802375
- [S11] Apple, BGContinuedProcessingTask: https://developer.apple.com/documentation/backgroundtasks/bgcontinuedprocessingtask
- [S12] Apple Developer Forums on BGContinuedProcessingTask in practice: https://developer.apple.com/forums/thread/802073
- [S13] New App Store age ratings, and Texas SB2420: https://www.pocketgamer.biz/apple-overhauls-app-store-age-ratings-with-new-categories and https://trysonar.app/blog/app-store-age-rating
- [S14] EU trader requirement: https://www.macrumors.com/2024/10/17/developers-eu-app-store-trader-requirements/ and https://www.macrumors.com/2025/02/18/european-union-trader-status-deadline/
- [S15] Google, IDFA explainer and UMP: https://developers.google.com/admob/ios/privacy/idfa
- [S16] Google, App Store data disclosure for the Mobile Ads SDK: https://developers.google.com/admob/ios/privacy/data-disclosure
- [S17] transfermarkt-datasets: https://github.com/dcaribou/transfermarkt-datasets
- [S18] StatsBomb Open Data: https://github.com/statsbomb/open-data
- [S19] Secondary readings of the StatsBomb agreement (not verified against the PDF): https://github.com/leovferreira13/sports-data-visualizer/issues/8 and https://hivebook.wiki/wiki/statsbomb-open-football-data-and-the-statsbombpy-package
- [S20] Metrica sample data: https://github.com/metrica-sports/sample-data
- [S21] Wyscout soccer match event dataset (figshare): https://figshare.com/collections/Soccer_match_event_dataset/4415000/2. Paper: https://www.nature.com/articles/s41597-019-0247-7
- [S22] SkillCorner Open Data: https://github.com/SkillCorner/opendata
- [S23] Gradient/PFF 2022 World Cup dataset: https://www.gradientsports.com/blog/pff-fc-release-2022-world-cup-data
- [S24] ClubElo API: https://clubelo.com/API
- [S25] football-data.co.uk notes: https://www.football-data.co.uk/notes.txt
- [S26] openfootball football.json: https://github.com/openfootball/football.json
- [S27] Wikidata licensing: https://www.wikidata.org/wiki/Wikidata:Licensing
- [S28] C.B.C. Distribution v. MLB Advanced Media (8th Cir. 2007): https://caselaw.findlaw.com/summary/opinion/us-8th-circuit/2007/10/16/153160.html
- [S29] Keller v. EA (9th Cir. 2013): https://gameinformer.com/b/news/archive/2013/07/31/court-rules-that-ncaa-and-ea-are-not-protected-under-first-amendment-in-likeness-suit.aspx
- [S30] Kahn v. EA: https://www.pinsentmasons.com/out-law/news/football-game-banned-over-players-image-rights
- [S31] Project Red Card: https://cms.law/en/gbr/legal-updates/the-future-of-sports-data-project-red-card-and-performance-data
- [S32] eCPM benchmarks: https://blog.playio.co/mobile-game-ecpm-benchmarks-2026, https://gamedevreports.substack.com/p/tenjin-ad-monetization-in-mobile, https://www.statista.com/statistics/1394672/ecpm-interstitial-ads-ios-usa
- [S33] Conversion rates: https://maf.ad/en/blog/mobile-game-conversion-rates/ and https://gamedeveloper.com/business/-i-breakout-ninja-i-dev-highlights-the-waning-appeal-of-ad-removal-iaps
- [S34] App Store Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
