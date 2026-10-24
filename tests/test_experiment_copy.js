const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const key = "flake.experiment-copy";
const copied = {source_id: "source", categories: ["medication"], user_id: "tester@example.org"};

function setup(sourcePage = false, initialClipboard = copied) {
  const ids = ["experiment-copy-tools", "experiment-copy-status"];
  ids.push(...(sourcePage ? ["open-experiment-copy", "experiment-copy-dialog", "experiment-copy-form"]
    : ["open-experiment-paste", "experiment-copy-selected", "clear-experiment-copy", "experiment-paste-dialog",
      "experiment-paste-summary", "experiment-paste-targets", "experiment-paste-form", "confirm-experiment-paste", "overview_table"]));
  const elements = new Map(ids.map(id => {
    const node = {dataset: {}, listeners: {}, textContent: "", disabled: false, open: false,
      addEventListener(name, callback) { this.listeners[name] = callback; },
      showModal() { this.open = true; }, close() { this.open = false; }, querySelectorAll() { return []; }};
    Object.defineProperty(node, "innerHTML", {set() { throw new Error("Messages must stay plain text"); }});
    return [id, node];
  }));
  const storage = new Map(initialClipboard ? [[key, JSON.stringify(initialClipboard)]] : []);
  const events = {errors: [], requests: [], alerts: [], reloads: 0, selected: ["B"], categories: ["medication"], dateMode: "shift"};
  const element = id => elements.get(id) || null;
  element("experiment-copy-tools").dataset = {userId: "tester@example.org", ...(sourcePage ? {sourceId: "source"} : {})};
  const documentEvents = {};
  const context = {
    document: {
      addEventListener(name, callback) { documentEvents[name] = callback; },
      getElementById: element,
      querySelectorAll(selector) {
        if (selector === '[name="mark_animal"]:checked') return events.selected.map(id => ({getAttribute() { return id; }}));
        if (selector === '[name="copy_category"]:checked') return events.categories.map(value => ({value}));
        throw new Error(`Unexpected selector: ${selector}`);
      },
      querySelector() { return {value: events.dateMode}; },
    },
    sessionStorage: {getItem: name => storage.get(name) || null,
      setItem: (name, value) => storage.set(name, value), removeItem: name => storage.delete(name)},
    MutationObserver: class {constructor(callback) { events.tableChanged = callback; } observe() {}},
    window: {location: {reload() { events.reloads++; }}},
    OpenErrorModal: (...args) => events.errors.push(args), alert: message => events.alerts.push(message),
    console: {error() {}},
    AppFetch: async (url, options) => {
      events.requests.push({url, ...options});
      return {ok: true, json: async () => ({target_ids: ["B"], copied_rows: 2})};
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/static/js/experiment_copy.js"), "utf8"), context);
  documentEvents.DOMContentLoaded();
  const submit = id => element(id).listeners.submit({preventDefault() {}});
  return {context, events, element, storage, documentEvents, submit};
}

async function main() {
  for (const categories of [["procedures"], ["viruses"], ["medication"], ["procedures", "medication", "viruses"]]) {
    const state = setup(true, null);
    state.events.categories = categories;
    state.element("open-experiment-copy").listeners.click();
    assert.equal(state.element("experiment-copy-dialog").open, true);
    state.submit("experiment-copy-form");
    assert.deepEqual(JSON.parse(state.storage.get(key)), {...copied, categories});
    assert.equal(state.element("experiment-copy-dialog").open, false);
  }
  {
    const state = setup(true, null);
    state.events.categories = [];
    state.submit("experiment-copy-form");
    assert.equal(state.storage.size, 0);
    assert.equal(state.events.errors.length, 1);
  }
  for (const invalid of [null, {...copied, categories: []}, {...copied, categories: ["general"]},
    {...copied, user_id: "other@example.org"}]) {
    const state = setup(false, invalid);
    assert.equal(state.element("open-experiment-paste").disabled, true);
  }
  {
    const state = setup();
    state.events.selected = ["B", "C", "B"];
    state.documentEvents.change();
    assert.equal(state.element("experiment-copy-selected").textContent, "2 animals selected.");
    state.events.selected = [];
    state.events.tableChanged();
    assert.equal(state.element("open-experiment-paste").disabled, true);
    state.events.selected = ["source"];
    state.element("open-experiment-paste").listeners.click();
    assert.equal(state.events.errors.length, 1);
    assert.equal(state.events.requests.length, 0);
  }
  for (const dateMode of ["keep", "shift"]) {
    const state = setup();
    state.events.dateMode = dateMode;
    state.element("open-experiment-paste").listeners.click();
    await state.submit("experiment-paste-form");
    assert.deepEqual(JSON.parse(state.events.requests[0].body), {
      source_id: "source", target_ids: ["B"], categories: ["medication"], date_mode: dateMode,
    });
    assert.equal(state.events.reloads, 1);
    assert.equal(state.element("confirm-experiment-paste").disabled, false);
  }
  for (const status of [400, 401, 403, 404, 500]) {
    const state = setup();
    state.context.AppFetch = async () => ({ok: false, status, text: async () => "Missing source start date"});
    state.element("open-experiment-paste").listeners.click();
    await state.submit("experiment-paste-form");
    assert.deepEqual(state.events.errors, [["Missing source start date", status, "experiment-paste-dialog"]]);
    assert.equal(state.events.reloads, 0);
    assert.equal(state.element("confirm-experiment-paste").disabled, false);
    assert.ok(state.storage.has(key));
  }
  {
    const state = setup();
    let finish;
    state.context.AppFetch = () => new Promise(resolve => { finish = resolve; });
    state.element("open-experiment-paste").listeners.click();
    const pending = state.submit("experiment-paste-form");
    assert.equal(state.element("confirm-experiment-paste").disabled, true);
    await state.submit("experiment-paste-form");
    finish({ok: false, status: 400, text: async () => "Dates missing"});
    await pending;
    state.element("clear-experiment-copy").listeners.click();
    assert.equal(state.storage.has(key), false);
    assert.equal(state.element("open-experiment-paste").disabled, true);
  }
  console.log("Experiment copy selection, date modes, batch submission and error handling passed");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
