async function UploadPyratData() 
{
  const elem = document.getElementById("pyrat_csv");
  if (elem.files.length == 0) {
    alert("No file selected!");
    return;
  }
  let pyrat_csv = elem.files[0];
  console.log(pyrat_csv);
  let formData = new FormData();

  formData.append("csv", pyrat_csv);
  
  const ctrl = new AbortController();    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  // Send request to server.
  try {
    // Send request:
    let r = await fetch('/upload/pyrat_csv', 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.ok) {
      if (r.status === 206) {
        let response_text = await r.text()
        alert(response_text);
      }
      window.location=window.location;
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

function GenerateP9(protocol) {
  alert("Funcionality not yet implemented. Sorry :(");
}

async function UpdateSubprotocol(subprotocol, animal_id, force) {
  console.log(subprotocol, animal_id, force);
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
    if (r.status === 409) {
      let response_text = await r.text()
      var dialog = document.getElementById("confirm_modal"); 
      document.getElementById("set_subprotocol_msg").innerHTML = response_text; 
      document.getElementById("set_subprotocol_btn").setAttribute("onclick", 
        "UpdateSubprotocol('"+subprotocol+"', '"+animal_id+"', true)");
      dialog.showModal(); 
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

function NotResponsible() {
  alert("You're not responsible for this animal!")
  return false;
}

function CloseModal() { 
  var dialog = document.getElementById("confirm_modal"); 
  document.getElementById("set_subprotocol_msg").innerHTML = ""; 
  dialog.close(); 
}
