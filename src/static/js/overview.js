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
  if (elem.files.length == 0) {
    alert("No file selected!");
    return;
  }
  let pyrat_csv = elem.files[0];
  console.log(pyrat_csv);
  let formData = new FormData();

  formData.append("csv", pyrat_csv);
  formData.append("ignore_comment", document.getElementById("ignore_comment").checked);
  
  const ctrl = new AbortController();    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  // Send request to server.
  try {
    // Send request:
    let r = await fetch('/upload/pyrat_csv', 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    // Handle response:
      if (r.status != 200) {
        r.text().then(text => OpenErrorModal(text, r.status, "upload_modal"));
      }
      else {
        let json = await r.json()
        if (json["animal_data"].length > 2) {
          document.getElementById("animal_modal_text").innerHTML = json["text"];
          document.getElementById("animal_modal_text_2").style.display = "block";
          document.getElementById("animal_modal").style.height = "400px";
          document.getElementById("animal_modal").style.width = "70%";
          document.getElementById("animal_modal_table").innerHTML = json["animal_data"];
          OpenModel("animal_modal")
        }
      }
  } catch(e) {
    alert("Something went wrong: " + e);
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
  let formData = new FormData();
  formData.append("mlas", JSON.stringify(animal_ids));
  
  const ctrl = new AbortController();    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  // Send request to server.
  try {
    // Send request:
    let r = await fetch('/comments/apply', 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    // Handle response:
      if (r.status != 200) {
        r.text().then(text => OpenErrorModal(text, r.status, "upload_modal"));
      }
      else {
        r.text().then(text => {
          document.getElementById("animal_modal_text").innerHTML = "Apply pirate comments";
          document.getElementById("animal_modal_text_2").style.display = "block";
          document.getElementById("animal_modal").style.height = "400px";
          document.getElementById("animal_modal").style.width = "70%";
          document.getElementById("animal_modal_table").innerHTML = text;
          OpenModel("animal_modal");
        });
      }
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}
function parseHttpHeaders(httpHeaders) {
    return httpHeaders.split("\n")
     .map(x=>x.split(/: */,2))
     .filter(x=>x[0])
     .reduce((ac, x)=>{ac[x[0]] = x[1];return ac;}, {});
}

function GenerateP9(protocol, force) {
  const use_year = document.getElementById("inp_use_year").value;
  var req = new XMLHttpRequest();
  req.open("POST", "/generate/paragraph9/"+protocol + "/" + use_year + ((force) ? "/force" : ""), true);
  req.responseType = "blob";
  req.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  req.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      // Print potential errors:
      const error_json = JSON.parse(req.getResponseHeader('filtered-procedures-json'));
      if (error_json) {
        console.log(error_json);
        msg = "The following procedures where removed since they took place after the "
          + "sacrifice of the animals: \n";
        Object.keys(error_json).forEach(function(key) {
          if (error_json[key].length > 0) {
            msg += "- " + key + ": \n";
            error_json[key].forEach(p => {
              msg += "  + " + p["name"] + ": " + p["start_date"] + " - " + p["end_date"] + "\n"
            });
          }
        });
        alert(msg);
      }

      // Get pdf
      var blob = new Blob([this.response], {"type": "application/pdf"});
      var url = window.URL.createObjectURL(blob);
      var link = document.createElement('a');
      document.body.appendChild(link);
      link.style = "display: none";
      link.href = url;
      link.download = protocol + "_paragraph-9.pdf";
      link.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        link.remove(); 
      } , 100);
    }
    else if (this.readyState === 4 && this.status == 409) {
      OpenModel("p9_error_modal");
    }
    else if (this.readyState === 4 && this.status != 400 ) {
      var blob = new Blob([this.response], {type: "text"});
      var reader = new FileReader();
      reader.onload = function() {
        OpenErrorModal(reader.result, this.status);
      }
      reader.readAsText(blob);
    }
  };
  req.send();
}

async function DeleteAnimalData(animal_id) {
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/animal_data/delete/' + animal_id, {method: "POST"}); 
    // Handle response:
    if (r.status === 200) {
      window.location=window.location;
    }
    else {
      alert("Something went wrong: Error code: " + r.status);
      window.location=window.location;
    }
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}


async function UpdateSubprotocol(subprotocol, animal_id, force) {
  let formData = new FormData();
  // Add extracted data to form.
  formData.append("subprotocol", subprotocol);
  formData.append("animal_id", animal_id);
  formData.append("force", force);
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/update/animal_data/subprotocol', {method: "POST", body: formData}); 
    // Handle response:
    if (r.status === 200) {
      window.location=window.location;
    }
    else if (r.status === 400) {
      let response_text = await r.text()
      alert(response_text + ": " + r.status);
    }
    else if (r.status === 409) {
      let response_text = await r.text()
      var dialog = document.getElementById("confirm_modal"); 
      document.getElementById("set_subprotocol_msg").innerHTML = response_text; 
      document.getElementById("set_subprotocol_btn").setAttribute("onclick", 
        "UpdateSubprotocol('"+subprotocol+"', '"+animal_id+"', true)");
      dialog.showModal(); 
    }
    else {
      alert("Something went wrong: Error code: " + r.status);
      window.location=window.location;
    }
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

async function UpdateProtocol(protocol, animal_id, force) {
  console.log("UpdateProtocol", protocol, animal_id, force);
  let formData = new FormData();
  // Add extracted data to form.
  formData.append("protocol", protocol);
  formData.append("animal_id", animal_id);
  formData.append("force", force);
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/update/animal_data/protocol', {method: "POST", body: formData}); 
    // Handle response:
    if (r.status === 200) {
      window.location=window.location;
    }
    else if (r.status === 409) {
      let response_text = await r.text()
      var dialog = document.getElementById("confirm_modal"); 
      document.getElementById("set_subprotocol_msg").innerHTML = response_text; 
      document.getElementById("set_subprotocol_btn").setAttribute("onclick", 
        "UpdateProtocol('"+protocol+"', '"+animal_id+"', true)");
      dialog.showModal(); 
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

async function UpdateProtocolLive(entries, protocol) {
  console.log("ENTRIES: ", entries);
  const animal_id = entries[0].innerHTML;
  let formData = new FormData();
  // Add extracted data to form.
  formData.append("protocol", protocol);
  formData.append("animal_id", animal_id);
  formData.append("force", false);
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/update/animal_data/protocol/live', {method: "POST", body: formData}); 
    // Handle response:
    if (r.status === 200) {
      var selectElement = entries[7].children[0];
      var response = await r.json();
      console.log("RESPONSE: ", response);
      var subprotocols = response["subprotocols"]
      for (var i=0; i<=subprotocols.length; i++) {
        console.log("Adding ", subprotocols[i]);
        selectElement.add(new Option(subprotocols[i])); 
      }
    }
    else {
      let response_text = await r.text()
      document.getElementById("animal_modal_text_3").innerHTML = response_text; 
    }
  } catch(e) {
    alert("Something went wrong: " + e);
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

function TypeaheadFilter() {
  const url = BuildFilter();
  const req = '/table/' + url.pathname + url.search
  fetch(req)
    .then(response => {
      if (response.ok) {
        response.text().then(text => {
          document.getElementById("overview_table").innerHTML = text;
          ApplyReducedOverviewFields();
          ResetLoadMoreOverview(response.headers.get("X-Overview-Has-More"));
        });
      }
    })
    .catch(error => {
      OpenErrorModal(error);
    })
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
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Error code: ${response.status}`);

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
    OpenErrorModal(error);
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
