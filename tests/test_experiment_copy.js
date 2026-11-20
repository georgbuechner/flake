const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const key = "flake.experiment-copy";
const copied = {source_id: "source", categories: ["medication"], user_id: "tester@example.org"};
const dates = (animal_id, start = "2025-02-01", sacrifice_date = "2025-12-31") =>
  ({animal_id, start, sacrifice_date, dob: "2024-01-01"});

class Node {
  constructor() {
    this.dataset = {};
    this.listeners = {};
    this.children = [];
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.open = false;
    const classes = new Set();
    this.classList = {toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
      contains: name => classes.has(name)};
  }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  setAttribute(name, value) { this[name] = value; }
  getAttribute(name) { return this[name]; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  querySelectorAll() { return []; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  checkValidity() {
    if (this.disabled) return true;
    if (!this.value) return !this.required;
    return /^\d{4}-\d{2}-\d{2}$/.test(this.value) &&
      (!this.min || this.value >= this.min) && (!this.max || this.value <= this.max);
  }
  set innerHTML(value) { throw new Error("Messages must stay plain text"); }
}

function setup(initialClipboard = copied, targets = [dates("B")]) {
  const ids = ["experiment-copy-tools", "experiment-copy-status", "experiment-copy-selected",
    "experiment-copy-mode", "experiment-paste-mode", "open-experiment-copy", "experiment-copy-dialog",
    "experiment-copy-source", "experiment-copy-dates", "experiment-copy-form", "open-experiment-paste",
    "clear-experiment-copy", "experiment-paste-dialog", "experiment-paste-summary", "experiment-paste-targets",
    "experiment-paste-ready", "experiment-paste-form", "confirm-experiment-paste", "overview_table",
    ...["procedures", "medication", "viruses"].map(category => `experiment-copy-count-${category}`)];
  const elements = new Map(ids.map(id => [id, new Node()]));
  const storage = new Map(initialClipboard ? [[key, JSON.stringify(initialClipboard)]] : []);
  const categories = ["procedures", "medication", "viruses"].map(value => Object.assign(new Node(), {value}));
  const events = {errors: [], requests: [], alerts: [], reloads: 0, dateMode: "shift", targets,
    source: dates("source", "2025-01-01"), counts: {procedures: 2, medication: 2, viruses: 1}};
  let selected = [];
  const select = ids => { selected = ids.map(animal_id => Object.assign(new Node(), {animal_id, checked: true})); };
  select(targets.map(target => target.animal_id));
  const element = id => elements.get(id) || null;
  element("experiment-copy-tools").dataset = {userId: "tester@example.org"};
  const documentEvents = {};
  const context = {
    document: {
      addEventListener(name, callback) { documentEvents[name] = callback; },
      getElementById: element,
      createElement: () => new Node(),
      querySelectorAll(selector) {
        if (selector === '[name="mark_animal"]:checked') return selected.filter(input => input.checked);
        if (selector === '[name="copy_category"]') return categories;
        if (selector === '[name="copy_category"]:checked') return categories.filter(input => input.checked);
        throw new Error(`Unexpected selector: ${selector}`);
      },
      querySelector(selector) {
        if (selector === '[name="copy_date_mode"]:checked') return {value: events.dateMode};
        if (selector === '#overview-table th input[type="checkbox"]') return null;
        throw new Error(`Unexpected selector: ${selector}`);
      },
    },
    sessionStorage: {getItem: name => storage.get(name) || null,
      setItem: (name, value) => storage.set(name, value), removeItem: name => storage.delete(name)},
    MutationObserver: class {constructor(callback) { events.tableChanged = callback; } observe() {}},
    window: {location: {reload() { events.reloads++; }}},
    OpenErrorModal: (...args) => events.errors.push(args), alert: message => events.alerts.push(message),
    console: {error() {}},
    AppFetch: async (url, options) => {
      events.requests.push({url, ...options});
      const body = JSON.parse(options.body);
      return {ok: true, json: async () => url.endsWith("/preview")
        ? {source: {...events.source, animal_id: body.source_id}, counts: events.counts,
          targets: events.targets.filter(target => body.target_ids.includes(target.animal_id))}
        : {target_ids: body.target_ids.filter(id => !body.skip_ids.includes(id)), copied_rows: 2, skipped_ids: body.skip_ids}};
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/static/js/experiment_copy.js"), "utf8"), context);
  documentEvents.DOMContentLoaded();
  const submit = id => element(id).listeners.submit({preventDefault() {}});
  const mode = value => {
    element("experiment-copy-mode").checked = value === "copy";
    element("experiment-paste-mode").checked = value === "paste";
    documentEvents.change();
  };
  const descendants = root => root.children.flatMap(child => [child, ...descendants(child)]);
  const row = id => element("experiment-paste-targets").children.find(child => child.dataset.animalId === id);
  const input = (id, field) => descendants(row(id)).find(child => child.dataset.dateField === field);
  const skip = id => descendants(row(id)).find(child => Object.hasOwn(child.dataset, "skipAnimal"));
  const sourceButton = (id, field) => row(id).children[field === "start" ? 1 : 2].children[1];
  const review = () => element("experiment-paste-targets").listeners.input();
  return {context, events, element, storage, documentEvents, submit, mode, select, categories, row, input, skip, sourceButton, review};
}

async function main() {
  for (const chosen of [["procedures"], ["viruses"], ["medication"], ["procedures", "medication", "viruses"]]) {
    const state = setup(null);
    assert.equal(state.element("experiment-copy-mode").checked, true);
    state.select(["source"]);
    state.documentEvents.change();
    await state.element("open-experiment-copy").listeners.click();
    assert.equal(state.element("experiment-copy-dialog").open, true);
    assert.equal(state.element("experiment-copy-source").textContent, "source");
    for (const category of state.categories) category.checked = chosen.includes(category.value);
    state.submit("experiment-copy-form");
    assert.deepEqual(JSON.parse(state.storage.get(key)), {...copied, categories: chosen});
    assert.equal(state.element("experiment-copy-dialog").open, false);
    assert.equal(state.element("experiment-paste-mode").checked, true);
    assert.equal(state.element("open-experiment-paste").disabled, true);
    state.mode("copy");
    assert.equal(state.element("open-experiment-copy").hidden, false);
    assert.ok(state.storage.has(key));
  }
  {
    const state = setup(null);
    state.select(["source"]);
    state.events.counts.viruses = 0;
    await state.element("open-experiment-copy").listeners.click();
    assert.equal(state.categories.find(input => input.value === "viruses").disabled, true);
    state.categories.forEach(input => { input.checked = false; });
    state.submit("experiment-copy-form");
    assert.equal(state.storage.size, 0);
    assert.equal(state.events.errors.length, 1);
  }
  for (const invalid of [null, {...copied, categories: []}, {...copied, categories: ["general"]},
    {...copied, user_id: "other@example.org"}]) {
    const state = setup(invalid);
    assert.equal(state.element("open-experiment-paste").disabled, true);
  }
  {
    const state = setup();
    state.select(["B", "C", "B"]);
    state.documentEvents.change();
    assert.equal(state.element("experiment-copy-selected").textContent, "2 destination animals selected.");
    state.mode("copy");
    assert.equal(state.element("open-experiment-copy").disabled, true);
    state.mode("paste");
    state.select([]);
    state.events.tableChanged();
    assert.equal(state.element("open-experiment-paste").disabled, true);
    state.select(["source"]);
    await state.element("open-experiment-paste").listeners.click();
    assert.equal(state.events.errors.length, 1);
    assert.equal(state.events.requests.length, 0);
  }
  for (const dateMode of ["keep", "shift"]) {
    const state = setup();
    state.events.dateMode = dateMode;
    await state.element("open-experiment-paste").listeners.click();
    assert.equal(state.row("B").classList.contains("copy-date-row--ready"), true);
    await state.submit("experiment-paste-form");
    assert.deepEqual(JSON.parse(state.events.requests[1].body), {
      source_id: "source", target_ids: ["B"], categories: ["medication"], date_mode: dateMode,
      target_dates: {}, skip_ids: [],
    });
    assert.equal(state.events.reloads, 1);
    assert.equal(state.element("confirm-experiment-paste").disabled, false);
  }
  {
    const state = setup(copied, [dates("B"), dates("C", ""), dates("D", "", ""), dates("E", "", "")]);
    await state.element("open-experiment-paste").listeners.click();
    assert.equal(state.element("confirm-experiment-paste").disabled, true);
    assert.equal(state.row("C").classList.contains("copy-date-row--missing"), true);
    state.sourceButton("C", "start").listeners.click();
    state.input("D", "start").value = "2025-03-01";
    state.input("D", "sacrifice_date").value = "2025-02-28";
    state.skip("E").checked = true;
    state.review();
    assert.equal(state.element("confirm-experiment-paste").disabled, true);
    state.input("D", "sacrifice_date").value = "2025-04-01";
    state.review();
    assert.equal(state.row("C").classList.contains("copy-date-row--ready"), true);
    assert.equal(state.row("E").classList.contains("copy-date-row--skipped"), true);
    assert.equal(state.input("E", "start").disabled, true);
    assert.equal(state.element("experiment-paste-ready").textContent, "3 ready, 0 need dates, 1 skipped.");
    await state.submit("experiment-paste-form");
    const body = JSON.parse(state.events.requests[1].body);
    assert.deepEqual(body.target_dates, {C: {start: "2025-01-01"}, D: {start: "2025-03-01", sacrifice_date: "2025-04-01"}});
    assert.deepEqual(body.skip_ids, ["E"]);
    assert.equal(state.events.reloads, 1);
  }
  {
    const state = setup(copied, [dates("B", "", "")]);
    state.events.source.sacrifice_date = "";
    await state.element("open-experiment-paste").listeners.click();
    assert.equal(state.sourceButton("B", "sacrifice_date").disabled, true);
    state.skip("B").checked = true;
    state.review();
    assert.equal(state.element("confirm-experiment-paste").disabled, true);
    await state.submit("experiment-paste-form");
    assert.equal(state.events.requests.length, 1);
  }
  for (const status of [400, 401, 403, 404, 500]) {
    const state = setup();
    await state.element("open-experiment-paste").listeners.click();
    state.context.AppFetch = async () => ({ok: false, status, text: async () => "Missing source start date"});
    await state.submit("experiment-paste-form");
    assert.deepEqual(state.events.errors, [["Missing source start date", status, "experiment-paste-dialog"]]);
    assert.equal(state.events.reloads, 0);
    assert.equal(state.element("confirm-experiment-paste").disabled, false);
    assert.ok(state.storage.has(key));
  }
  {
    const state = setup();
    state.context.AppFetch = async () => ({ok: false, status: 403, text: async () => "Not responsible"});
    await state.element("open-experiment-paste").listeners.click();
    assert.deepEqual(state.events.errors, [["Not responsible", 403]]);
    assert.equal(state.element("experiment-paste-dialog").open, false);
    assert.equal(state.element("open-experiment-paste").disabled, false);
  }
  {
    const state = setup();
    await state.element("open-experiment-paste").listeners.click();
    let finish;
    let submissions = 0;
    state.context.AppFetch = () => { submissions++; return new Promise(resolve => { finish = resolve; }); };
    const pending = state.submit("experiment-paste-form");
    assert.equal(state.element("confirm-experiment-paste").disabled, true);
    await state.submit("experiment-paste-form");
    state.element("clear-experiment-copy").listeners.click();
    assert.equal(submissions, 1);
    assert.ok(state.storage.has(key));
    finish({ok: false, status: 400, text: async () => "Dates missing"});
    await pending;
    state.element("clear-experiment-copy").listeners.click();
    assert.equal(state.storage.has(key), false);
    assert.equal(state.element("experiment-copy-mode").checked, true);
  }
  console.log("Overview copy/paste modes, source selection, date review/entry, skipping and request handling passed");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
