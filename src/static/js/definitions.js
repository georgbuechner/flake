function Add(entry) { 
  console.log(entry);
  if (entry !== undefined) {
    for (var i=0; i<entry.children.length; i++) {
      if (entry.children[i].hasAttribute("name")) {
        const cur_name = entry.children[i].getAttribute("name");
        var elem = document.getElementById(cur_name);
        if (elem.type == "checkbox") {
          elem.checked = entry.children[i].innerHTML === "True" || entry.children[i].innerHTML === "yes";
          if (entry.children[i].innerHTML === "True" && cur_name === "weight_independant")
            BlockDosis();
          else if (cur_name == "weight_independant")
            BlockAmount();
        }
        else if (entry.children[i].getAttribute("name").indexOf("date") !== -1 
          && entry.children[i].innerHTML == "---" 
          && document.getElementById("start") !== undefined) {
          elem.value=document.getElementById("start").value;
          elem.classList.add("date_suggest");
        }
        else 
          elem.value=entry.children[i].innerHTML;
      }
    }
  }
  // open add-/edit-modal
  var dialog = document.getElementById("edit_modal"); 
  dialog.showModal();
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

function RemoveDateSuggest(elem) {
    elem.classList.remove("date_suggest");
}

async function DelProtocolEntry(category, uuid) {
  console.log(category, uuid);
  try {
    // Send request:
    let r = await fetch("/settings/protocols/delete/"+category+"/"+uuid, 
      {method: "POST", body: new FormData}); 
    // Handle response:
    if (r.status === 200)
      window.location=window.location;
    else 
      alert("Unkown error. Sorry " + r.status);
  } catch(e) {
    console.log(e);
    alert("Unkown error. Sorry", e);
  }
}
async function DelADEntry(animal_id, category, uuid) {
  console.log(category, uuid);
  try {
    // Send request:
    let r = await fetch("/animal_data/"+animal_id+"/delete/"+category+"/"+uuid, 
      {method: "POST", body: new FormData}); 
    // Handle response:
    if (r.status === 200)
      window.location=window.location;
    else 
      alert("Unkown error. Sorry " + r.status);
  } catch(e) {
    console.log(e);
    alert("Unkown error. Sorry", e);
  }
}


async function Del(category, name, type, identifier, protocol) {
  const escaped_name = escape(name).replace("/", "_");
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
  try {
    // Send request:
    let r = await fetch(base_url+"/delete/"+category+"/"+escaped_name+protocol, {
      method: "POST", body: new FormData}); 
    // Handle response:
    if (r.status === 200)
      window.location=window.location;
    else 
      alert("Unkown error. Sorry " + r.status);
  } catch(e) {
    console.log(e);
    alert("Unkown error. Sorry", e);
  }
}

function Restricted() {
    alert("This action is restricted to admin-users!")
}

function CloseModal() { 
  var dialog = document.getElementById("edit_modal"); 
  dialog.close(); 
}

function Set(elem, availible) {
  console.log("all availible entries: ", availible)
  const getByKey = (arr, key) => (arr.find(x => x["name"] === key) || {});
  const definition = getByKey(availible, elem.value);
  for (const [key, value] of Object.entries(definition)) {
    let el = document.getElementById(key)
    if (el !== undefined && el !== null) {
      if ((el || {}).type === "checkbox" && value === true)
        el.checked = true;
      else if ((el || {}).type === "checkbox" && value === false)
        el.checked = false;
      else 
        el.value = value; 
    }
  }
}

function OpenAllowedUsers() {
  var users = document.getElementById("allowed_users").value;
  users.split(", ").forEach(function(user) {
    AddAllowedUser(user); 
  });
  var dialog = document.getElementById("allowed_users_modal"); 
  dialog.showModal(); 
}

function CloseAllowedUsers() {
  var table = document.getElementById("allowed_users_table");
  var users = "";
  while(table.rows.length > 1) {
    users += table.rows[1].cells[0].innerHTML + ", ";
    table.deleteRow(1);
  }
  if (users.length >=2) 
    users = users.substring(0, users.length-2);
  document.getElementById("allowed_users").value = users;
  var dialog = document.getElementById("allowed_users_modal"); 
  dialog.close(); 
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
