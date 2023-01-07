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
    if (Math.abs(initial_weight-weights[i])/initial_weight > 0.2)
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
        { value: initial_weight+0.2*initial_weight, label: "upper"},
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

async function UpdateDates(animal_id, date_str) {
  // Send request to server:
  try {
    let formData = new FormData();
    formData.append("date", document.getElementById("start").value);
    // Send request:
    let r = await fetch('/update/animal_data/dates/'+animal_id, {method: "POST", body: formData}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    let response_text = await r.text()
    if (r.status === 200) {
      alert("Dates have been auto filled based on protocol-specific information. You should double-check! "
        + response_text);
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
      link.download = type + ".docx";
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
      // var text = reader.readAsText(blob);
      // alert(blob.stream() + ": " + this.status);
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
async function Store(animal_id) {
  // Create new form:
  let formData = new FormData();

  // Create data with all elements to extract from html.
  let data = {"anesthetic":[], "analgesic":[], "procedures":[], "post_procedures":[], "viruses":[]};
  let general_entry = new Object();
  for (const id of ["start", "end", "experiment", "start_weight", "watercontrol", "weights"]) {
    console.log("ID: ", id);
    general_entry[id] = document.getElementById(id).value;
  }
  data["general"] = [general_entry];
  for (const key in data) {
    // Get table from html DOM
    const table = document.getElementById(key);
    // Check if table was found
    if (table !== undefined && table != null) {
      // Iterate over all rows
      for (var i = 0, row; row = table.rows[i]; i++) {
        // Iterate over all colums and add to new entry
        let entry = new Object();
        for (var j = 0, col; col = row.cells[j]; j++) {
          // If has children (not th), add new entry:
          if (col.children.length > 0) {
            const input = col.children[0];
            if (input.value === "") {
              input.style.borderColor = "red";
              return;
            }
            if (input.hasAttribute("type") && input.getAttribute("type") === "date") {
              const date = new Date(input.value);
              entry[input.id] = date.toISOString().substring(0, 10);
            }
            else if (input.hasAttribute("convert") && input.getAttribute("convert") === "int")
              entry[input.id] = parseInt(input.value);
            else if (input.hasAttribute("convert") && input.getAttribute("convert") === "bool")
              entry[input.id] = (input.value === "yes") ? true : false;
            else 
              entry[input.id] = input.value;
          }
        }  
        // If avoid empty lines, check if data was added to entry, then add:
        if (Object.keys(entry).length > 0) {
          data[key].push(entry);
        }
      }
    }
  }
  // Add extracted data to form.
  formData.append("data", JSON.stringify(data));
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/store/'+animal_id, {method: "POST", body: formData}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200)
      window.location=window.location;
    else if (r.status >=400 && r.status < 500) {
      let response_text = await r.text()
      alert(r.status + ": " + response_text);
    }
    else {
      alert("Something went wrong: Error code: " + r.status);
    }
  } catch(e) {
    alert("Something went wrong: " + e);
  }
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
    if (Math.abs(weights[0]-weights[i])/weights[0]> 0.2)
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

function OpenUpdateDatesConfirmation(animal_id) { 
  var dialog = document.getElementById("confirm_modal"); 
  dialog.showModal();
} 

function CloseConfirmationModal(animal_id) { 
  var dialog = document.getElementById("confirm_modal"); 
  dialog.close();
}
