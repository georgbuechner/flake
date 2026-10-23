const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function setup() {
  const elements = new Map();
  const events = {errors: [], dialogs: [], downloads: [], revoked: [], ready: [], timers: new Map(), intervals: new Map()};
  let timerId = 0;
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: "2026", style: {}, dataset: {offset: "0"}, attributes: {},
      setAttribute(name, value) { this.attributes[name] = value; },
    });
    return elements.get(id);
  }
  class TestURL extends URL {
    static createObjectURL() { return "blob:test"; }
    static revokeObjectURL(url) { events.revoked.push(url); }
  }
  const context = {
    Headers, URL: TestURL, Blob,
    document: {
      addEventListener(event, listener) { if (event === "DOMContentLoaded") events.ready.push(listener); },
      getElementById: element, body: {appendChild() {}},
      createElement() { return {click() { events.downloads.push(this.download); }, remove() { this.removed = true; }}; },
    },
    window: {addEventListener() {}, location: {href: "https://flake.test/overview", origin: "https://flake.test"}},
    console: {log() {}, error() {}}, alert() {},
    setInterval(callback) { events.intervals.set(++timerId, callback); return timerId; },
    clearInterval(id) { events.intervals.delete(id); },
    setTimeout(callback) { events.timers.set(++timerId, callback); return timerId; },
    clearTimeout(id) { events.timers.delete(id); },
  };
  vm.createContext(context);
  for (const name of ["general", "input", "overview"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, `../src/static/js/${name}.js`), "utf8"), context);
  }
  context.OpenErrorModal = (...args) => events.errors.push(args);
  context.OpenModel = id => events.dialogs.push(id);
  return {context, events, element};
}

function response(status, message = "Useful server message") {
  return {ok: status >= 200 && status < 300, status, headers: new Headers(),
    text: async () => message, blob: async () => new Blob(["document"])};
}

async function main() {
  for (const status of [400, 401, 403, 404, 409, 422, 500]) {
    const {context, events, element} = setup();
    context.fetch = async (url, options) => {
      assert.equal(options.headers.get("X-Requested-With"), "XMLHttpRequest");
      return response(status);
    };
    await context.GenerateMainSheet("animal", "score_sheet");
    assert.deepEqual(events.errors, [["Useful server message", status]]);
    assert.equal(element("progress_container").style.display, "none");
    assert.equal(events.intervals.size, 0);
    assert.equal(events.downloads.length, 0);
    events.errors.length = 0;
    await context.GenerateP9("protocol", false);
    if (status === 409) assert.deepEqual(events.dialogs, ["p9_error_modal"]);
    else assert.deepEqual(events.errors, [["Useful server message", status]]);
    assert.equal(events.downloads.length, 0);
  }

  for (const operation of ["GenerateMainSheet", "GenerateP9"]) {
    const {context, events, element} = setup();
    context.fetch = async () => { throw new Error("offline"); };
    await context[operation]("animal", operation === "GenerateMainSheet" ? "score_sheet" : false);
    assert.equal(events.errors.length, 1);
    assert.equal(events.downloads.length, 0);
    assert.equal(events.intervals.size, 0);
    if (operation === "GenerateMainSheet") assert.equal(element("progress_container").style.display, "none");
  }

  for (const operation of ["GenerateMainSheet", "GenerateP9"]) {
    const {context, events} = setup();
    context.fetch = async () => response(200);
    await context[operation]("animal", operation === "GenerateMainSheet" ? "score_sheet" : false);
    assert.deepEqual(events.errors, []);
    assert.deepEqual(events.downloads, [operation === "GenerateMainSheet" ? "animal_score_sheet.docx" : "animal_paragraph-9.pdf"]);
    assert.equal(events.intervals.size, 0);
    for (const callback of events.timers.values()) callback();
    assert.deepEqual(events.revoked, ["blob:test"]);
  }

  const {context, events, element} = setup();
  let savedOptions;
  context.fetch = async (url, options) => { savedOptions = options; return response(200); };
  await context.AppFetch("/operation", {method: "POST", headers: {"Content-Type": "custom/type"}, body: "data"});
  assert.equal(savedOptions.headers.get("Content-Type"), "custom/type");
  assert.equal(savedOptions.headers.get("X-Requested-With"), "XMLHttpRequest");
  assert.equal(savedOptions.body, "data");

  context.fetch = async () => response(404);
  assert.equal(await context.UpdateProgress("job"), true);
  assert.deepEqual(events.errors, []);
  context.fetch = async () => response(401, "Log in again");
  assert.equal(await context.UpdateProgress("job"), false);
  assert.deepEqual(events.errors.pop(), ["Log in again", 401]);
  context.fetch = async () => ({...response(200), json: async () => ({cur: 2, total: 3})});
  assert.equal(await context.UpdateProgress("job"), true);
  assert.equal(element("progress_bar").attributes.value, 2);

  context.BuildFilter = () => new URL("https://flake.test/overview");
  for (const operation of ["TypeaheadFilter", "LoadMoreOverview"]) {
    context.fetch = async () => response(500);
    await context[operation]();
    assert.deepEqual(events.errors.pop(), ["Useful server message", 500]);
    context.fetch = async () => { throw new Error("offline"); };
    await context[operation]();
    assert.equal(events.errors.length, 1);
    events.errors.length = 0;
  }
  assert.equal(element("load-more-overview").disabled, false);

  function form(marked, dialog) {
    return {marked, action: "/save", method: "post", listeners: {},
      addEventListener(event, listener) { this.listeners[event] = listener; },
      closest() { return dialog ? {id: dialog} : null; }};
  }
  const startDate = form(false);
  const editor = form(true, "edit_modal");
  const general = form(true);
  const deathDate = form(false, "death_edit_modal");
  context.document.querySelectorAll = selector => {
    assert.equal(selector, "form[data-ajax-submit]");
    return [startDate, editor, general, deathDate].filter(form => form.marked);
  };
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/static/js/definitions.js"), "utf8"), context);
  events.ready.at(-1)();
  assert.equal(startDate.listeners.submit, undefined);
  assert.equal(deathDate.listeners.submit, undefined);
  context.FormData = class {};
  context.fetch = async () => response(422);
  for (const target of [editor, general]) {
    let prevented = false;
    await target.listeners.submit({preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.deepEqual(events.errors.pop(), ["Useful server message", 422, target === editor ? "edit_modal" : undefined]);
  }
  console.log("AJAX authentication headers, download errors/success/cleanup, filtering and progress checks passed");
}

main().catch(error => { console.error(error); process.exitCode = 1; });
