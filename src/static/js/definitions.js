document.addEventListener('DOMContentLoaded', function() {
  for (const form of document.querySelectorAll('form[data-ajax-submit]')) {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const previous = form.closest('dialog')?.id;
      try {
        const response = await AppFetch(form.action, {
          method: form.method,
          body: new FormData(form),
        });
        if (!response.ok) {
          const message = await response.text();
          OpenErrorModal(message, response.status, previous);
          return;
        }
      } catch(error) {
        console.error("Failed submitting definition form:", error);
        OpenErrorModal(undefined, undefined, previous);
        return;
      }

      window.location.reload();
    });
  }
});

function SetEditName(form, value) {
  const field = form.querySelector("#name");
  let display = form.querySelector("[data-edit-name]");
  let submittedName = form.querySelector("[data-edit-name-value]");
  let originalName = form.querySelector('[name="original_name"]');
  if (!display) {
    display = document.createElement("span");
    display.setAttribute("data-edit-name", "");
    field.after(display);
    submittedName = document.createElement("input");
    submittedName.type = "hidden";
    submittedName.name = "name";
    submittedName.setAttribute("data-edit-name-value", "");
    form.append(submittedName);
    originalName = document.createElement("input");
    originalName.type = "hidden";
    originalName.name = "original_name";
    form.append(originalName);
  }
  const locked = value !== null;
  field.hidden = locked;
  field.disabled = locked;
  display.hidden = !locked;
  display.textContent = value ?? "";
  submittedName.disabled = !locked;
  submittedName.value = value ?? "";
  // Definitions use their original name as identity; other entries have UUIDs.
  originalName.disabled = !locked || form.elements.namedItem("uuid") !== null;
  originalName.value = value ?? "";
}

function Add(entry) {
  const form = document.querySelector("#edit_modal form");
  form.reset();
  SetEditName(form, null);
  for (const field of form.querySelectorAll(".date_suggest")) {
    field.classList.remove("date_suggest");
  }
  if (entry !== undefined) {
    for (const cell of entry.children) {
      const name = cell.getAttribute("name");
      if (!name) continue;
      const value = cell.getAttribute("data-value") ??
        (name === "name" ? cell.textContent : cell.textContent.trim());
      if (name === "name") {
        SetEditName(form, value);
        continue;
      }
      const field = form.elements.namedItem(name);
      if (!field) continue;
      if (field.type === "checkbox") {
        field.checked = value === "True" || value === "yes";
      } else {
        const start = document.getElementById("start");
        if (name.includes("date") && value === "---" && start) {
          field.value = start.value;
          field.classList.add("date_suggest");
        } else {
          field.value = value;
        }
      }
    }
  }
  const weightIndependent = form.elements.namedItem("weight_independant");
  if (weightIndependent) SwitchWeightDependant(weightIndependent.checked);
  OpenModel("edit_modal");
}

function BlockAmount() {
  document.getElementById("dosis").removeAttribute("readonly");
  document.getElementById("amount").setAttribute("readonly", "readonly");
  document.getElementById("amount").title = "Amount is calculated based on a default of 30g oder the animals weight.";
}
function BlockDosis() {
  document.getElementById("amount").removeAttribute("readonly");
  document.getElementById("dosis").setAttribute("readonly", "readonly");
  document.getElementById("dosis").title = "Dosis cannot be set if weight-independant.";
}

function SwitchWeightDependant(checked) {
  if (checked)
    BlockDosis();
  else
    BlockAmount();
}

