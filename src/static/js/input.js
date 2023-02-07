window.onload = function() {
  // Get some values
  const date_string = document.getElementById("start").value
  const day = new Date(date_string).getDate();
  const start_date = new Date().getDate();
  const weights = JSON.parse(document.getElementById("weights").value);
  const watercontrol = JSON.parse(document.getElementById("watercontrol").value);
  const initial_weight = weights[0];

  // Create chart-data
  var data = [];
  var ds = { 
      yValueFormatString: "#.##g",
      type: "spline",
      lineColor: "#053769",
      lineThickness: 1,
      dataPoints: []
  };
  var dataPoints = [];
  for (var i=0; i<weights.length; i++) {
    // Increase date by one day
    const copiedDate = new Date(date_string);
    copiedDate.setDate(i+parseInt(day));
    // Set color according to watercontrol and exeeded bounds (+/- 10%)
    var color = "#053769";
    if ((initial_weight-weights[i])/initial_weight > 0.2)
      color = "Red";
    else if (watercontrol[i])
      color = "#992e32";
    // Add data-point
    dataPoints.push({x: copiedDate, y: weights[i], color: color});
  }
  ds.dataPoints = dataPoints;
  data.push(ds);

  // Create chart
  var chart = new CanvasJS.Chart("weight_graph", {
    zoomEnabled: true, 
    title: {
      padding: 10,
      text: "Weights and Watercontrol"
    },
    axisX:{
	    lineThickness: 0,
	    tickThickness: 0,
      margin: 15 
    },
    axisY: {
      includeZero: false,
      lineThickness: 0,
      gridThickness: 0,
      tickLength: 0,
      title: "weight",
      suffix: "g",
      margin: 10,
      stripLines: [
        { value: initial_weight, label: "initial weight"},
        { value: initial_weight-0.2*initial_weight, label: "lower"}
      ]
    },
    data: data,
  });
  chart.render();
}

function ToggleGraph() {
  var chart = document.getElementById("weight_graph");
  let hidden = chart.getAttribute("hidden");
  if (hidden)
    chart.removeAttribute("hidden");
  else 
    chart.setAttribute("hidden", "hidden");
}

