document.addEventListener("DOMContentLoaded", function() {
  // Check if there is a stored scroll position
  var scrollPosition = localStorage.getItem('scrollPosition');

  // If there is a stored scroll position, scroll to that position
  if (scrollPosition !== null) {
    window.scrollTo(0, parseInt(scrollPosition));
  }

  if (localStorage.getItem("reduced_fields")) {
    var reduced_fields = JSON.parse(localStorage.getItem("reduced_fields"));
    reduced_fields.forEach((column_index, _) => {
      document.getElementById("reduce_" + column_index.toString()).checked = false;
      Reduce(column_index);
    });
  } else {
    localStorage.setItem("reduced_fields", JSON.stringify([]));
  }
});

window.addEventListener("beforeunload", () => {
  localStorage.setItem("scrollPosition", window.scrollY);
});


async function UploadPyratData() {
  const elem = document.getElementById("pyrat_csv");
  if (elem.files.length === 0) {
    alert("No file selected!");
    return;
  }
  const formData = new FormData();
  formData.append("csv", elem.files[0]);
  formData.append("ignore_comment", document.getElementById("ignore_comment").checked);
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 5000);
  try {
    const response = await AppFetch('/upload/pyrat_csv',
      {method: "POST", body: formData, signal: ctrl.signal});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed importing animal data.", response.status, "upload_modal");
      return;
    }
    const json = await response.json();
    if (json["animal_data"].length > 2) {
      document.getElementById("animal_modal_text").textContent = json["text"];
      document.getElementById("animal_modal_text_2").style.display = "block";
      document.getElementById("animal_modal").style.height = "400px";
      document.getElementById("animal_modal").style.width = "70%";
      document.getElementById("animal_modal_table").innerHTML = json["animal_data"];
      OpenModel("animal_modal");
    }
  } catch (error) {
    console.error("Failed importing animal data:", error);
    OpenErrorModal();
  } finally {
    clearTimeout(timeout);
  }
}

function ApplyAllSelectedComments() {
  // Get all selected animals
  var checkboxes = document.getElementsByName("mark_animal");
  var mlas = [];
  for (var i=0; i<checkboxes.length; i++) {
    if (checkboxes[i].checked)
      mlas.push(checkboxes[i].getAttribute("animal_id"));
  }
  console.log("Got mlas to delete: ", mlas);
  ApplyComments(mlas);
}

async function ApplyComments(animal_ids) {
  const formData = new FormData();
  formData.append("mlas", JSON.stringify(animal_ids));
  const ctrl = new AbortController();
  const timeout = setTimeout(() => ctrl.abort(), 5000);
  try {
    const response = await AppFetch('/comments/apply',
      {method: "POST", body: formData, signal: ctrl.signal});
    const message = await response.text();
    if (!response.ok) {
      OpenErrorModal(message || "Failed applying comments.", response.status, "upload_modal");
      return;
    }
    document.getElementById("animal_modal_text").textContent = "Apply pirate comments";
    document.getElementById("animal_modal_text_2").style.display = "block";
    document.getElementById("animal_modal").style.height = "400px";
    document.getElementById("animal_modal").style.width = "70%";
    document.getElementById("animal_modal_table").innerHTML = message;
    OpenModel("animal_modal");
  } catch (error) {
    console.error("Failed applying comments:", error);
    OpenErrorModal();
  } finally {
    clearTimeout(timeout);
  }
}

async function GenerateP9(protocol, force) {
  const year = document.getElementById("inp_use_year").value;
  let downloadUrl;
  let link;
  try {
    const response = await AppFetch(
      "/generate/paragraph9/" + protocol + "/" + year + (force ? "/force" : ""),
      {method: "POST"}
    );
    if (!response.ok) {
      if (response.status === 409) {
        OpenModel("p9_error_modal");
      } else {
        OpenErrorModal(await response.text(), response.status);
      }
      return;
    }
    const filtered = response.headers.get("Filtered-Procedures-JSON");
    if (filtered) {
      const errors = JSON.parse(filtered);
      let message = "The following procedures were removed because they took place after sacrifice:\n";
      for (const [animal, procedures] of Object.entries(errors)) {
        if (procedures.length) {
          message += "- " + animal + ":\n";
          for (const procedure of procedures) {
            message += "  + " + procedure.name + ": " + procedure.start_date + " - " + procedure.end_date + "\n";
          }
        }
      }
      alert(message);
    }
    downloadUrl = URL.createObjectURL(await response.blob());
    link = document.createElement("a");
    link.href = downloadUrl;
    link.download = protocol + "_paragraph-9.pdf";
    document.body.appendChild(link);
    link.click();
  } catch (error) {
    console.error("Failed downloading paragraph 9:", error);
    OpenErrorModal("The PDF could not be downloaded. Please try again.");
  } finally {
    if (downloadUrl) {
      setTimeout(() => {
        URL.revokeObjectURL(downloadUrl);
        link?.remove();
      }, 100);
    }
  }
}

