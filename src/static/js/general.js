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
  var req = new XMLHttpRequest();
  req.open("POST", "/generate/paragraph9/"+protocol, true);
  req.responseType = "blob";
  req.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  req.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      var blob = new Blob([this.response], {"type": "application/pdf"});
      var url = window.URL.createObjectURL(blob);
      var link = document.createElement('a');
      document.body.appendChild(link);
      link.style = "display: none";
      link.href = url;
      link.download = "paragraph9.pdf";
      link.click();

      setTimeout(() => {
      window.URL.revokeObjectURL(url);
      link.remove(); } , 100);
    }
    else if (this.readyState === 4 && this.status >= 400 ) {
      var blob = new Blob([this.response], {type: "text"});
      var reader = new FileReader();
      reader.onload = function() {
        alert(reader.result);
      }
      reader.readAsText(blob);
    }
  };
  req.send();
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

function Refresh() {
  window.location=window.location;
}

function CloseModal(modal_name) { 
  var dialog = document.getElementById(modal_name); 
  dialog.close(); 
}

function OpenModel(modal_name) {
  var dialog = document.getElementById(modal_name); 
  dialog.showModal(); 
}