async function DelProtocolEntry(category, uuid) {
  console.log(category, uuid);
  let reload = false;
  try {
    // Send request:
    let response = await AppFetch("/settings/protocols/delete/" + category + "/" + uuid,
      {method: "POST", body: new FormData}); 
    // Handle response:
    if (!response.ok) {
      let message = await response.text()
      OpenErrorModal(message || "Failed deleting entry.", response.status);
    }
    else {
      reload = true;
    }
  } catch(error) {
    console.error("Failed deleting protocol entry:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function DelADEntry(animal_id, category, uuid) {
  console.log(category, uuid);
  let reload = false;
  try {
    // Send request:
    let response = await AppFetch("/animal_data/" + animal_id + "/delete/" + category + "/" + uuid,
      {method: "POST", body: new FormData}); 
    // Handle response:
    if (!response.ok) {
      let message = await response.text()
      OpenErrorModal(message || "Failed deleting entry.", response.status);
    }
    else {
      reload = true;
    }
  } catch(error) {
    console.error("Failed deleting animal data entry:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function Del(category, name, type, identifier, protocol) {
  const escaped_name = encodeURIComponent(name);
  let base_url = "";
  if (type === "protocol") 
    base_url = "/settings/protocols/" + identifier;
  else if (type === "experiment")
    base_url = "/animal_data/" + identifier;
  else 
    base_url = "/definitions";
  // Add date if set.
  protocol = (protocol !== undefined) ? "/"+protocol: "";
  console.log(category, escaped_name);
  let reload = false;

  try {
    // Send request:
    let response = await AppFetch(base_url+"/delete/" + category + "/" + escaped_name + protocol, {
      method: "POST", body: new FormData}); 
    // Handle response:
    if (!response.ok) {
      let message = await response.text()
      OpenErrorModal(message || "Failed deleting entry.", response.status);
    }
    else {
      reload = true;
    }
  } catch(error) {
    console.error("Failed saveing notes:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

function Restricted() {
  alert("This action is restricted to admin-users!")
}

function Set(elem, availible) {
  console.log("all availible entries: ", availible)
  const getByKey = (arr, key) => (arr.find(x => x["name"] === key) || {});
  const definition = getByKey(availible, elem.value);
  for (const [key, value] of Object.entries(definition)) {
    let el = document.getElementById(key)
    if (el !== undefined && el !== null) {
      if ((el || {}).type === "checkbox" && value === true) {
        el.checked = true;
        if (el.id === "weight_independant") BlockDosis();
      }
      else if ((el || {}).type === "checkbox" && value === false) {
        el.checked = false;
        if (el.id === "weight_independant") BlockAmount();
      }
      else 
        el.value = value; 
    }
  }
}

function OpenAllowedUsers() {
  var users = document.getElementById("allowed_users").value;
  users.split(", ").forEach(function(user) {
    if (user !== "")
      AddAllowedUser(user); 
  });
  OpenModel("allowed_users_modal"); 
}

function CloseAllowedUsers(store) {
  var table = document.getElementById("allowed_users_table");
  var users = "";
  while(table.rows.length > 1) {
    users += table.rows[1].cells[0].innerHTML + ", ";
    table.deleteRow(1);
  }
  if (users.length >=2) 
    users = users.substring(0, users.length-2);
	if (store === true)
  	document.getElementById("allowed_users").value = users;
  CloseModal("allowed_users_modal"); 
}

function AddAllowedUser(user) {
  if (user == "---")
    return;
  var table = document.getElementById("allowed_users_table");
  var row = table.insertRow();
  var cell = row.insertCell();
  var text = document.createTextNode(user);
  cell.appendChild(text);
  var cell_2 = row.insertCell();
  var button = document.createElement("input");
  button.type = "button";
  button.value = "remove";
  button.setAttribute("onclick", "RemoveAllowedUser(this.parentNode.parentNode);");
  cell_2.appendChild(button);
}

function RemoveAllowedUser(elem) {
  var table = document.getElementById("allowed_users_table");
  elem.parentNode.removeChild(elem);
}

async function ResetSubprotocols(protocol) {
  let reload = false;
  let formData = new FormData();
  formData.append("experiment", protocol);

  try {
    const response = await AppFetch("/animal_data/reset/", {method: "POST", body: formData});
    const message = await response.text();
    if (!response.ok) {
      OpenErrorModal(message || "Failed resetting subprotocol", response.status, 
        "protocol_changed_modal");
    } else {
      alert("resetted subprotocol for " + message + " animals")
      reload = true
    }
  } catch(error) {
    console.error("Failed resetting subprotocol:", error);
    OpenErrorModal();
  };
  if (reload) window.location.reload();
}

async function ReloadSubprotocols(protocol) {
  let formData = new FormData();
  formData.append("experiment", protocol);
  let reload = false;
  try {
    const response = await AppFetch("/animal_data/reload/", {method: "POST", body: formData});
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(message, response.status, "protocol_changed_modal");
    } else {
      const json = await response.json();
      if ("animal_data" in json && json["animal_data"].length > 2) {
        document.getElementById("animal_modal_text").textContent = json["text"];
        document.getElementById("animal_modal_text_2").style.display = "block";
        document.getElementById("animal_modal").style.height = "400px";
        document.getElementById("animal_modal").style.width = "70%";
        document.getElementById("animal_modal_table").innerHTML = json["animal_data"];
        OpenModel("animal_modal")
      } else {
        alert("Nothing to do: there has been no animal-data listed under this protocol.");
        window.location = window.location;
      }
    }
  } catch(error) {
    console.error("Failed saveing notes:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}
