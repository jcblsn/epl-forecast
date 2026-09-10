const state = { index: null, document: null, ledger: null, view: "table", team: null };
const panel = document.getElementById("panel");
const VIEWS = [
  ["table", "Table"],
  ["positions", "Positions"],
  ["teams", "Distributions"],
  ["fixtures", "Fixtures"],
  ["impact", "Impact"],
  ["ledger", "Ledger"],
];
const EVENT_ORDER = [
  "title_probability",
  "top_four_probability",
  "top_five_probability",
  "automatic_promotion_probability",
  "playoff_qualification_probability",
  "playoff_promotion_probability",
  "promotion_probability",
  "relegation_probability",
];

const pct = (p) => (p === null || p === undefined ? "" : (100 * p).toFixed(1));
const label = (key) => key.replace(/_probability$/, "").replace(/_/g, " ");
const shade = (p, peak) => `rgba(68, 119, 204, ${Math.min(1, Math.sqrt(p / peak)).toFixed(3)})`;
const when = (value) => (value ? new Date(value).toISOString().slice(0, 16).replace("T", " ") : "");

function element(tag, properties = {}, children = []) {
  const { dataset, ...rest } = properties;
  const node = Object.assign(document.createElement(tag), rest);
  Object.assign(node.dataset, dataset ?? {});
  for (const child of [].concat(children)) {
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function table(headers, rows) {
  const head = element("tr", {}, headers.map((h) => element("th", { textContent: h })));
  const body = element("tbody", {}, rows);
  const node = element("table", {}, [element("thead", {}, [head]), body]);
  head.querySelectorAll("th").forEach((th, column) => {
    th.onclick = () => {
      const ascending = th.dataset.order !== "asc";
      head.querySelectorAll("th").forEach((other) => delete other.dataset.order);
      th.dataset.order = ascending ? "asc" : "desc";
      const value = (row) => {
        const text = row.children[column].dataset.sort ?? row.children[column].textContent;
        const number = parseFloat(text);
        return Number.isNaN(number) ? text : number;
      };
      [...body.children]
        .sort((a, b) => (value(a) > value(b) ? 1 : value(a) < value(b) ? -1 : 0) * (ascending ? 1 : -1))
        .forEach((row) => body.append(row));
    };
  });
  return node;
}

function cell(text, properties = {}) {
  return element("td", { textContent: text, ...properties });
}

async function load(href) {
  const response = await fetch(href, { cache: "no-store" });
  if (!response.ok) throw new Error(`${href}: ${response.status}`);
  return response.json();
}

function competitionsOf(snapshot) {
  return state.index.snapshots.find((row) => row.snapshot_id === snapshot)?.competitions ?? [];
}

async function refresh() {
  const snapshot = document.getElementById("snapshot").value;
  const competition = document.getElementById("competition").value;
  const entry =
    competitionsOf(snapshot).find((row) => row.competition_id === competition) ??
    competitionsOf(snapshot)[0];
  if (!entry) return;
  state.document = await load(`data/${entry.href}`);
  document.getElementById("meta").textContent =
    `${state.document.model.model_id} · cutoff ${state.document.model_results_cutoff} · ` +
    `${state.document.simulations.toLocaleString()} paths · generated ${when(state.document.generated_at)}`;
  render();
}

function render() {
  document.querySelectorAll("#views button").forEach((button) => {
    button.setAttribute("aria-current", String(button.dataset.view === state.view));
  });
  panel.replaceChildren();
  const views = { table: tableView, positions: positionsView, teams: teamsView, fixtures: fixturesView, impact: impactView, ledger: ledgerView };
  views[state.view]();
}

function tableView() {
  const teams = state.document.teams;
  const events = EVENT_ORDER.filter((key) => key in teams[0].events);
  const headers = ["#", "Team", "P", "Pts", "E[pts]", "80% pts", "E[rank]", "80% rank", ...events.map(label)];
  const rows = teams.map((team, position) =>
    element("tr", {}, [
      cell(position + 1),
      element("td", { className: "name" }, [
        element("a", { href: "#", textContent: team.name, onclick: (e) => { e.preventDefault(); state.team = team.team_id; state.view = "teams"; render(); } }),
      ]),
      cell(team.played),
      cell(team.current_points),
      cell(team.mean_points.toFixed(1)),
      cell(team.points_intervals["80"].join("–"), { dataset: { sort: team.points_intervals["80"][0] } }),
      cell(team.mean_position.toFixed(2)),
      cell(team.position_intervals["80"].join("–"), { dataset: { sort: team.position_intervals["80"][0] } }),
      ...events.map((key) => cell(pct(team.events[key]))),
    ])
  );
  panel.append(table(headers, rows));
}

function positionsView() {
  const teams = state.document.teams;
  const places = teams[0].position_probabilities.length;
  const peak = Math.max(...teams.flatMap((team) => team.position_probabilities));
  const headers = ["Team", ...Array.from({ length: places }, (_, i) => String(i + 1))];
  const rows = teams.map((team) =>
    element("tr", {}, [
      element("td", { className: "name", textContent: team.name }),
      ...team.position_probabilities.map((p) =>
        cell(p >= 0.005 ? pct(p) : "", { className: "cell", style: `background:${shade(p, peak)}` })
      ),
    ])
  );
  panel.append(table(headers, rows));
}

function distribution(values, formatter) {
  const peak = Math.max(...values.map(([, p]) => p));
  return element(
    "table",
    {},
    values.map(([key, p]) =>
      element("tr", {}, [
        cell(formatter(key)),
        cell(pct(p)),
        element("td", { className: "name" }, [
          element("span", { className: "bar", style: `width:${Math.round((140 * p) / peak)}px` }),
        ]),
      ])
    )
  );
}

function teamsView() {
  const teams = state.document.teams;
  const chosen = teams.find((team) => team.team_id === state.team) ?? teams[0];
  const chooser = element(
    "select",
    { onchange: (event) => { state.team = event.target.value; render(); } },
    teams.map((team) => element("option", { value: team.team_id, textContent: team.name, selected: team.team_id === chosen.team_id }))
  );
  const points = Object.entries(chosen.points_distribution).map(([k, p]) => [Number(k), p]);
  const positions = chosen.position_probabilities.map((p, i) => [i + 1, p]).filter(([, p]) => p > 0);
  panel.append(
    chooser,
    element("div", { className: "grid" }, [
      element("div", { className: "card" }, [
        element("h2", { textContent: `Final points — mean ${chosen.mean_points.toFixed(1)}, 90% ${chosen.points_intervals["90"].join("–")}` }),
        distribution(points, String),
      ]),
      element("div", { className: "card" }, [
        element("h2", { textContent: `Finishing position — mean ${chosen.mean_position.toFixed(2)}, 90% ${chosen.position_intervals["90"].join("–")}` }),
        distribution(positions, String),
      ]),
      element("div", { className: "card" }, [
        element("h2", { textContent: "Event probabilities" }),
        table(["Event", "%"], Object.entries(chosen.events).map(([key, p]) => element("tr", {}, [element("td", { className: "name", textContent: label(key) }), cell(pct(p))]))),
      ]),
    ])
  );
}

function fixturesView() {
  const names = Object.fromEntries(state.document.teams.map((team) => [team.team_id, team.name]));
  const rows = state.document.matches.map((match) =>
    element("tr", {}, [
      cell(when(match.kickoff_time)),
      element("td", { className: "name", textContent: names[match.home_team_id] ?? match.home_team_id }),
      element("td", { className: "name", textContent: names[match.away_team_id] ?? match.away_team_id }),
      cell(pct(match.p_home)),
      cell(pct(match.p_draw)),
      cell(pct(match.p_away)),
      cell(match.score_probabilities ? topScores(match.score_probabilities) : "", { className: "muted" }),
    ])
  );
  panel.append(table(["Kickoff (UTC)", "Home", "Away", "H", "D", "A", "Likeliest scores"], rows));
}

function topScores(scores) {
  const cells = [];
  scores.grid_home_rows_away_columns.forEach((row, home) =>
    row.forEach((p, away) => cells.push([`${home}-${away}`, p]))
  );
  return cells
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([score, p]) => `${score} ${pct(p)}%`)
    .join("  ");
}

function impactView() {
  const impact = state.document.impact;
  if (!impact || !impact.fixtures.length) {
    panel.append(element("p", { className: "muted", textContent: "No fixtures inside the impact horizon." }));
    return;
  }
  const names = Object.fromEntries(state.document.teams.map((team) => [team.team_id, team.name]));
  const name = (id) => names[id] ?? id;
  panel.append(
    element("p", { className: "muted", textContent: `${impact.basis} Next ${impact.horizon_days} days, from ${state.document.simulations.toLocaleString()} season paths; smallest outcome sample ${impact.smallest_outcome_count}.` })
  );
  for (const fixture of impact.fixtures) {
    const counts = fixture.outcome_counts;
    const total = counts.home + counts.draw + counts.away;
    const rows = fixture.impacts.map((row) => {
      const home = row.team_id === fixture.home_team_id;
      const win = home ? row.conditional.home : row.conditional.away;
      const loss = home ? row.conditional.away : row.conditional.home;
      return element("tr", {}, [
        element("td", { className: "name", textContent: name(row.team_id) }),
        element("td", { className: "name", textContent: label(row.event) }),
        cell(pct(row.baseline)),
        cell(pct(win)),
        cell(pct(row.conditional.draw)),
        cell(pct(loss)),
        cell(pct(row.rms_movement)),
        cell(pct(row.swing)),
        cell(row.sufficient_sample ? "" : "thin", { className: "muted" }),
      ]);
    });
    panel.append(
      element("h2", { textContent: `${name(fixture.home_team_id)} v ${name(fixture.away_team_id)} — ${when(fixture.kickoff_time) || fixture.match_date}` }),
      element("p", { className: "muted", textContent: `Paths: home ${pct(counts.home / total)}%, draw ${pct(counts.draw / total)}%, away ${pct(counts.away / total)}%` }),
      table(["Team", "Event", "Now", "If win", "If draw", "If loss", "RMS", "Swing", ""], rows)
    );
  }
}

function ledgerView() {
  if (!state.ledger) {
    panel.append(element("p", { className: "muted", textContent: "No ledger published yet." }));
    return;
  }
  const summary = state.ledger.summary;
  panel.append(
    element("h2", { textContent: `Settled H/D/A forecasts — ${state.ledger.settled.length} scored, ${state.ledger.unsettled} awaiting results` }),
    table(
      ["Scope", "Matches", "Log loss", "Brier", "Classwise ECE"],
      Object.entries(summary).map(([scope, row]) =>
        element("tr", {}, [
          element("td", { className: "name", textContent: scope }),
          cell(row.scored),
          cell(row.log_loss.toFixed(5)),
          cell(row.brier.toFixed(5)),
          cell(row.classwise_ece.toFixed(5)),
        ])
      )
    ),
    element("h2", { textContent: "Scored matches" }),
    table(
      ["Kickoff (UTC)", "Match", "Outcome", "H", "D", "A", "Snapshot"],
      [...state.ledger.settled].reverse().map((row) =>
        element("tr", {}, [
          cell(when(row.kickoff_time)),
          element("td", { className: "name", textContent: row.match_id.split(":").slice(2).join(" v ") }),
          cell(row.outcome),
          cell(pct(row.p_home)),
          cell(pct(row.p_draw)),
          cell(pct(row.p_away)),
          cell(row.snapshot_id),
        ])
      )
    )
  );
}

async function start() {
  try {
    state.index = await load("data/index.json");
  } catch (error) {
    panel.append(element("p", { className: "error", textContent: `No published forecasts found (${error.message}). Run: uv run epl-forecast operate` }));
    return;
  }
  state.ledger = await load("data/ledger.json").catch(() => null);
  const snapshots = document.getElementById("snapshot");
  snapshots.append(...state.index.snapshots.map((row) => element("option", { value: row.snapshot_id, textContent: row.snapshot_id })));
  const competitions = document.getElementById("competition");
  competitions.append(
    ...competitionsOf(state.index.latest).map((row) => element("option", { value: row.competition_id, textContent: row.competition_name }))
  );
  document.getElementById("views").append(
    ...VIEWS.map(([view, text]) =>
      element("button", { textContent: text, dataset: { view }, onclick: () => { state.view = view; render(); } })
    )
  );
  snapshots.onchange = refresh;
  competitions.onchange = refresh;
  await refresh();
}

start();
