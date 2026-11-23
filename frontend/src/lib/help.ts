// The Help tab under the version tag (components/WhatsNew.tsx): what the game lets you do, topic by
// topic. It is written from what the screens do, so when a change adds or alters something a
// player can do, update the topic here and add an entry to data/changelog.yaml.
//
// A topic's blocks are shown in order: a string is a paragraph, an array of strings a bullet list.

export type HelpBlock = string | string[]

export interface HelpTopic {
  id: string
  title: string
  /** What the topic covers, in a line. It is searched along with the title and the text. */
  summary: string
  blocks: HelpBlock[]
}

export const HELP_TOPICS: HelpTopic[] = [
  {
    id: 'start',
    title: 'Starting a career',
    summary: 'Choosing a club, the sandbox budget, the board and the currency.',
    blocks: [
      'The start page appears when no career is loaded, and from Save / Load in the menu. Saved careers are at the top under Continue: Load opens your last manual save, Autosave the game’s own. Under New career: 1, type a manager name and pick a save slot (the first free one is chosen for you); 2, choose a country and a league, then tap a club (each shows its squad’s average rating and its reputation, so you can see how big a job it is), or switch to NCAA program to coach a US college team (see Coaching a college program), or to Manage a country to manage only a national team, with no club (see International football); 3, Options holds the board, the currency and a sandbox budget. Then press Start.',
      [
        'Leagues: 62 leagues in 54 countries: every country with clubs in UEFA’s competitions (Russia aside, and Liechtenstein, which has no league of its own). England has four divisions; Spain, Italy, Germany and France have their lower divisions too; every other country has its top flight, each with its cup. The country picker lists the big leagues first; type to find any country, or filter by continent. Sweden, Norway, Finland, Iceland, Ireland, the Baltic countries and a few more really play spring to autumn; like every league here, they play August to May.',
        'Squads in the smaller leagues: where FC 27 has no club, its squad is built from real data: the players who really played for it (with ratings from their market values, so a club’s best player stays its best), filled out with made-up players. Each league’s strength comes from its country’s UEFA coefficient, and each club’s from its real results (its Elo), so the champions are stronger than the bottom side.',
        'Save slot: starting a new career in a slot that already has one replaces it. A yellow warning tells you.',
        'Sandbox budget (optional): type an amount, in millions of the money shown, and your club starts with that to spend on transfer fees and wages (up to about €10 billion). Leave it empty to play on the board’s budget. A sandbox starts with the board off, unless you switch it on.',
        'Board expectations: on, the board expects a league finish, its confidence in you moves with results, and your budget each season comes from the club’s income and cash. Off, there are no targets and all your cash is your budget. You can change it later on the Finances page.',
        'Currency: pick dollars, euros or pounds next to the budget. It only changes how money is shown (prices are quoted as round figures in it), and you can change it later on the Finances page.',
        'Simulation: choose which leagues are fully simulated. Everything is, unless you change it; fewer fully simulated leagues make simulating faster. You can change it later under Settings (see Simulation settings).',
      ],
    ],
  },
  {
    id: 'time',
    title: 'The dashboard, Continue and Sim to…',
    summary: 'Moving time forward, match days, stopping for offers.',
    blocks: [
      'The dashboard shows your next match, the league table around your club, your recent results (click one for its match report), which players are injured, suspended or tired, and a finance summary (click it to open Finances).',
      'Time only moves when you say so.',
      [
        'Continue plays the days forward, with every other match in the world, until your next match day. Then the button turns orange and says Match day. Continue stays on whichever page you were on: click Match day when you are ready to play.',
        'Continue also stops when a club bids for one of your players (it opens the Transfers page), and at the end of the season (with a season summary).',
        'Sim to… skips further: one week, one month, the end of the season, your next cup match, or a date you choose (up to 400 days ahead). Your own matches on the way are played instantly; the matches on the day you pick are left for you. Stop ends it early. It also stops for a bid on one of your players. If it reaches the end of the season it stops there, with the season summary.',
        'On a phone, Sim to… and Save are in the ⋯ menu in the header.',
        'You can’t sim while a match you are watching is still going: finish it first.',
      ],
    ],
  },
  {
    id: 'saving',
    title: 'Saving and loading',
    summary: 'Save, autosave and the three slots.',
    blocks: [
      'Each career lives in one of three slots. Open Save / Load in the menu to see them, with the club, the manager and the game date.',
      [
        'Save (the button in the header) writes the slot’s save and keeps a few older saves as backups.',
        'The game also autosaves as you play: after Continue, after your matches, after Sim to…, and after transfer, contract and finance actions. On the start page, Load opens the last Save and Load autosave the latest autosave (which may be newer).',
        'If the game was updated or restarted while you were away, it is back on the start page: load your slot. Load autosave if you haven’t pressed Save lately.',
        'Starting a new career in a slot replaces what is there.',
      ],
    ],
  },
  {
    id: 'squad',
    title: 'Your squad and players',
    summary: 'The squad table, player pages, ratings, potential and condition.',
    blocks: [
      'Squad lists your players. Click a column heading to sort by it, and use the buttons to show goalkeepers, defenders, midfielders or attackers. The columns are position, team (XI, Bench or Reserve, as set on Tactics), name, age, Ovr, condition, form, appearances, goals and assists, value, wage and the year his contract ends. INJ and SUS mark injured and suspended players.',
      [
        'Ovr is a player’s overall rating, his rating in his best position. The arrow beside it shows how it has changed since the season began.',
        'Condition is how fit he is going into a match. The dashboard lists up to five players below 80%.',
        'Click a player to open his page. On a computer, the left and right arrow keys (or Previous and Next) move through the list you came from.',
      ],
      'A player’s page shows his overall, whether he is rising or falling lately, six headline ratings (the outlined ones count most for his position), every attribute, his best roles, his details (value, wage, contract, record this season) and his record season by season.',
      'Potential is an estimate shown as a range, never exact. It is narrower for your own players and for older players, and wider for players at other clubs.',
      'Release, on your own player’s page, ends his contract at once and he becomes a free agent.',
    ],
  },
  {
    id: 'positions',
    title: 'Positions and position training',
    summary: 'How well a player plays out of position, and how to make a new position natural.',
    blocks: [
      'The coloured badges under a player’s name are the positions he can play comfortably; the filled one is his main position.',
      'A player gives his full rating only in positions he is natural in. In any other he loses a share of it: the less familiar he is, the more he loses. The Positions card on his page lists every position he knows with how natural he is there (natural, accomplished, competent, awkward or unconvincing), his rating there and what it costs him. On Tactics, a ring marks a starter who is not fully at home (amber a little, red out of position).',
      [
        'Position training: on your own player’s page, choose a position under Position training and press Train, or use Train on a row of the Positions card.',
        'Assistant trains positions (Settings → Position training, or the switch on a player’s Position training card): every one of your players not learning a position starts on his best alternate one, the position he already plays a little and knows best, at once and on the 1st of each month, until he is natural everywhere he plays. You can still choose or stop any player’s training yourself. Managing a national team, you train its squad’s players too (they learn at their clubs): by hand on a player’s Position training card, or with the national team’s own assistant switch (Settings → Position training, or International → My country).',
        'It works on one position at a time. Each month he gets more familiar there, faster when he is young, until he is natural. Then he plays it at his full rating and you can train another position.',
        'Training doesn’t change his attributes. Stop cancels it, and the news tells you when he gets there.',
      ],
    ],
  },
  {
    id: 'tactics',
    title: 'Tactics',
    summary: 'Formation, roles, the line-up, instructions and saved tactics.',
    blocks: [
      'Tactics sets how your team lines up. Changes apply at once and are used in your next match.',
      [
        'Formation: choose from 11 formations. Changing it resets the roles and picks the best XI and bench again. Pick best XI and bench picks them again for the current formation.',
        'Moving players: on a computer, click a player (on the pitch, in the Starting XI list, or among the bench and reserves), then click where he should go: a position on the pitch, another player to swap with, or an empty bench place. You can also drag and drop. Esc cancels. On a phone or tablet, tap a player, then tap where he should go.',
        'Roles: click a position on the pitch to see who plays there and choose his role. The roles on offer depend on the position, and each says what it does.',
        'Ratings: the number on each position is the player’s rating there. Hover a starter in the list (or look under his name) for the steps: his overall, then role, familiarity and fitness.',
        'Bench: you choose the substitutes; everyone else is a reserve. Bench (auto) means the game picks them. Injured and suspended players can’t be picked.',
      ],
      'Team instructions are Mentality, Pressing, Defensive line, Width, Tempo and Passing. They change what your players do (where they stand, what they try, how hard they run), never how good they are, and each has a cost. Attacking leaves fewer players behind the ball. High pressing tires players and leaves gaps behind. A high line squeezes space but leaves room in behind. Wide stretches the opponent but spreads your own players. Fast tempo hurries passes. Direct passing gets the ball forward quickly but loses more long balls.',
      'Saved tactics: the Saved tactics menu stores the current tactic under a name (its formation, roles and instructions, and the line-up too if you tick it). Load or delete one from the same menu. You can keep up to 20, and saving under an existing name replaces it.',
    ],
  },
  {
    id: 'match',
    title: 'Match day and the live match',
    summary: 'Watching, speeds, highlights, substitutions, red cards, the assistant and instant results.',
    blocks: [
      'When Continue stops at a match, the Match day page shows the fixture and your starting XI with their ratings and condition. Watch match plays it live. Instant result plays the same match at once and shows the match report. Tactics lets you change your set-up first.',
      [
        'Pause and Play; speeds 0.5×, 1×, 2×, 4× and 8× (at 1× a half takes about five minutes). Speed only changes how fast you see the match; the match itself is the same at any speed.',
        'Full match or Highlights. Highlights jumps from chance to chance (shots, goals, penalties and red cards) and replays each one.',
        'Instant result finishes the match at once. Names turns the player names on the pitch on or off.',
        'Click or tap a player on the pitch for his card: energy, rating, cards, role (which you can change there) and match stats.',
        'The tabs beside the pitch are Commentary (key moments in bold), Stats, Tactics and Subs. When a goal is scored the picture holds for a few seconds with the scorer shown.',
      ],
      'Tactics tab: change the formation and the instructions while you watch, and they apply straight away. Assistant adjusts tactics to the score and the opponent hands the tactics to the assistant: your settings become its plan and it adjusts from there. It is off for your side until you tick it.',
      [
        'Subs tab: you can make up to five substitutions. Assistant makes subs is on to begin with and makes changes from about the hour mark; untick it to do them all yourself.',
        'On the pitch view, drag a substitute onto the player he replaces (on a phone, tap one and then the other). Drag one player onto another to swap their positions. The List view does the same with rows and a button.',
        'A change that is waiting to be made shows at the top of the Subs tab with an Undo button and a choice of role for the newcomer. Changes made together count as one stoppage. When it is made: the fourth official waits for a dead ball, so a change chosen while the match runs is made at the next stoppage; one chosen while paused at a break or a restart is made as play resumes; and one chosen while paused with the ball in play is made at the first stoppage after play resumes.',
        'After a red card, move a player into the empty position (drag him onto it, or pick him and then the position) so the team can reshape. Cards show beside the players.',
        'Half-time shows the stats, who is most tired and who is rated best. Make changes in the Tactics and Subs tabs, then start the second half. Cup ties can go to extra time and penalties.',
        'At full time, Match report shows the stats, the events and every player’s rating.',
      ],
      'Home advantage: playing at home is worth about a quarter of a goal a match, as in real football. The crowd unsettles the away side’s players when they are under pressure, so they choose and pass worse, and referees show away sides about a third of a yellow card more a match. Home sides win about 40% of matches, away sides about 30%. A neutral ground (a cup final) has none of it.',
    ],
  },
  {
    id: 'transfers',
    title: 'Transfers: finding and signing players',
    summary: 'Search and filters, offers and haggling, loans in, free agents.',
    blocks: [
      'You can sign players only while your country’s transfer window is open. The Calendar marks the windows, and the offer screen tells you when yours is closed.',
      [
        'Find players: search by name, position, overall, age, value, league, free agents, or listed players only. The results show his club, his value and when his contract ends. Offer makes a bid (Sign for a free agent).',
        'The offer screen: set your bid (buttons set it around his value or at their price), the weekly wage and the number of years you offer. It shows what the deal costs against your budget: the fee, this season’s wages, the total, and the whole contract.',
        'The club answers first: it accepts, counters with the price it wants, or refuses. Then the player answers: he has to like the wage and the club. A free agent costs no fee, only the wage he wants.',
        'Haggling: a club will only come down so far. A fair offer brings its price down towards your bid, a lower offer is countered at the same price, and an insulting one costs two rounds. After four rounds its price is final and talks end for the window.',
        'A signing costs the fee plus his wages for the rest of the season, out of your budget (see Finances).',
        'Loan: for players aged 23 or under at other clubs. Choose how much of his wage you pay (50%, 75% or 100%). He joins until the end of the season. His club lends only players it can spare, and he goes where he will play.',
        'Market overview shows the season’s biggest transfers, the 20 most valuable players, and the best prospects aged 21 or under.',
      ],
    ],
  },
  {
    id: 'selling',
    title: 'Transfers: selling, loans out, offers and contracts',
    summary: 'Offers for your players, listing a player for transfer or loan, contract renewals.',
    blocks: [
      [
        'Offers for your players: other clubs bid for your players while their window is open. A bid stands for three days, and up to three can be waiting at once. Accept it, Reject it, or Counter with an amount (the bidder pays a counter if it can afford it, or walks away). At most four bids a window come in for your players.',
        'Continue and Sim to… stop on the day a bid arrives. Continue opens the Transfers page.',
        'Transfer list and Loan list (on the Sell tab, or on a player’s page): a player on the transfer list is one clubs bid to buy. A player on the loan list is one clubs that need cover ask to borrow for the season, at any age. Not for sale takes him off both. Clubs can still bid for a player who isn’t listed, and you can turn them down.',
        'Loans out: when a club asks to borrow one of your players you can accept or reject (there is no counter). The Sell tab lists your loans in and out, with who pays the wage.',
        'If you sell a player, other clubs’ bids for him are withdrawn.',
      ],
      'Contracts end on 30 June. Open Contracts on the Transfers page to see the players in their last season, each with the wage and length he asks. Type the wage you offer (he wants his asking wage or more) and press Renew. The raise comes out of your budget for the weeks left. Some players won’t sign. Any you haven’t renewed by 30 June leave as free agents, and news reminds you on 1 April, 1 May and 1 June.',
      'History lists the moves your club has made, or everyone’s.',
    ],
  },
  {
    id: 'finances',
    title: 'Finances',
    summary: 'Balance, budgets, wages, board confidence, prize money and currency.',
    blocks: [
      [
        'Balance is the club’s cash. Budget is what you can spend this season on transfer fees and new wages. If the club is in debt there is no budget at the start of the next season.',
        'Wages shows your weekly wage bill. With the board on, it also shows how much your income supports, and wages above that come off next season’s budget. With no board there is no wage limit; the page shows how much more your budget could pay each week.',
        'Each month: league TV money, commercial and matchday income, wages and running costs, with the profit at today’s rates. The profit reaches your balance on the 1st of each month and your budget at the start of the next season.',
        'Changes notes when a part of that moves a lot, for instance after a promotion or a new wage bill. Transactions lists one-off money: transfers, prize money, parachute payments and the like.',
      ],
      'Prize money is paid when a league ends, by final position with the champions getting the most. Cups pay a prize for each round won. A club that drops a division gets a parachute payment.',
      'The board: it expects a league finish, and shows your position, its confidence in you out of 100 and a mood word. Confidence moves each month with where you are against the target. Turn Board expectations off for no targets and a budget that is all your cash.',
      'Show money in sets dollars, euros or pounds. Other clubs’ pages show their budgets and balances, rounded.',
    ],
  },
  {
    id: 'calendar',
    title: 'Calendar and fixtures',
    summary: 'The month view, transfer windows, simming to a day, and the season’s matches.',
    blocks: [
      [
        'Calendar shows a month at a time (Monday first), with arrows and a Today button. Each of your matches shows home or away, the opponent, the competition (a coloured stripe: Champions League blue, Europa League orange, Conference League green) and then the result; click a played match for its report.',
        'A yellow line marks the days a transfer window is open, and a blue tint marks an international break. Up next lists your coming matches.',
        'Click a coming day to sim to it. Your matches on the way are played instantly, and that day’s matches are left for you. It stops early for a bid on one of your players or at the end of the season.',
      ],
      'Fixtures lists all your club’s matches for a season with the date, the competition, the opponent and the result; a season picker shows past seasons. Click a result for the match report.',
    ],
  },
  {
    id: 'tables',
    title: 'League tables and cups',
    summary: 'Tables, promotion and relegation zones, past seasons, cups.',
    blocks: [
      [
        'League shows a table for any league in the game: pick a country, then a league. Zones are coloured for promotion, play-offs and relegation, and your club is in bold. In a top division the European places are in colour too: Champions League blue, Europa League orange, Conference League green (a stripe only for a place in a qualifying round), with a key under the table. A finished season’s table shows where clubs actually went. A season picker shows past seasons.',
        'Finding a country: your own country and England, Spain, Italy, Germany and France are buttons at the top; every other country is in the All countries box, listed by continent and strongest first, which finds a country by its name or by the name of one of its leagues or cups (accents don’t matter: try “Süper” or “Eliteserien”). Where the game has leagues on more than one continent, a continent filter beside the box narrows that list.',
        'Between seasons the League page keeps showing last season’s final table until the new season’s first league match.',
        'A league with play-offs shows them under its table: each round’s ties and results as they are played, and the rounds still to come with their dates. Leagues of conferences or zones show each one’s table (or the whole league’s, with Overall); leagues of two tournaments a season (an Apertura and a Clausura) show each tournament’s table and the whole season’s. The titles won so far this season are listed above the table.',
        'Cups shows a country’s cups (yours to begin with), every round with its ties and results, what is still to come, and how your club is doing. Pick another country (the same buttons and All countries box as on League) or cup, or a past season.',
      ],
    ],
  },
  {
    id: 'europe',
    title: 'European competitions',
    summary: 'The Champions League, Europa League and Conference League: who qualifies, the league phase, the knockouts and the prize money.',
    blocks: [
      'Europe in the menu (it only appears in a game that has the European competitions) shows the Champions League, the Europa League and the Conference League. It opens on the one your club is in this season, and has a season picker for past ones. A new career has them from its first season; a career started before they arrived gets them when its next season starts.',
      [
        'Qualifying: a country’s places in each competition and round depend on its place in UEFA’s country ranking (the sum of its clubs’ results over five seasons, as it stood two seasons earlier). Places go by league finish, to domestic cup winners (a Europa League place) and to the holders; the two countries with the best season also get an extra Champions League place each (a European Performance Spot). A club is in the highest competition it earns, and its lower place passes to the next club.',
        'Qualifying rounds: the first, second and third qualifying rounds and the play-off round are played in July and August. Each competition has paths, so that champions meet champions (the Champions Path) and other clubs meet each other (the League Path in the Champions League, the Main Path in the Europa and Conference Leagues). Better-ranked countries’ clubs come in at later rounds. The winners go on, and the losers drop down: from the Champions League into the Europa League, and from there into the Conference League, whose losers are out. The page has a section for each round and path, and a clash of the same country’s clubs is avoided in the draw.',
        'League phase: 36 clubs in one table. In the Champions League and Europa League each club plays 8 matches, against two clubs from each of four pots (one at home, one away); in the Conference League each plays 6, against one club from each of six pots. Pots follow the clubs’ European record over five seasons (the Champions League holders are always in pot 1), and nobody plays a club from their own country. The matchday picker shows each matchday’s fixtures and scores; click a played match for its report.',
        'After the league phase: the top 8 go straight to the round of 16, and 9th to 24th meet in a two-legged knockout play-off for the other eight places. The rest are out. The round of 16, quarter-finals and semi-finals are two legs, and the final is a single match at a neutral ground. There is no away-goals rule: extra time and penalties decide a tie that is still level.',
        'Aggregate scores: a second leg shows the score over both legs in brackets, as in 2 – 1 (4 – 3 on agg.), on fixtures, results, match reports and cup rounds (any two-legged tie: European rounds, domestic cup semi-finals, league play-offs). Before a second leg, match day shows the first leg’s score, and during it the live score bar shows the running aggregate under the score.',
        'Prize money: a starting fee, a payment for each league-phase win and draw, a payment for each knockout round a club reaches, and a bonus for the winners. The Champions League pays most. It is a bonus on top of a club’s normal income.',
        'Next season: the Champions League and Europa League winners go into the Champions League league phase, and the Conference League winner into the Europa League’s. Their own league places pass to the next clubs.',
        'Fixtures: European matches are on fixed dates, nearly all midweek. A club’s league and cup matches move to leave it two clear days either side (just one, now and then, in a crowded spell).',
        'The page also lists the qualifying rounds and everyone who entered, with how they qualified (and where they dropped from), grouped by pot once the draw is made. Its Rankings view shows the UEFA country ranking (five seasons and the total, with your country highlighted) and the club coefficients that seed the draws.',
      ],
    ],
  },
  {
    id: 'superdraft',
    title: 'The MLS SuperDraft',
    summary: 'Drafting college players into an MLS club in January.',
    blocks: [
      [
        'Every January the MLS clubs draft the college players of the NCAA season just finished: three rounds, in reverse order of last season’s table, with the play-off clubs after the rest and the MLS Cup winners last (in your first season, the table so far). Managing an MLS club, you get a reminder two weeks before.',
        'Open Draft (in the menu for an MLS club, or from the MLS table) to see the prospects: each one’s college, class, position and overall, and your scouts’ view of his potential as a range. Add the ones you want to your board and put them in order. When your club is on the clock it takes the best one still on your board; if none is left, your scouts choose.',
        'Picks join your squad at the league minimum if MLS’s rules allow (roster places, the salary budget, international slots). Generation adidas picks (underclassmen who declared) go on the supplemental roster and cost nothing against the budget. A pick who can’t be signed yet stays yours: sign him from the Draft page once you’ve made room, while you hold his rights. No other MLS club can sign him meanwhile.',
      ],
    ],
  },
  {
    id: 'mls',
    title: 'MLS’s roster rules',
    summary: 'The MLS roster page: the salary budget, designations, TAM and GAM, slots and the roster model.',
    blocks: [
      'An MLS club plays under MLS’s roster rules. MLS roster (a button on Squad and on your club’s page, in the menu, and under More on a phone) shows where your club stands. Money is shown in your currency, a year at a time.',
      [
        'Salary budget: what the senior roster (slots 1–20) is charged, after TAM and GAM buy-downs, against the budget. A player’s charge is at most the maximum charge; the Supplemental Roster (slots 21–30) isn’t charged.',
        'Designations: each player is a Designated Player (DP: charged a fixed amount whatever he earns), U22 Initiative (signed at 22 or younger), Senior, Supplemental, Homegrown (senior or supplemental) or Generation adidas. Pick one from the list beside him; if a rule forbids it, the reason appears under him and nothing changes.',
        'TAM and GAM: Targeted and General Allocation Money buy players’ charges down, TAM first. The game spends only what’s needed; the Buy-down column shows what each player takes. GAM left over carries into next season and can buy an international slot.',
        'Slots: DPs and U22 players by the roster model, international slots (8 a season; Buy a slot buys one from a club with one to spare, for GAM), and the senior and supplemental rosters.',
        'Roster model: Model 1 has 3 DPs and 3 U22 players, Model 2 has 2 DPs, 4 U22 players and more GAM. You can change it until your first league match of the season.',
        'Compliance: anything breaking the rules is listed in red at the top. Until it is fixed you can’t sign or borrow anyone (unless the move itself fixes it); matches are never blocked.',
      ],
    ],
  },
  {
    id: 'college',
    title: 'College soccer',
    summary: 'NCAA conference tables, the RPI, the NCAA tournament bracket and the draft pool.',
    blocks: [
      'College in the menu (under More on a phone) follows NCAA Division I men’s soccer, whose players feed MLS’s SuperDraft. A career started before college soccer joined the game gets it from its next season.',
      [
        'Conferences: pick a conference for its table (ranked on conference games only; the marked places go to its tournament), or Tournament for its bracket in November. Its winner takes an automatic bid to the NCAA tournament. Switch Conference games to All games to see each team’s record over every college game this season (non-conference games and the tournaments too; a shoot-out counts as a draw), in the same order.',
        'RPI: the Rating Percentage Index, which picks the NCAA’s 25 at-large teams and its seeds, with each team’s overall record (W-D-L).',
        'NCAA: the 48-team bracket, picked on 16 November. Seeds 1–16 have a bye to the second round; the College Cup (the semifinals and final, at a neutral ground) is in mid-December. Click a played match for its report, or a club for its page.',
        'Draft pool: after the College Cup, the seniors and a few underclassmen signed by Generation adidas (GA) who are up for the SuperDraft, with their college, class, position and overall. Underclassmen may declare from their sophomore year: never straight after their freshman year.',
        'Draft history (College → Draft pool → Draft history, or Past drafts on the SuperDraft page): every SuperDraft of your career, pick by pick: who picked him, his college (a college coach’s own alumni are highlighted, and My alumni lists them across every draft), where he plays now, his overall and market value now, and his professional appearances, goals and assists since.',
      ],
    ],
  },
  {
    id: 'college-coach',
    title: 'Coaching a college program',
    summary: 'An NCAA program as your club: what a college coach sees, and how players come and go.',
    blocks: [
      'On the start page, under Your club, choose NCAA program, pick a conference and tap a program. Each shows its tier as stars (five for a national power) and its state. A college program has no board, budget, wages or transfers: your players come from high-school recruiting.',
      [
        'Your matches: the regular season from late August, your conference’s tournament in November, then the NCAA tournament if you make the field. Continue, Match day and the live match work as for any club. The whole NCAA is your league, so it is always fully simulated.',
        'Continue also stops on the college year’s set days, the day after each, with its news: the NCAA tournament’s selection, the College Cup final, the MLS SuperDraft, the opening of recruiting offers, signing day and the class’s close, and, once your games are over for the season, the first of each month.',
        'News: after Continue or a sim the news comes in sections: your team first, the conference champions a line each, the rest of college soccer, recruiting, and the world beyond. Leagues you set to fast results (Settings → Simulation) stay out of the news and of the season summary; following no professional league at all, Europe’s competitions, the Club World Cup and other clubs’ retirements stay out too.',
        'Season summary: your conference finish, record over every game, RPI rank, NCAA run and the class you signed, then every conference’s champions, your squad’s development and the other news.',
        'Squad: each player’s class (Fr, So, Jr, Sr), his scholarship (Full, a percentage, or Walk-on) and the season he leaves after. A Draft mark means he has declared for the MLS SuperDraft.',
        'Leaving early for the draft: after the College Cup the country’s best underclassmen (8, by potential, then overall) declare for the SuperDraft. All season the draft watch shows who would go if it were today: May leave (one of those 8) or Draft watch (next in line) beside his name, and a news warning on 2 November (Continue stops there). On his page, Ask him to stay, once a season, before he declares or after (until the draft in January): his chance is shown, higher with more playing time and a bigger program, lower the bigger a prospect he is and once he has declared. If he agrees he stays another season; if not, he has made up his mind.',
        'Next season (Squad → Next season, or the card on Home): your squad after this season by line: who joins (your committed and signed recruits with their stars and the staff’s overall estimate; portal transfers marked with their school), who leaves (graduating seniors, players who declared, those likely to declare early) and who stays (a class on), with the places left under the 28-player limit.',
        'Top 25: a program in the RPI’s top 25 shows its rank before its name (#12 Wake Forest) on links, fixtures and the match-day screen; before a season’s first games, last season’s final ranking is used.',
        'Dashboard: your conference’s table, and your program’s overall record (every game this season), place in the conference, RPI rank and prestige. Every program’s club page shows the same for it: its record, conference finish, RPI rank, NCAA run, titles, tier and prestige.',
        'Tactics: Pick best XI and bench puts the best players in the formation, each in the role he rates highest in. Automatic substitutions (yours when the assistant manages, and the other teams’) bring on whoever rates highest in the tired player’s position, in his best role there.',
        'Players leave by graduating after their senior season, by declaring for the SuperDraft (seniors, and the best underclassmen after the College Cup), or when you let one go (Release on his page): he turns pro as a free agent. A program can’t sign professionals.',
        'Prestige (0–100) starts from the program’s tier and moves at each season’s end with your last three seasons: your RPI rank, NCAA tournament wins and titles. Each NCAA tournament win also lifts it at once (1.5), and the national title more (6), so recruits still deciding hear about a run. The higher it is, the better the recruits who want you.',
        'OP player (on Recruiting): once every four seasons you may sign a freshman with a professional’s ratings (about 78 overall) at a random position, on no scholarship. He never declares early for the draft, so he plays all four years. Your roster needs a free place.',
        'The menu leaves out Transfers, Finances, the professional League, Cups and Europe. On a phone the bar has Home, Squad, Tactics and Recruiting; College is under More.',
      ],
    ],
  },
  {
    id: 'program-builder',
    title: 'Program builder: money and facilities',
    summary: 'The college game mode with a budget, training facilities and a stadium.',
    blocks: [
      'A college coach chooses the game mode when starting the career (Classic or Program builder), or turns the program builder on later from Program in the menu (it can’t be turned off). In the program builder every NCAA program has money, and builds its training facilities and stadium.',
      [
        'Money: each season starts on 1 July with the athletic department’s allocation (bigger for a bigger-name program); the season’s scholarships (a full one about $55,000 a year), coaching staff and facility upkeep are paid then. Home games sell tickets, away games cost travel, boosters give after the regular season (by wins and a conference title) and after the NCAA tournament, and every NCAA tournament game pays both teams. Program shows the balance and this season’s money line by line.',
        'Scholarships for next season’s class: set how many full scholarships to put aside (Program). Recruiting’s money left comes from it, so a richer program can offer more. You can’t set more than you can afford after next season’s costs, nor less than your class has already committed.',
        'Training facilities (levels 1–5): your players grow towards their potential faster, up to 24% faster at level 5. Their potential doesn’t change; they just get there sooner.',
        'Stadium (levels 1–5, 1,000 to 12,000 seats): more seats sell more tickets when people want to come (better prestige, a winning run, a big-name visitor and tournament games fill it). A bigger, fuller crowd puts more pressure on the visiting team, as home advantage works in the match engine: their decisions and passing suffer more. A small crowd gives you less home advantage than a professional club has, a full 12,000 the same.',
        'Building: pay for the next level on Program. Work ordered before 1 March is ready for next season; later, the season after. One project per facility at a time, and each level costs more upkeep.',
        'Recruits count your facilities as part of your program’s appeal, beside its prestige.',
        'The other programs build too, keeping some money in hand, so winners get richer and build up, and rivals catch up.',
      ],
    ],
  },
  {
    id: 'lower-divisions',
    title: 'Divisions II and III, and the transfer portal',
    summary: 'Where unsigned recruits develop, and how their best move up to D-I.',
    blocks: [
      'The NCAA’s Divisions II and III are in the game: about 200 D-II and 400 D-III programs, real schools in their conferences, played with quick results (scores, scorers and ratings, no full match). Nobody coaches them; on the College page, switch to Division II or III for their conference tables, RPI rankings and national tournament. A top-25 team in D-II or D-III shows its rank beside its name (“D-II #3”), as D-I’s top 25 do (“#3”).',
      [
        'Their seasons: each team plays its conference once and fills the rest with non-conference games, from late August to early November. Each conference’s table winner takes its title and an automatic bid; the best of the rest by the RPI (as in D-I) fill the national tournament (36 teams in D-II, 64 in D-III), single matches to the final in early December.',
        'Hidden gems: the high-school seniors no D-I program signed don’t leave the game any more. At the season’s start they join D-II and D-III programs as freshmen (the best of them to the strongest D-II programs), keeping their potential, and develop there. Rosters are filled with generated freshmen beside them; seniors graduate and leave.',
        'The transfer portal opens on 8 December, after the national tournaments: the best D-II and D-III players who aren’t seniors (60 at most, each at least a 43 overall now) want to move up. They join D-I’s recruiting class: on Recruiting, the Transfer portal tab lists them, each marked with his school. Offer, visit and sign them as you would a high-school senior; the other D-I programs recruit them too.',
        'A portal player who signs joins his D-I program at the season’s start, a class on from where he was (a D-II sophomore arrives a junior), on the scholarship he signed for. One nobody signs stays at his school.',
      ],
    ],
  },
  {
    id: 'all-division',
    title: 'The All-Division Tournament',
    summary: 'D-I, D-II and D-III’s best, after the national finals, to settle the best team in college soccer.',
    blocks: [
      'Once D-I’s College Cup and the D-II and D-III finals are played, the All-Division Tournament (on the College page, the All-Division tab) brings the three divisions together, from 16 to 29 December. Its games count in no division’s table, RPI or record.',
      [
        'The field (picked on 15 December): each division’s national champion, then its best by the season’s final RPI. 16 from D-I, 12 each from D-II and D-III, 40 in all.',
        'Byes: D-I’s top four start in the Round of 16 (two byes); D-I’s 5th to 8th and the top four of D-II and D-III start in the second round (one bye); the rest play the first round.',
        'Matchups: a set bracket, all of it known once the field is picked, so a team’s path doesn’t change as others win or lose. It mixes the divisions from the first round (D-I’s 9th to 16th and D-II and D-III’s 5th to 12th), but D-II and D-III’s top two meet none of D-I’s top four before the quarterfinals. The better seed (the later a team starts, the better) is at home until the semifinals, which with the final are at a neutral ground; extra time, then penalties.',
        'If your team is in it, you play its games as any other; the rest are quick results. Continue stops after the final.',
      ],
    ],
  },
  {
    id: 'recruiting',
    title: 'Recruiting high-school players',
    summary: 'The national class, your targets, scholarship offers, commitments and signing day.',
    blocks: [
      'Every season a national class of about 2,200 high-school seniors is ranked: stars (five-star for the top 25, then four, three and two), a national rank, and ranks by position and by home state (some come from abroad). Recruiting (in the menu, in the bar on a phone) is where you bring the best of them to your program. They join as freshmen at next season’s start.',
      [
        'Your chances: each recruit shows how he sees a program of your prestige: Good fit, Reach, Long shot or Out of reach. Prestige weighs most in his choice, so a tier-3 program will rarely land a top-100 recruit, however good its offer; aim at the good fits and reaches (the Realistic for you filter), and win to raise your prestige. His card shows the prestige he hopes for beside yours.',
        'Board: the class by national rank, with filters for position, home state, stars, the uncommitted and the recruits realistic for you. Overall and potential are your staff’s estimates, as ranges: they narrow as your staff get to know a recruit. Where shows who he committed to, or who he leans towards once your staff know him (the press follows the top 100).',
        'Targets: open a recruit and give him a priority, Top, High or Watch. Your staff spread their week of effort over your targets (a Top target gets three times a watched one’s share, up to a limit), so a long list means less for each. Effort builds his interest in you, faster with your offer out, and your staff’s knowledge of him. Interest fades when you stop recruiting him. Keen Top targets with your offer visit your campus (a big boost; 12 visits a season).',
        'Offers: from 1 August, offer a full scholarship, a percentage in 5% steps, or a walk-on place. Your money is counted in full scholarships (a tier-1 program has 18, a tier-5 program about 6): what next season’s returning players don’t hold is yours for recruits. Next season’s roster has at most 28 players. You may have offers out worth more than you have (up to one and a half times your money and places), but a recruit can only commit while you still have the money and a place: if not, he goes to his next choice and the news tells you.',
        'How recruits decide: each weighs the scholarship against what he hopes for, your program’s prestige against his level (a five-star wants a power; a two-star is glad of any offer), his playing time at his position next season, the distance from home, and the attention he got. His card says what he cares about most. The best recruits take longest to decide, and a recruit whose offers are below his hopes waits for better.',
        'Commitments and signing day: recruits commit through the autumn. A committed recruit can still flip to a much better offer until signing day (early February), when every commitment becomes a signing. Those still open sign as they decide until the class closes on 1 May; the rest go to other levels of college soccer.',
        'Recruiting assistant (the switch at the top of Recruiting, or Settings → Recruiting): every Monday from the day offers open until signing day, and as soon as you switch it on, it compares next season’s squad (the players staying, leaving out seniors, those who declared and those likely to declare early, plus your committed class) with a balanced roster: 3 keepers, 4 centre-backs, 4 full-backs, 2 defensive, 4 central and 2 attacking midfielders, 4 wingers and 4 strikers. Where a position is short it makes the best realistic recruits there (Good fit or Reach, by your staff’s estimate of their potential) Top targets and offers each the scholarship he hopes for, about one and a half offers a place since some will say no, the biggest gaps first. Where a position is covered it withdraws its own offers still open there. It stops when your money or places run out (the switch says what’s still needed and warns when your roster is too full), and never changes the targets and offers you made yourself.',
        'Game-day visits: on a recruit’s card, invite him to one of your home games before signing day for his official visit (one of your 12; up to 3 recruits a game). When the game is played his interest in you rises with the result: a win most (a win by three or more even more), a draw as much as a usual visit, a defeat much less. The news tells you how it went. A recruit you’ve invited isn’t also given the automatic visit.',
        'Pulling an offer: Pull offer withdraws it. Pulling the scholarship of a recruit who committed to you frees his place and money, but your other targets trust you a little less.',
        'Class: your commitments and signings. Rankings: every program’s class by points (more for more stars).',
        'The AI programs recruit the same way, so the powers land most of the five-stars, and a program that wins climbs in prestige and recruits better. If your roster is still short at the season’s start, walk-ons fill it to 22.',
      ],
    ],
  },
  {
    id: 'clubs',
    title: 'Other clubs and club history',
    summary: 'Club search, club pages and your club’s history.',
    blocks: [
      [
        'Search for any club by name with the box in the header (on a narrow screen, at the top of the menu). Accents don’t matter.',
        'A club page shows its league position, squad, average age and rating, manager, reputation, wage bill, budget and balance (estimates for other clubs), and its squad table. Click a player there for his page. Hall of fame in the menu lists everyone who has played for you in the career, with his record for your club (years, appearances, goals, assists, average rating), the titles won while he was there and where he is now; the greats (40 appearances, and a 7.0 average rating, 20 goals, 20 assists or a national title, the All-Division Tournament included) get a card. Star (☆) anyone on the list to make him a favourite: your favourites get their own cards at the top, and the ★ filter shows only them. Club & history in the menu is your own club’s page, with its history: how each past season ended. The history lists the trophies won, European ones in their competition’s colour (Champions League blue, Europa League orange, Conference League green), and each season’s European run; winning the league, the main domestic cup and the Champions League in one season is a Treble, shown with a gold banner.',
      ],
    ],
  },
  {
    id: 'offers',
    title: 'Transfer offers while simming: asking prices',
    summary: 'Stop for bids, let them wait, or have them answered by your asking prices.',
    blocks: [
      'Settings → Transfer offers chooses what a club’s bid (or loan request) for one of your players does while the game moves on:',
      [
        'Stop the game (the default): Continue and Sim to stop on the day it arrives, so you can answer it under Transfers.',
        'Let them wait: the game carries on; bids wait under Transfers, in Offers for your players, until they expire after a few days.',
        'Answer for me: each bid is answered as it arrives. At or above the player’s asking price he’s sold; below it the club is asked for the price, and either pays it or walks away. A player with no asking price is sold at the share of his value you choose for everyone else (his value, 125%, 150%, twice or three times), or is not for sale. Loan requests are agreed to or turned down, as you choose. The news after a sim says what happened to each bid.',
        'Asking prices: set one on a player’s page, under Up for sale (in the money you play in, in millions); Clear removes it.',
      ],
    ],
  },
  {
    id: 'international',
    title: 'International football',
    summary: 'National teams, call-ups in the international windows, friendlies and the Elo ranking.',
    blocks: [
      'Every FIFA member has a national team (Russia is suspended). Its squad of 26 is picked from players of its nationality. Countries whose players mostly play at home, in leagues the game doesn’t have, are filled out with made-up home-based players at the country’s real strength; they can’t be signed.',
      [
        'International windows: September–October, November, March and June. The day before one starts, every national team calls up its squad, and those players are away from their clubs until it ends (most leagues pause; those that play on, like League One and Two, are without them). The news says which of your players are away.',
        'Friendlies: in each window every team plays nations of a similar strength. They count as caps and goals and move the ranking, but are quick results: no cards or injuries.',
        'The ranking (International in the menu) is World Football Elo: it starts from the real ratings of November 2026 and moves with every international result, more for an upset. Filter by confederation, or find a country by name. A player’s page shows his national team, caps and goals.',
        'The World Cup every four years from 2030 (International → World Cup, which shows the one being played or the next). 2030’s qualifiers: Spain, Portugal and Morocco host. Each confederation qualifies in its own format, lighter than the real one but with the same shares: CONMEBOL’s ten play a round robin from September 2027 (top six through, the seventh to the intercontinental play-off); CAF’s best 48 play eight groups (winners through, the best runners-up to a play-off); AFC’s best 18 play three groups and then two more rounds; CONCACAF’s best 24 play two group rounds; OFC’s best eight play groups and a final; UEFA’s 52 play twelve groups in 2029 (winners through, the eight best runners-up to two play-off paths in March 2030). The intercontinental play-off in March 2030 gives the last two places. Weaker teams’ early rounds are settled by the ranking.',
        'Later World Cups: each edition’s qualifiers start in September three years before it, in the same windows as 2030’s moved on four years, so the 2034 ones start after the 2030 final. Saudi Arabia hosts 2034, so Europe has 16 places through qualifying (four play-off paths of three for the 12 best runners-up), Africa 9 (nine groups) and Asia 7 (the fourth round’s two group winners meet over two legs; the loser goes to the intercontinental play-off). The hosts after 2034 aren’t chosen yet: 2038 repeats 2030’s, 2042 2034’s, and so on.',
        'Qualifiers are fully simulated: players come back to their clubs with the fatigue and injuries they picked up. Cards in internationals don’t count towards club bans.',
        'The FIFA Club World Cup (International → Club World Cup): every four years from June 2029, hosted by the USA. The draw in December the year before picks 32 clubs: Europe’s twelve are the Champions League winners and the best by UEFA’s club coefficient (at most two a country); the other continents’ come from their leagues in the game, ranked by squad strength and league titles, and from guest clubs for the regions the game has no league for (Africa, most of Asia, Oceania), whose squads are made up to their real strength and whose players also play for their countries. Eight groups of four, no two clubs of one continent in a group (Europe’s, two at most), at neutral venues; the top two go to the round of 16, then single matches to the final in mid-July. Prize money as FIFA paid in 2025.',
        'The World Cup finals (International → World Cup), 2030’s and every later one’s on the same days of its year: the 48 qualified teams are drawn on 5 April 2030 into 12 groups of four, the hosts heading groups A to C and playing their group games at home; no group has two teams of one continent (Europe’s, two at most). The top two of each group and the eight best thirds play a round of 32 (no rematch of a group game), then single matches with extra time and penalties to the final on 19 July, with a match for third place. Squads are called up the day before the first match on 13 June; their players are away from their clubs until the final.',
        'Trophy cabinets: the World Cup’s winners have it in their national team’s History (the team’s page), and the Club World Cup’s winners in their club’s, with the year, above the European, league and cup trophies.',
        'History: under the World Cup and Club World Cup tabs, Past World Cups and Past Club World Cups list every final played in your career, latest first: the champions, the runners-up, the score (it opens the match), the hosts and, for the World Cup, third place. View shows that edition: its groups and every knockout round.',
        'Managing a country (International → My country): take any national team’s job alongside your club, and leave it when you like. Pick its squad of up to 26 from the players eligible for it (those of its nationality, and its home-based players); it stays as you pick it, and if it’s empty at a call-up it is picked for you. Set its tactics on the Tactics page (switch between your club and your country at the top). Its matches are yours: Continue stops for them as for your club’s, and you watch them or take an Instant result. When its match is the next one, Home shows the country instead of your club: its world rank, Elo, call-ups and injuries, where it stands for the next World Cup, its recent results and coming matches. A career can also be a country’s alone: on the start page pick Manage a country and a national team (the strongest are buttons, any other is in the Country box). With no club there is no squad, transfers, finances, board, league or cups in the menu: Home shows your country’s world rank and call-ups, Country (International → My country) its squad, and Tactics its tactic. Continue and Sim to move on from one international window to the next and stop at your matches; you can take another country’s job but not leave your only one.',
      ],
    ],
  },
  {
    id: 'simulation',
    title: 'Simulation settings: faster sims',
    summary: 'Choosing which leagues are fully simulated and which get fast results.',
    blocks: [
      'Settings in the menu (under More on a phone), or Options when starting a career, chooses which leagues are fully simulated. A fully simulated league plays every match minute by minute, with cards, injuries, bans and fitness. The others get a fast result: the score comes from the two teams’ strengths in one go, with the scorers, assists, substitutes, minutes and ratings handed out, so tables, top scorers, player pages and development all carry on. Fast results have no cards, injuries or match statistics.',
      [
        'Presets: Everything (the default), Big five + my country (the top flights of England, Spain, Italy, Germany and France, and every league in your country), My country, and My league only. Or tick leagues by continent and country; the College season (NCAA) is there too.',
        'Your own league is always fully simulated, even if you switch to a club in a league you made fast.',
        'Clubs from fast leagues are still fully simulated in the Champions League, Europa League and Conference League, and in a cup tie against a club from a fully simulated league. Cup ties between two fast-league clubs get fast results.',
        'Transfers are unchanged: clubs in fast leagues still buy and sell as before.',
        'Changes apply from the next day played; matches already played keep their results. A fast result’s match page shows the score, scorers and line-ups.',
      ],
    ],
  },
  {
    id: 'seasons',
    title: 'Seasons, development and retirements',
    summary: 'How the season ends, how players change, the season summary.',
    blocks: [
      [
        'The season rolls over on 1 July. When the season’s last match has been played, Continue stops with the season summary: your finish and cup runs, then by country the champions, the promoted and the relegated, how your squad developed, retirements, the new youth intake and other news. Promotion, relegation and the new fixtures follow.',
        'Players develop month by month. Young players grow towards their ceiling, hold it through their late twenties and decline from their early thirties, physical attributes first. Playing time helps: players who play develop best, and unused substitutes still gain some. Young players from a club’s own academy who play regularly can also raise their potential.',
        'Players retire, mostly from their mid-thirties, and every club takes in a few youngsters from its academy each season.',
        'A club’s reputation moves with its squad: buying better players lifts it over a few seasons, and selling its best lowers it. Titles and cups add a little.',
      ],
    ],
  },
  {
    id: 'phone',
    title: 'Playing on a phone',
    summary: 'The phone layout, tapping instead of dragging, and Add to Home Screen.',
    blocks: [
      [
        'On a phone, a bar at the bottom has Home, Squad, Tactics and Transfers (Recruiting for a college coach); More opens the rest (League, Fixtures, Calendar, Cups, Europe, MLS roster for an MLS club, College, Finances, your club, Save / Load) with the club search and the version. The header has your club’s name and the date, one main button (Continue, or Match day), and a ⋯ menu with Save and Sim to…. The bar steps aside while you watch a match.',
        'Tables keep their key columns and put the rest in a small line under the name. The Transfers filters are behind a Filters button.',
        'There is no dragging on a touch screen. On Tactics and in the live match, tap a player and then tap where he should go.',
        'The live match draws the pitch upright. Half-time is a full-screen sheet; Tactics and substitutions puts it aside so you can make changes, with a bar at the bottom to bring it back or start the second half.',
        'Add to Home Screen: on an iPhone, open the game in Safari, tap Share, then Add to Home Screen. On Android, use the browser menu’s Add to Home screen (or Install app). The game then opens full screen like an app.',
      ],
    ],
  },
  {
    id: 'accounts',
    title: 'Accounts',
    summary: 'Signing in and out when the server has accounts.',
    blocks: [
      'If the server you play on has accounts, the game opens on a sign-in screen. Everyone who signs in has their own three save slots and never sees anyone else’s careers. Ask whoever runs the server to make you an account. Your browser stays signed in for 30 days from the last time you played (the server can change that).',
      'Signed in as… and Sign out are at the foot of the menu and on the start page. If your sign-in expires, you are taken back to the sign-in screen.',
      'On a server without accounts, such as the game on your own computer, there is nothing to sign in to and the game opens straight away.',
    ],
  },
  {
    id: 'version',
    title: 'The version, and reporting a problem',
    summary: 'What the version number means, the orange warning and Copy version.',
    blocks: [
      [
        'The version tag shows the game’s version (for example v1.12) and the date of its last update. The number goes up by one with every update. A + after it means files were edited by hand on that machine.',
        'Orange text such as “server v1.12 · page v1.10” means the page and the server are on different versions. Reload the page.',
        'To report a problem, press Copy version at the top of this window and paste the line into your message. It names the version, the commit and when the page was built.',
      ],
    ],
  },
]

/** The topics that match a search: every word must appear in the title, the summary or the text. */
export function matchingTopics(topics: HelpTopic[], query: string): HelpTopic[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return topics
  return topics.filter((topic) => {
    const text = [topic.title, topic.summary, ...topic.blocks.flat()].join(' ').toLowerCase()
    return words.every((word) => text.includes(word))
  })
}
