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
      'The start page appears when no career is loaded, and from Save / Load in the menu. Under New career, type a manager name, pick a save slot (1 to 3), choose a country and a league, then click a club. Each club card shows the squad’s average rating and the club’s reputation, so you can see how big a job it is. Press Start career.',
      [
        'Leagues: 19 leagues in 11 countries. England has four divisions; Spain, Italy, Germany and France have their lower divisions too; Portugal, the Netherlands, Scotland, Saudi Arabia, Turkey and Belgium have their top flight. England, Spain, Italy, Germany and France are listed first.',
        'Save slot: starting a new career in a slot that already has one replaces it. A yellow warning tells you.',
        'Sandbox budget (optional): type an amount, in millions of the money shown, and your club starts with that to spend on transfer fees and wages (up to about €10 billion). Leave it empty to play on the board’s budget. A sandbox starts with the board off, unless you switch it on.',
        'Board expectations: on, the board expects a league finish, its confidence in you moves with results, and your budget each season comes from the club’s income and cash. Off, there are no targets and all your cash is your budget. You can change it later on the Finances page.',
        'Currency: pick dollars, euros or pounds next to the budget. It only changes how money is shown (prices are quoted as round figures in it), and you can change it later on the Finances page.',
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
        'A change that is waiting to be made (until the next stoppage while the match runs, or until play resumes if you are paused or at a break) shows at the top of the Subs tab with an Undo button and a choice of role for the newcomer. Changes made together count as one stoppage.',
        'After a red card, move a player into the empty position (drag him onto it, or pick him and then the position) so the team can reshape. Cards show beside the players.',
        'Half-time shows the stats, who is most tired and who is rated best. Make changes in the Tactics and Subs tabs, then start the second half. Cup ties can go to extra time and penalties.',
        'At full time, Match report shows the stats, the events and every player’s rating.',
      ],
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
        'Calendar shows a month at a time (Monday first), with arrows and a Today button. Each of your matches shows home or away, the opponent, the competition (a coloured stripe) and then the result; click a played match for its report.',
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
        'League shows a table for any league in the game: pick a country, then a league. Zones are coloured for promotion, play-offs and relegation, and your club is in bold. A season picker shows past seasons.',
        'Between seasons the League page keeps showing last season’s final table until the new season’s first league match.',
        'Cups shows a country’s cups (yours to begin with), every round with its ties and results, what is still to come, and how your club is doing. Pick another country or cup, or a past season.',
      ],
    ],
  },
  {
    id: 'europe',
    title: 'European competitions',
    summary: 'The Champions League, Europa League and Conference League: who qualifies, the league phase, the knockouts and the prize money.',
    blocks: [
      'Europe in the menu (it only appears in a game that has the European competitions) shows the Champions League, the Europa League and the Conference League. It opens on the one your club is in this season, and has a season picker for past ones.',
      [
        'Qualifying: places go by league finish, to domestic cup winners (a Europa League place) and to the holders. A club is in the highest competition it earns, and its lower place passes to the next club. Countries without a league in the game send clubs by reputation. A short summer play-off round (two legs, in August) fills the last places: the winners go into the league phase, and the losers drop down a competition, from the Champions League to the Europa League and from the Europa League to the Conference League. The Conference League’s losers are out.',
        'League phase: 36 clubs in one table. In the Champions League and Europa League each club plays 8 matches, against two clubs from each of four pots (one at home, one away); in the Conference League each plays 6, against one club from each of six pots. Pots follow the clubs’ European record over five seasons (the Champions League holders are always in pot 1), and nobody plays a club from their own country. The matchday picker shows each matchday’s fixtures and scores; click a played match for its report.',
        'After the league phase: the top 8 go straight to the round of 16, and 9th to 24th meet in a two-legged knockout play-off for the other eight places. The rest are out. The round of 16, quarter-finals and semi-finals are two legs, and the final is a single match at a neutral ground. There is no away-goals rule: extra time and penalties decide a tie that is still level.',
        'Prize money: a starting fee, a payment for each league-phase win and draw, a payment for each knockout round a club reaches, and a bonus for the winners. The Champions League pays most. It is a bonus on top of a club’s normal income.',
        'Next season: the Champions League and Europa League winners go into the Champions League league phase, and the Conference League winner into the Europa League’s. Their own league places pass to the next clubs.',
        'The page also lists the summer play-off round and everyone who entered, with how they qualified, grouped by pot once the draw is made.',
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
        'A club page shows its league position, squad, average age and rating, manager, reputation, wage bill, budget and balance (estimates for other clubs), and its squad table. Click a player there for his page. Club & history in the menu is your own club’s page, with its history: how each past season ended.',
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
        'On a phone the menu folds away behind the menu button. The header has your club’s name with the version under it, one main button (Continue, or Match day), and a ⋯ menu with Save and Sim to….',
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
