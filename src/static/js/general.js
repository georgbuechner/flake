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