async function UpdateDates(animal_id, autofill) {
  // Send request to server:
  try {
    let formData = new FormData();
    formData.append("date", document.getElementById("start").value);
    // Send request:
    let r = await fetch('/update/animal_data/dates/'+animal_id+"/"+autofill, 
      {method: "POST", body: formData}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    let response_text = await r.text()
    if (r.status === 200) {
      alert(response_text);
      window.location=window.location;
    }
    else if (r.status > 400 && r.status < 500) {
      alert("Error code: " + r.status + ": " + response_text);
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

async function GenerateWeightList(animal_id, weight) {
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/generate/weights/'+animal_id+"/"+weight, 
      {method: "POST", body: new FormData()}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200) {
      alert("Generated weight placeholders, fill in the proper weights as soon as they are messuered!")
      window.location=window.location;
    }
    else if (r.status > 400 && r.status < 500) {
      let response_text = await r.text()
      alert("Error code: " + r.status + ": " + response_text);
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

async function UpdateSuffering(animal_id, suffering) {
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/update/animal_data/suffering/'+animal_id+"/"+suffering, 
      {method: "POST", body: new FormData()}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200) {
      window.location=window.location;
    }
    else if (r.status > 400 && r.status < 500) {
      let response_text = await r.text()
      alert("Error code: " + r.status + ": " + response_text);
    }
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}


async function GenerateMainSheet(animal_id, type) {
  console.log("animal_id: ", animal_id);
  var req = new XMLHttpRequest();
  req.open("POST", "/generate/"+type+"/"+animal_id, true);
  req.responseType = "blob";
  req.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  req.onreadystatechange = function() {
    if (this.readyState == 4 && this.status == 200) {
      var blob = new Blob([this.response], {type: "application/docx"});
      var url = window.URL.createObjectURL(blob);
      var link = document.createElement('a');
      document.body.appendChild(link);
      link.style = "display: none";
      link.href = url;
      link.download = animal_id + "_" + type + ".docx";
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

function AddOrEdit(elem) {
  if (entry !== undefined) {
    for (var i=0; i<entry.children.length; i++) {
      if (entry.children[i].hasAttribute("name")) {
        var elem = document.getElementById(entry.children[i].getAttribute("name"));
        if (elem.type == "checkbox")
          elem.checked = entry.children[i].innerHTML === "True";
        else 
          elem.value=entry.children[i].innerHTML;
      }
    }
  }

  var dialog = document.getElementById("edit_modal"); 
}

async function Clear(animal_id) {
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/clear/'+animal_id, {method: "POST", body: new FormData()}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200)
      window.location=window.location;
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}


// Modal //

function OpenModalNotes(category, note) { 
  var dialog = document.getElementById("notes_modal"); 
  dialog.setAttribute("category", category);
  document.getElementById("notes_txt").value = unescape(note);
  // dailog.show(); 
  dialog.showModal();
} 

async function CloseModalNotes(animal_id, save) { 
  var save_notes_error = document.getElementById("save_notes_error");
  var dialog = document.getElementById("notes_modal"); 
  if (!save) {
    save_notes_error.innerHTML = "";
    dialog.close(); 
  }
  else {
    const category = dialog.getAttribute("category");
    let formData = new FormData();
    let txt = document.getElementById("notes_txt").value;
    formData.append("note", escape(txt)); 
    try {
      // Send request:
      let r = await fetch('/store/notes/'+animal_id+'/'+category, {method: "POST", body: formData}); 
      // Handle response:
      console.log('HTTP response code: ' + r.status); 
      if (r.status === 200) {
        window.location=window.location;
      }
      else if (r.status > 400 && r.status < 500) {
        let response_text = await r.text()
        save_notes_error.innerHTML = response_text;
      }
      else {
        save_notes_error.innerHTML = "Unkown error. Sorry";
      }
    } catch(e) {
      save_notes_error.innerHTML = "Unkown error. Sorry";
    }
  }
} 

function EditWeightList(category, note) { 
  // Fill weight-table
  const date_string = document.getElementById("start").value
  const day = new Date(date_string).getDate();
  const start_date = new Date().getDate();

  const weights = JSON.parse(document.getElementById("weights").value);
  const watercontrol = JSON.parse(document.getElementById("watercontrol").value);
  var tbl = document.getElementById("weights_table"); 
  var tbody = tbl.getElementsByTagName("tbody")[0];

  for (var i=0; i<weights.length; i++) {
    var row = document.createElement("tr");
    // date 
    var cell1 = document.createElement("td");
    const copiedDate = new Date(date_string);
    copiedDate.setDate(i+parseInt(day));
    cell1.innerHTML = copiedDate.toISOString().substring(0, 10);

    var cell2 = document.createElement("td");
    var inp = document.createElement("input");
    inp.setAttribute("type", "number");
    inp.step = 0.1;
    inp.value = weights[i].toFixed(2);
    if ((weights[0]-weights[i])/weights[0]> 0.2)
      inp.style.borderColor = "red";
    inp.onchange = CheckWeightLimit;
    inp.setAttribute("initial", weights[0]);
    cell2.appendChild(inp);

    var cell3 = document.createElement("td");
    var checkbox = document.createElement('input');
    checkbox.type = "checkbox";
    checkbox.checked = watercontrol[i];
    cell3.appendChild(checkbox);

    row.appendChild(cell1);
    row.appendChild(cell2);
    row.appendChild(cell3);
    tbody.appendChild(row);
  }

  // Show modal
  var dialog = document.getElementById("edit_weights_modal"); 
  dialog.showModal();
} 

function CheckWeightLimit() {
  const initial = this.getAttribute("initial")
  if (Math.abs(initial-this.value)/initial > 0.2)
    this.style.borderColor = "red";
  else 
    this.style.borderColor = "black";
}

async function CloseModalWeights(animal_id, save) {
  if (!save) {
    var dialog = document.getElementById("edit_weights_modal"); 
    dialog.close(); 
  }
  else {
    var tbl = document.getElementById("weights_table"); 
    var tbody = tbl.getElementsByTagName("tbody")[0];
    var weights = [];
    var watercontrol = [];
    for (var i=1; i< tbody.children.length; i++) {
      weights.push(tbody.children[i].children[1].getElementsByTagName("input")[0].valueAsNumber);
      watercontrol.push(tbody.children[i].children[2].getElementsByTagName("input")[0].checked);
    }
    let formData = new FormData();
    formData.append("weights", JSON.stringify(weights)); 
    formData.append("watercontrol", JSON.stringify(watercontrol)); 
    try {
      // Send request:
      let r = await fetch('/update/animal_data/weights/'+animal_id, {method: "POST", body: formData}); 
      // Handle response:
      console.log('HTTP response code: ' + r.status); 
      if (r.status === 200) {
        window.location=window.location;
      }
      else if (r.status > 400 && r.status < 500) {
        let response_text = await r.text()
        save_notes_error.innerHTML = response_text;
      }
      else {
        save_notes_error.innerHTML = "Unkown error. Sorry";
      }
    } catch(e) {
      save_notes_error.innerHTML = "Unkown error. Sorry";
    }
  }
}

function OpenUpdateDatesConfirmation(start_date) { 
  var dialog = document.getElementById("confirm_modal"); 
  document.getElementById("start").value = start_date;
  dialog.showModal();
} 

function CloseConfirmationModal(animal_id) { 
  var dialog = document.getElementById("confirm_modal"); 
  dialog.close();
}
