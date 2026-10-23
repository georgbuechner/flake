const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

async function main() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      const node = {textContent: "", open: true, style: {},
        close() { this.open = false; }, showModal() { this.open = true; }};
      if (["error_modal_msg", "animal_modal_text_3", "animal_modal_text"].includes(id)) {
        Object.defineProperty(node, "innerHTML", {
          set() { throw new Error(`Message ${id} must not be parsed as HTML`); },
        });
      }
      elements.set(id, node);
    }
    return elements.get(id);
  }
  const payload = '<img src=x onerror="alert(1)"> & <script>alert(2)</script>';
  const context = {
    Headers,
    document: {getElementById: element, addEventListener() {}},
    console: {log() {}, error() {}},
    FormData: class {append() {}},
    window: {location: {reload() { throw new Error("Unexpected reload"); }}},
    alert() {},
  };
  vm.createContext(context);
  for (const name of ["general", "definitions"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, `../src/static/js/${name}.js`), "utf8"), context);
  }

  context.OpenErrorModal(payload, 400, "edit_modal");
  assert.equal(element("error_modal_msg").textContent, `${payload} (status: 400)`);
  assert.equal(element("edit_modal").open, false);
  context.OpenErrorModal();
  assert.match(element("error_modal_msg").textContent, /result could not be confirmed/);
  assert.ok(!element("error_modal_msg").textContent.includes("undefined"));

  const row = {children: Array.from({length: 9}, () => ({children: [{value: "value"}]})),
    classList: {remove() {}}};
  row.children[0].innerHTML = "animal";
  for (const ok of [false, true]) {
    context.fetch = async () => ({ok, status: ok ? 200 : 400, text: async () => payload});
    await context.UpdateAll(row);
    assert.equal(element("animal_modal_text_3").textContent, ok ? payload : `${payload} 400`);
  }

  context.fetch = async () => ({ok: true, json: async () => ({
    text: payload, animal_data: "<table><tr><td>animal</td></tr></table>",
  })});
  await context.ReloadSubprotocols("protocol/sub");
  assert.equal(element("animal_modal_text").textContent, payload);
  assert.equal(element("animal_modal_table").innerHTML, "<table><tr><td>animal</td></tr></table>");
  console.log("Plain-text modal, inline error, warning and reload-message checks passed");
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
