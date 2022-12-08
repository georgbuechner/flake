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

function UpdateDates(date_string, surgery_start) {
  console.log("UpdateDates: surgery_start:", surgery_start);
  // Get all elements with `start_plus` (days to add/ days after surgery) attribute:
  var arr = document.querySelectorAll("[start_plus]");
  // Get current day and add surgery-start
  const day = new Date(date_string).getDate() + parseInt(surgery_start);
  // Iterate over all elements with `start_plus` attribute and modify date
  // accordings to start_plus 
  max_date = 0;
  for (var i = 0; i < arr.length; i++) {
    // Create copy and increment days by `start_plus` value of elemenyt
    const copiedDate = new Date(date_string);
    const start_plus = parseInt(arr[i].getAttribute("start_plus"));
    copiedDate.setDate(start_plus+parseInt(day));
    // Set date-value
    arr[i].setAttribute("value", copiedDate.toISOString().substring(0, 10));
    // Check if new date might by new max-date
    if (copiedDate.getTime() > max_date)
      max_date = copiedDate.getTime()
  }
  // Set end-date
  const endDate = new Date(max_date);
  let end_date_elem = document.getElementById("end");
  end_date_elem.setAttribute("value", endDate.toISOString().substring(0, 10));
  // Send message to user to double check all entries.
  alert("All dates have been auto filled based on protocol-specific information. You should double-check!");
}

async function GenerateWeightList(animal_id) {
  // Send request to server:
  try {
    // Send request:
    let r = await fetch('/generate/weights/'+animal_id, {method: "POST", body: new FormData()}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200)
      window.location=window.location;
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
  req.onreadystatechange = function(){
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
    else if (this.readyState ===4) {
      alert("Something went wrong. Status: " + this.status);
    }
  };
  req.send();
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

function Del(row, table) {
  console.log(row);
  console.log(table.children.length);
  // last element (apart from th), simply clear element:
  if (table.children.length < 3) {
    reset_row(row)
  }
  // Otherwise: remove element:
  else {
    row.parentNode.removeChild(row);
  }
}

function Add(row) {
  let new_row = row.cloneNode(true);
  reset_row(new_row);
  row.after(new_row);
}

function reset_row(row) {
  for (var i=0; i<row.children.length; i++) {
    reset_input(row.children[i].children[0]);
  }
}

function reset_input(elem) {
  if (elem.nodeName === "SELECT") {
    elem.options[0].selected = true;
  }
  else if (elem.nodeName === "INPUT") {
    elem.value = "";
  }
}

// Modal //

function openModal(category, note) { 
  var dialog = document.getElementById("notes"); 
  dialog.setAttribute("category", category);
  document.getElementById("notes_txt").value = unescape(note);
  // dailog.show(); 
  dialog.showModal();
} 

async function closeModal(animal_id, save) { 
  var save_notes_error = document.getElementById("save_notes_error");
  var dialog = document.getElementById("notes"); 
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