async function DeleteAnimalData(animal_id) {
  let reload = false;
  try {
    const response = await AppFetch('/animal_data/delete/' + animal_id, {method: "POST"});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message || "Failed deleting animal data.", response.status);
    } else {
      reload = true;
    }
  } catch (error) {
    console.error("Failed deleting animal data:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function UpdateSubprotocol(subprotocol, animal_id, force) {
  const formData = new FormData();
  formData.append("subprotocol", subprotocol);
  formData.append("animal_id", animal_id);
  formData.append("force", force);
  let reload = false;
  try {
    const response = await AppFetch('/update/animal_data/subprotocol', {method: "POST", body: formData});
    if (response.ok) {
      reload = true;
    } else {
      const message = await response.text();
      if (response.status === 409) {
        document.getElementById("set_subprotocol_msg").textContent = message;
        document.getElementById("set_subprotocol_btn").onclick = () =>
          UpdateSubprotocol(subprotocol, animal_id, true);
        OpenModel("confirm_modal");
      } else {
        OpenErrorModal(message || "Failed updating subprotocol.", response.status);
      }
    }
  } catch (error) {
    console.error("Failed updating subprotocol:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function UpdateProtocol(protocol, animal_id, force) {
  const formData = new FormData();
  formData.append("protocol", protocol);
  formData.append("animal_id", animal_id);
  formData.append("force", force);
  let reload = false;
  try {
    const response = await AppFetch('/update/animal_data/protocol', {method: "POST", body: formData});
    if (response.ok) {
      reload = true;
    } else {
      const message = await response.text();
      if (response.status === 409) {
        document.getElementById("set_subprotocol_msg").textContent = message;
        document.getElementById("set_subprotocol_btn").onclick = () =>
          UpdateProtocol(protocol, animal_id, true);
        OpenModel("confirm_modal");
      } else {
        OpenErrorModal(message || "Failed updating protocol.", response.status);
      }
    }
  } catch (error) {
    console.error("Failed updating protocol:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function UpdateProtocolLive(entries, protocol) {
  const animal_id = entries[0].textContent;
  const formData = new FormData();
  formData.append("protocol", protocol);
  formData.append("animal_id", animal_id);
  formData.append("force", false);
  try {
    const response = await AppFetch('/update/animal_data/protocol/live', {method: "POST", body: formData});
    const message = await response.text();
    if (!response.ok) {
      OpenErrorModal(message || "Failed updating protocol.", response.status);
      return;
    }
    const subprotocols = message ? JSON.parse(message)["subprotocols"] : [];
    const select = entries[8].children[0];
    select.replaceChildren(new Option("---", "---"));
    for (const subprotocol of subprotocols) {
      select.add(new Option(subprotocol));
    }
  } catch (error) {
    console.error("Failed updating live protocol:", error);
    OpenErrorModal();
  }
}

function NotResponsible() {
  alert("You're not responsible for this animal!")
  return false;
}

function ToggleExpandFilter() {
  let filter_div = document.getElementById("filter");
  let filter_toggle = document.getElementById("filter_toggle");
  if (filter_div.style.display === "none") {
    filter_div.style.display = "block";
    filter_toggle.innerHTML = "expand_less";
  }
  else {
    filter_div.style.display = "none";
    filter_toggle.innerHTML = "expand_more";
  }
}

function ApplySorting(key, reverse) {
  var url = new URL(window.location.href);
  url.searchParams.set('sort_by', key);
  url.searchParams.set('reverse', reverse);
  window.location = url.href;
}

function BuildFilter() {
  const from_year = document.getElementById("filter_year_from").value;
  const from_month = document.getElementById("filter_month_from").value;
  const to_year = document.getElementById("filter_year_to").value;
  const to_month = document.getElementById("filter_month_to").value;
  var url = new URL(window.location.href);
  url.searchParams.set('range', document.getElementById("filter_month_what").value);
  url.searchParams.set('from', from_year + "-" + ((from_month != "") ? from_month : "01") + "-01");
  url.searchParams.set('to', to_year+ "-" + ((to_month != "") ? to_month : "31") + "-31");
  url.searchParams.set('id', document.getElementById("filter_animal_id").value);
  console.log("HREF: ", url);
  return url;
}

function ApplyFilter() {
  window.location = BuildFilter().href;
}

async function TypeaheadFilter() {
  const url = BuildFilter();
  const req = '/table/' + url.pathname + url.search
  try {
    const response = await AppFetch(req);
    const message = await response.text();
    if (!response.ok) {
      OpenErrorModal(message, response.status);
      return;
    }
    document.getElementById("overview_table").innerHTML = message;
    ApplyReducedOverviewFields();
    ResetLoadMoreOverview(response.headers.get("X-Overview-Has-More"));
  } catch (error) {
    console.error("Failed filtering overview:", error);
    OpenErrorModal("The overview could not be loaded. Please try again.");
  }
}

function ResetLoadMoreOverview(hasMore) {
  const button = document.getElementById("load-more-overview");
  if (!button) return;

  const rows = document.querySelectorAll("#overview-table tr");
  button.dataset.offset = Math.max(rows.length - 1, 0);
  button.style.display = hasMore === "true" ? "" : "none";
  button.disabled = false;
}

async function LoadMoreOverview() {
  const button = document.getElementById("load-more-overview");
  button.disabled = true;

  const url = new URL("/table/overview/", window.location.origin);
  const activeFilters = BuildFilter();
  activeFilters.searchParams.forEach(
    (value, key) => url.searchParams.set(key, value)
  );
  url.searchParams.set("offset", button.dataset.offset);

  try {
    const response = await AppFetch(url);
    if (!response.ok) {
      OpenErrorModal(await response.text(), response.status);
      return;
    }

    const documentFragment = new DOMParser().parseFromString(
      await response.text(),
      "text/html"
    );
    const newRows = Array.from(
      documentFragment.querySelectorAll("#overview-table tr")
    ).slice(1);
    const tableBody = document.querySelector("#overview-table tbody");
    newRows.forEach(row => tableBody.appendChild(document.importNode(row, true)));
    ApplyReducedOverviewFields();

    button.dataset.offset = Number(button.dataset.offset) + newRows.length;
    const shownCount = document.getElementById("overview-shown-count");
    if (shownCount) shownCount.textContent = button.dataset.offset;
    const hasMore = response.headers.get("X-Overview-Has-More") === "true";
    button.style.display = hasMore ? "" : "none";
  } catch (error) {
    console.error("Failed loading more overview rows:", error);
    OpenErrorModal();
  } finally {
    button.disabled = false;
  }
}

function ApplyReducedOverviewFields() {
  const reducedFields = JSON.parse(
    localStorage.getItem("reduced_fields") || "[]"
  );
  reducedFields.forEach(columnIndex => Reduce(columnIndex));
}

function RemoveFilter() {
  var url = new URL(window.location.href);
  url.searchParams.delete('range');
  url.searchParams.delete('to');
  url.searchParams.delete('from');
  url.searchParams.delete('id');
  window.location = url.href;
}

function ExDispand(elem, column_index) {
  // Call Reduce-/ Expand-Function
  var reduced_fields = JSON.parse(localStorage.getItem("reduced_fields"));
  if (elem.checked) {
    if (reduced_fields.indexOf(column_index) > -1)
      reduced_fields.splice(reduced_fields.indexOf(column_index), 1);
    Expand(column_index);
  } else {
    if (!reduced_fields.includes(column_index))
      reduced_fields.push(column_index)
    Reduce(column_index);
  }
  // Save reduced fields.
  localStorage.setItem("reduced_fields", JSON.stringify(reduced_fields));
}

function Reduce(column_index) {
  var table = document.getElementById("overview-table");
  // Modify table
  for (var i=0, row; row = table.rows[i]; i++) {
    row.cells[column_index].classList.add('hide-column');
  }
}

function Expand(column_index) {
  var table = document.getElementById("overview-table");
  // Modify table
  for (var i=0, row; row = table.rows[i]; i++) {
    row.cells[column_index].classList.remove('hide-column');
  }
}
