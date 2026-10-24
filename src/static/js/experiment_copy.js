(() => {
  const clipboardKey = "flake.experiment-copy";
  const categoryLabels = {procedures: "procedures", medication: "medication", viruses: "viruses"};

  document.addEventListener("DOMContentLoaded", () => {
    const tools = document.getElementById("experiment-copy-tools");
    if (!tools) return;
    const status = document.getElementById("experiment-copy-status");
    const pasteButton = document.getElementById("open-experiment-paste");
    let pendingPaste;

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

    function updatePasteState() {
      if (!pasteButton) return;
      const data = clipboard();
      const selected = selectedAnimals();
      status.textContent = data ? `Copy from ${data.source_id}: ${data.categories.map(c => categoryLabels[c]).join(", ")}.`
        : "No experiment data copied.";
      document.getElementById("experiment-copy-selected").textContent = `${selected.length} animals selected.`;
      document.getElementById("clear-experiment-copy").hidden = !data;
      pasteButton.disabled = !data || !selected.length;
    }

    document.getElementById("open-experiment-copy")?.addEventListener("click", () => {
      document.getElementById("experiment-copy-dialog").showModal();
    });
    document.getElementById("experiment-copy-form")?.addEventListener("submit", event => {
      event.preventDefault();
      const categories = Array.from(document.querySelectorAll('[name="copy_category"]:checked'), input => input.value);
      if (!categories.length) {
        OpenErrorModal("Select at least one category to copy.", undefined, "experiment-copy-dialog");
        return;
      }
      try {
        sessionStorage.setItem(clipboardKey, JSON.stringify({
          source_id: tools.dataset.sourceId, categories, user_id: tools.dataset.userId,
        }));
        document.getElementById("experiment-copy-dialog").close();
        status.textContent = "Selection copied. Choose destination animals on an overview page.";
      } catch {
        OpenErrorModal("The copied selection could not be saved in this tab.", undefined, "experiment-copy-dialog");
      }
    });

    pasteButton?.addEventListener("click", () => {
      const data = clipboard();
      const targetIds = selectedAnimals();
      if (!data || !targetIds.length) return;
      if (targetIds.includes(data.source_id)) {
        OpenErrorModal("Deselect the source animal before pasting.");
        return;
      }
      pendingPaste = {...data, target_ids: targetIds};
      document.getElementById("experiment-paste-summary").textContent =
        `Replace ${data.categories.map(c => categoryLabels[c]).join(", ")} from ${data.source_id} for ${targetIds.length} animals.`;
      document.getElementById("experiment-paste-targets").textContent = targetIds.join(", ");
      document.getElementById("experiment-paste-dialog").showModal();
    });

    document.getElementById("experiment-paste-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      if (!pendingPaste) return;
      const button = document.getElementById("confirm-experiment-paste");
      if (button.disabled) return;
      button.disabled = true;
      try {
        const response = await AppFetch("/animal_data/copy", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            source_id: pendingPaste.source_id, target_ids: pendingPaste.target_ids,
            categories: pendingPaste.categories,
            date_mode: document.querySelector('[name="copy_date_mode"]:checked').value,
          }),
        });
        if (!response.ok) {
          OpenErrorModal(await response.text(), response.status, "experiment-paste-dialog");
          return;
        }
        const result = await response.json();
        alert(`Copied ${result.copied_rows} entries to ${result.target_ids.length} animals.`);
        window.location.reload();
      } catch (error) {
        console.error("Failed copying experiment data:", error);
        OpenErrorModal(undefined, undefined, "experiment-paste-dialog");
      } finally {
        button.disabled = false;
      }
    });

    document.getElementById("clear-experiment-copy")?.addEventListener("click", () => {
      try {
        sessionStorage.removeItem(clipboardKey);
        updatePasteState();
      } catch {
        OpenErrorModal("The copied selection could not be cleared in this tab.");
      }
    });
    tools.querySelectorAll("[data-close-copy-dialog]").forEach(button => {
      button.addEventListener("click", () => button.closest("dialog").close());
    });
    document.addEventListener("change", updatePasteState);
    const table = document.getElementById("overview_table");
    if (table) new MutationObserver(updatePasteState).observe(table, {childList: true, subtree: true});
    updatePasteState();
  });
})();
