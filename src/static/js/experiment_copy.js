(() => {
  const clipboardKey = "flake.experiment-copy";
  const categoryLabels = {procedures: "procedures", medication: "medication", viruses: "viruses"};

  document.addEventListener("DOMContentLoaded", () => {
    const tools = document.getElementById("experiment-copy-tools");
    if (!tools) return;
    const element = id => document.getElementById(id);
    const copyButton = element("open-experiment-copy");
    const pasteButton = element("open-experiment-paste");
    const confirmButton = element("confirm-experiment-paste");
    let pendingSource;
    let pendingPaste;
    let targetRows = [];
    let copying = false;
    let loadingPaste = false;
    let pasting = false;

    function clipboard() {
      try {
        const data = JSON.parse(sessionStorage.getItem(clipboardKey));
        if (data?.user_id !== tools.dataset.userId || typeof data.source_id !== "string" ||
            !data.source_id || !Array.isArray(data.categories) || !data.categories.length ||
            data.categories.some(category => !Object.hasOwn(categoryLabels, category))) return null;
        return data;
      } catch {
        return null;
      }
    }

    function selectedAnimals() {
      return [...new Set(Array.from(document.querySelectorAll('[name="mark_animal"]:checked'),
        input => input.getAttribute("animal_id")))];
    }

    function setMode(mode) {
      element("experiment-copy-mode").checked = mode === "copy";
      element("experiment-paste-mode").checked = mode === "paste";
      updateSelectionState();
    }

    function updateSelectionState() {
      const data = clipboard();
      const selected = selectedAnimals();
      const copyMode = element("experiment-copy-mode").checked;
      element("experiment-copy-status").textContent = data
        ? `Copy from ${data.source_id}: ${data.categories.map(c => categoryLabels[c]).join(", ")}.`
        : "No experiment data copied.";
      element("experiment-copy-selected").textContent = copyMode
        ? `${selected.length} animals selected. Select one source animal to copy.`
        : `${selected.length} destination animals selected.`;
      element("clear-experiment-copy").hidden = !data;
      copyButton.hidden = !copyMode;
      pasteButton.hidden = copyMode;
      copyButton.disabled = selected.length !== 1 || copying || pasting;
      pasteButton.disabled = !data || !selected.length || loadingPaste || pasting;
    }

    async function preview(sourceId, targetIds) {
      const response = await AppFetch("/animal_data/copy/preview", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({source_id: sourceId, target_ids: targetIds}),
      });
      if (!response.ok) {
        OpenErrorModal(await response.text(), response.status);
        return null;
      }
      return response.json();
    }

    copyButton.addEventListener("click", async () => {
      const selected = selectedAnimals();
      if (selected.length !== 1 || copying || pasting) return;
      copying = true;
      updateSelectionState();
      try {
        const result = await preview(selected[0], []);
        if (!result || !element("experiment-copy-mode").checked) return;
        pendingSource = result.source.animal_id;
        element("experiment-copy-source").textContent = pendingSource;
        element("experiment-copy-dates").textContent =
          `Start: ${result.source.start || "missing"}. Sacrifice: ${result.source.sacrifice_date || "missing"}.`;
        document.querySelectorAll('[name="copy_category"]').forEach(input => {
          const count = result.counts[input.value];
          element(`experiment-copy-count-${input.value}`).textContent = count;
          input.checked = count > 0;
          input.disabled = !count;
        });
        element("experiment-copy-dialog").showModal();
      } catch (error) {
        console.error("Failed reading source animal:", error);
        OpenErrorModal("The source animal could not be loaded.");
      } finally {
        copying = false;
        updateSelectionState();
      }
    });

    element("experiment-copy-form").addEventListener("submit", event => {
      event.preventDefault();
      if (!pendingSource) return;
      const categories = Array.from(document.querySelectorAll('[name="copy_category"]:checked'), input => input.value);
      if (!categories.length) {
        OpenErrorModal("Select at least one category to copy.", undefined, "experiment-copy-dialog");
        return;
      }
      try {
        sessionStorage.setItem(clipboardKey, JSON.stringify({
          source_id: pendingSource, categories, user_id: tools.dataset.userId,
        }));
        element("experiment-copy-dialog").close();
        document.querySelectorAll('[name="mark_animal"]:checked').forEach(input => { input.checked = false; });
        const selectAll = document.querySelector('#overview-table th input[type="checkbox"]');
        if (selectAll) selectAll.checked = false;
        setMode("paste");
      } catch {
        OpenErrorModal("The copied selection could not be saved in this tab.", undefined, "experiment-copy-dialog");
      }
    });

    function node(tag, text) {
      const result = document.createElement(tag);
      if (text !== undefined) result.textContent = text;
      return result;
    }

    function dateCell(target, field, label, sourceDate, rowState) {
      const cell = node("td");
      if (target[field]) {
        cell.append(node("span", target[field]), node("span", " (existing)"));
      } else {
        const input = node("input");
        input.type = "date";
        input.min = target.dob;
        input.required = true;
        input.setAttribute("aria-label", `${target.animal_id} ${label}`);
        input.dataset.dateField = field;
        rowState.inputs[field] = input;
        const useSource = node("button", `Use source ${label}`);
        useSource.type = "button";
        useSource.disabled = !sourceDate;
        useSource.addEventListener("click", () => {
          input.value = sourceDate;
          updatePasteReview();
        });
        rowState.sourceButtons.push({button: useSource, available: Boolean(sourceDate)});
        cell.append(input, useSource);
      }
      return cell;
    }

    function renderTargets(result) {
      const body = element("experiment-paste-targets");
      body.replaceChildren();
      targetRows = result.targets.map(target => {
        const row = node("tr");
        row.dataset.animalId = target.animal_id;
        const state = {target, row, inputs: {}, sourceButtons: [], skip: node("input"), status: node("span")};
        state.skip.type = "checkbox";
        state.skip.dataset.skipAnimal = "";
        state.status.className = "copy-date-status";
        const action = node("td");
        const label = node("label");
        label.append(state.skip, node("span", " Skip animal"));
        action.append(state.status, label);
        row.append(node("td", target.animal_id),
          dateCell(target, "start", "start date", result.source.start, state),
          dateCell(target, "sacrifice_date", "sacrifice date", result.source.sacrifice_date, state), action);
        body.append(row);
        return state;
      });
      updatePasteReview();
    }

    function updatePasteReview() {
      let ready = 0;
      let missing = 0;
      let skipped = 0;
      for (const state of targetRows) {
        const skip = state.skip.checked;
        const start = state.inputs.start?.value || state.target.start;
        const end = state.inputs.sacrifice_date?.value || state.target.sacrifice_date;
        if (state.inputs.start) state.inputs.start.max = end || "";
        if (state.inputs.sacrifice_date) state.inputs.sacrifice_date.min = start || state.target.dob;
        for (const input of Object.values(state.inputs)) {
          input.disabled = skip;
          input.required = !skip;
        }
        for (const {button, available} of state.sourceButtons) button.disabled = skip || !available;
        const complete = Boolean(start && end && Object.values(state.inputs).every(input => input.checkValidity()));
        state.row.classList.toggle("copy-date-row--ready", !skip && complete);
        state.row.classList.toggle("copy-date-row--missing", !skip && !complete);
        state.row.classList.toggle("copy-date-row--skipped", skip);
        state.status.textContent = skip ? "Skipped" : complete ? "Ready" : "Enter valid dates";
        if (skip) skipped++;
        else if (complete) ready++;
        else missing++;
      }
      element("experiment-paste-ready").textContent = `${ready} ready, ${missing} need dates, ${skipped} skipped.`;
      confirmButton.disabled = pasting || !ready || missing > 0;
    }

    pasteButton.addEventListener("click", async () => {
      const data = clipboard();
      const targetIds = selectedAnimals();
      if (!data || !targetIds.length || loadingPaste || pasting) return;
      if (targetIds.includes(data.source_id)) {
        OpenErrorModal("Deselect the source animal before pasting.");
        return;
      }
      loadingPaste = true;
      updateSelectionState();
      try {
        const result = await preview(data.source_id, targetIds);
        if (!result || !element("experiment-paste-mode").checked) return;
        pendingPaste = {...data, target_ids: targetIds};
        element("experiment-paste-summary").textContent =
          `Replace ${data.categories.map(c => categoryLabels[c]).join(", ")} from ${data.source_id} for the included animals.`;
        renderTargets(result);
        element("experiment-paste-dialog").showModal();
      } catch (error) {
        console.error("Failed reading destination dates:", error);
        OpenErrorModal("The destination animals could not be loaded.");
      } finally {
        loadingPaste = false;
        updateSelectionState();
      }
    });

    element("experiment-paste-form").addEventListener("submit", async event => {
      event.preventDefault();
      updatePasteReview();
      if (!pendingPaste || confirmButton.disabled) return;
      const skipIds = targetRows.filter(state => state.skip.checked).map(state => state.target.animal_id);
      const targetDates = {};
      for (const state of targetRows.filter(state => !state.skip.checked)) {
        if (Object.keys(state.inputs).length) {
          targetDates[state.target.animal_id] = Object.fromEntries(
            Object.entries(state.inputs).map(([field, input]) => [field, input.value]));
        }
      }
      pasting = true;
      updatePasteReview();
      updateSelectionState();
      try {
        const response = await AppFetch("/animal_data/copy", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            source_id: pendingPaste.source_id, target_ids: pendingPaste.target_ids,
            categories: pendingPaste.categories, target_dates: targetDates, skip_ids: skipIds,
            date_mode: document.querySelector('[name="copy_date_mode"]:checked').value,
          }),
        });
        if (!response.ok) {
          OpenErrorModal(await response.text(), response.status, "experiment-paste-dialog");
          return;
        }
        const result = await response.json();
        alert(`Copied ${result.copied_rows} entries to ${result.target_ids.length} animals. ${result.skipped_ids.length} skipped.`);
        window.location.reload();
      } catch (error) {
        console.error("Failed copying experiment data:", error);
        OpenErrorModal(undefined, undefined, "experiment-paste-dialog");
      } finally {
        pasting = false;
        updatePasteReview();
        updateSelectionState();
      }
    });

    element("experiment-paste-targets").addEventListener("input", updatePasteReview);
    element("experiment-paste-targets").addEventListener("change", updatePasteReview);
    element("clear-experiment-copy").addEventListener("click", () => {
      if (pasting) return;
      try {
        sessionStorage.removeItem(clipboardKey);
        setMode("copy");
      } catch {
        OpenErrorModal("The copied selection could not be cleared in this tab.");
      }
    });
    tools.querySelectorAll("[data-close-copy-dialog]").forEach(button => {
      button.addEventListener("click", () => button.closest("dialog").close());
    });
    document.addEventListener("change", updateSelectionState);
    const table = element("overview_table");
    if (table) new MutationObserver(updateSelectionState).observe(table, {childList: true, subtree: true});
    setMode(clipboard() ? "paste" : "copy");
  });
})();
