function Refresh() {
  window.location=window.location;
}

function CloseModal(modal_name) { 
  var dialog = document.getElementById(modal_name); 
  dialog.close(); 
}

function OpenModel(modal_name) {
  console.log("opening modal ", modal_name);
  var dialog = document.getElementById(modal_name); 
  dialog.showModal(); 
}

function OpenEditDeathModel(animal_id) {
  const action = document.getElementById('death_date_edit_form').action; //Will retrieve it
  document.getElementById('death_date_edit_form').action = action + "/" + animal_id;
  OpenModel("death_edit_modal");
}

function OpenErrorModal(msg, resp_status, previous) {
  if (previous !== undefined)
    CloseModal(previous);
  OpenModel("error_modal");
  if (resp_status === 500) {
    msg = "Sorry, this is probably our fault: " + msg;
  }
  document.getElementById("error_modal_msg").innerHTML = msg + " (status: " + resp_status + ")";
}

async function UpdateAll(td, force) {
  console.log(td);
  let entries = td.children;
  start = entries[3].children[0].value;
  end = entries[4].children[0].value;
  weight = entries[5].children[0].value;
  protocol = entries[7].children[0].value;
  subprotocol = entries[8].children[0].value;
  if (start == "")
    document.getElementById("animal_modal_text_3").innerHTML = "Missing start-date";
  else if (end == "")
    document.getElementById("animal_modal_text_3").innerHTML = "Missing end-date";
  else if (protocol == "---")
    document.getElementById("animal_modal_text_3").innerHTML = "Missing protocol";
  else if (subprotocol == "---")
    document.getElementById("animal_modal_text_3").innerHTML = "Missing sub-protocol";
  else {
    let formData = new FormData();
    // Add extracted data to form.
    formData.append("start", start);
    formData.append("end", end);
    formData.append("start_weight", weight);
    formData.append("protocol", protocol);
    formData.append("subprotocol", subprotocol);
    formData.append("animal_id", entries[0].innerHTML);
    // Send request to server:
    try {
      // Send request:
      let r = await fetch('/update/animal_data/all', {method: "POST", body: formData}); 
      // Handle response:
      let response_text = await r.text();
      document.getElementById("animal_modal_text_3").innerHTML = response_text + " " + r.status;
      if (r.status == 200) {
        td.classList.remove("not_stored");
        document.getElementById("animal_modal_text_3").innerHTML = "success";
      }
    } catch(e) {
      alert("Something went wrong: " + e);
    }
  }
}

function SelectAll(checked) {
  var checkboxes = document.getElementsByName("mark_animal");
  for (var i=0; i<checkboxes.length; i++)
    checkboxes[i].checked = checked;
}

function OpenDeleteAnimalModal(mla_num) {
  document.getElementById("animals_to_delete").innerHTML = mla_num;
	let delete_btn = document.getElementById("confirm_delete_animal_btn");
  delete_btn.style.display = "";
	delete_btn.setAttribute("onclick", "DeleteAnimalData('" + mla_num + "')");
	delete_btn.setAttribute("value", "delete " + mla_num);
	OpenModel("confirm_delete_animal_modal");
}

function OpenDeleteAllAnimalsModal() {
  // Get all selected animals
  var checkboxes = document.getElementsByName("mark_animal");
  var mlas = [];
  for (var i=0; i<checkboxes.length; i++) {
    if (checkboxes[i].checked)
      mlas.push(checkboxes[i].getAttribute("animal_id"));
  }
  console.log("Got mlas to delete: ", mlas);

  // Open delete animal modal
  let delete_btn = document.getElementById("confirm_delete_animal_btn");
  if (mlas.length > 0) {
    document.getElementById("animals_to_delete").innerHTML = mlas.join(", ");
    delete_btn.style.display = "";
    delete_btn.setAttribute("onclick", "DeleteAnimalData('" + mlas.join(",") + "')");
    delete_btn.setAttribute("value", "delete all selected animals");
  }
  else {
    delete_btn.style.display = "none";
    document.getElementById("animals_to_delete").innerHTML = "No animals selected!";
  }
  OpenModel("confirm_delete_animal_modal");
}

function UpdateReportingYear(year) {
  console.log("New reporting year: ", year)
  var url = new URL(window.location.href);
  url.searchParams.set('reporting_year', year);
  console.log("New url: ", url)
  window.location = url.href;
}


