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
      let json = await r.json()
      if (r.status != 200) {
        OpenErrorModal(json["text"], r.status, "upload_modal");
      }
      if (json["animal_data"].length > 2) {
        document.getElementById("animal_modal_text").innerHTML = json["text"];
        document.getElementById("animal_modal_text_2").style.display = "block";
        document.getElementById("animal_modal").style.height = "400px";
        document.getElementById("animal_modal").style.width = "70%";
        document.getElementById("animal_modal_table").innerHTML = json["animal_data"];
        OpenModel("animal_modal")
      }
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
      link.download = protocol + "_paragraph-9.pdf";
      link.click();
      setTimeout(() => {
        window.URL.revokeObjectURL(url);
        link.remove(); 
      } , 100);
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

async function UpdateAll(subprotocol, td, force) {
  console.log(td);
  let entries = td.children;
  let formData = new FormData();
  // Add extracted data to form.
  formData.append("start", entries[2].children[0].value);
  formData.append("end", entries[3].children[0].value);
  formData.append("protocol", entries[5].children[0].value);
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

async function UpdateProtocol(protocol, animal_id, force) {
  console.log(subprotocol, animal_id, force);
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
    if (r.status === 409) {
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
      var selectElement = entries[6].children[0];
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
