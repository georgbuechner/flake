window.onload = function() {
  // Get some values

  if (document.getElementById("weights") === null)
    return;
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
  // get form data 
  const dialog_name = "confirm_modal";
  const form = document.getElementById("start_date_form");
  const dialog = document.getElementById(dialog_name);
  // Send request:
  let reload = false;
  try {
    const response = await AppFetch(
      '/update/animal_data/dates/' + animal_id + "/" + autofill,
      {method: "POST", body: new FormData(form)}
    );
    const message = await response.text();

    if (!response.ok) {
      OpenErrorModal(
        message || "The dates could not be updated",
        response.status, 
        dialog_name
      );
      return;
    }
    if (dialog.open) dialog.close();
    alert(message || "Dates updated");
    reload = true;
  } catch (error) {
    console.error("Updating dates failed:", error); 
    OpenErrorModal();
  }

  if (reload) window.location.reload()
}

async function GenerateWeightList(animal_id, weight) {
  let reload = false;
  // Send request:
  try {
    let response = await AppFetch(
      '/generate/weights/' + animal_id + "/" + weight, 
      {method: "POST"}
    );

    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(
        message || "Weights could not be generated", response.status
      );
      return;
    } else {
      alert("Generated weight placeholders, fill in the proper weights as soon as they are measured!");
      reload = true;
    }
  } catch (error) {
    console.error("Generating weights failed:", error); 
    OpenErrorModal();
  };
  if (reload) window.location.reload();
}

async function UpdateSuffering(animal_id, suffering) {
  let reload = false;
  // Send request to server:
  try {
    // Send request:
    let response = await AppFetch(
      '/update/animal_data/suffering/' + animal_id + "/" + suffering, 
      {method: "POST", body: new FormData()}
    ); 
    if (!response.ok) {
      const message = await response.text(); 
      OpenErrorModal(message || "Failed updating suffering.", response.status);
      return;
    } else {
      reload = true;
    }
  } catch(error) {
    console.error("Updating suffering failed:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

async function UpdateProgress(id) {
  try {
    const response = await AppFetch("/generate/progress/" + id);
    // A job may not have started yet, or may have just finished.
    if (response.status === 404) return true;
    if (!response.ok) {
      OpenErrorModal(await response.text(), response.status);
      return false;
    }
    const data = await response.json();
    const progress = document.getElementById("progress_bar");
    progress.setAttribute("max", Number(data.total));
    progress.setAttribute("value", Number(data.cur));
    return true;
  } catch (error) {
    console.error("Failed retrieving document progress:", error);
    OpenErrorModal("Progress could not be retrieved. The document may still be generating.");
    return false;
  }
}

async function GenerateMainSheet(animal_id, type) {
  const progress = document.getElementById("progress_container");
  progress.style.display = "block";
  const id = type + "/" + animal_id;
  const interval = setInterval(async () => {
    if (!await UpdateProgress(id.replace("/", "_"))) clearInterval(interval);
  }, 2500);
  let downloadUrl;
  let link;
  try {
    const response = await AppFetch("/generate/" + id);
    if (!response.ok) {
      OpenErrorModal(await response.text(), response.status);
      return;
    }
    const filtered = response.headers.get("Filtered-Procedures-JSON");
    if (filtered) {
      const filtered_procedures = JSON.parse(filtered);
      if (filtered_procedures.length > 0) {
        let msg = "The following procedures where removed since they took place after the "
            + "sacrifice of the animal: \n";
        filtered_procedures.forEach(p => {
          msg += "- " + p.name + ": " + p.start_date + " - " + p.end_date + "\n";
        });
        alert(msg);
      }
    }
    downloadUrl = URL.createObjectURL(await response.blob());
    link = document.createElement("a");
    link.href = downloadUrl;
    link.download = animal_id + "_" + type + ".docx";
    document.body.appendChild(link);
    link.click();
  } catch (error) {
    console.error("Failed downloading document:", error);
    OpenErrorModal("The document could not be downloaded. Please try again.");
  } finally {
    clearInterval(interval);
    progress.style.display = "none";
    if (downloadUrl) {
      setTimeout(() => {
        URL.revokeObjectURL(downloadUrl);
        link?.remove();
      }, 100);
    }
  }
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
  let reload = false;
  // Send request to server:
  try {
    // Send request:
    let response = await AppFetch(
      '/clear/' + encodeURIComponent(animal_id), 
      {method: "POST", body: new FormData()}
    ); 
    // Handle response:
    console.log('HTTP response code: ' + response.status); 
    if (!response.ok) {
      const message = await response.text();
      OpenErrorModal(
        message || "Failed clearing animal data for " + animal_id, 
        response.status
      );
    } else {
      reload = true;
    }
  } catch(error) {
    console.error("Failed clearing animal data:", error);
    OpenErrorModal();
  }

  if (reload) window.location.reload();
}


// Modal //

function OpenModalNotes(category, note, apply_note) { 
  console.log("OpenModalNotes: ", apply_note, apply_note === "True");
  var dialog = document.getElementById("notes_modal"); 
  dialog.setAttribute("category", category);
  document.getElementById("notes_txt").value = decodeURI(note);
  document.getElementById("notes_apply").checked = (apply_note === "True");
  // dailog.show(); 
  dialog.showModal();
} 

async function CloseModalNotes(animal_id, save) { 
  var dialog = document.getElementById("notes_modal"); 
  if (!save) {
    dialog.close(); 
    return;
  }

  const category = dialog.getAttribute("category");
  let formData = new FormData();
  let txt = document.getElementById("notes_txt").value;
  formData.append("note", encodeURI(txt)); 
  formData.append("apply_note", document.getElementById("notes_apply").checked); 
  let reload = false;
  try {
    // Send request:
    let response = await AppFetch('/store/notes/'+animal_id+'/'+category, {method: "POST", body: formData});
    // Handle response:
    console.log('HTTP response code: ' + response.status); 
    if (!response.ok) {
      let message = await response.text()
      OpenErrorModal(message || "Failed saving notes", response.status);
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

function EditWeightList(category, note) { 
  // Fill weight-table
  const date_string = document.getElementById("start").value + " 04:00:00";
  const day = new Date(date_string).getDate();

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
    inp.value = (weights[i] !== null) ? weights[i].toFixed(2) : 0;
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
    return;
  }
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
  let reload = false;
  try {
    // Send request:
    let r = await AppFetch('/update/animal_data/weights/'+animal_id, {method: "POST", body: formData});
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (!r.ok) {
      let message = await r.text();
      OpenErrorModal(message || "Failed updating weights", r.status);
    } else {
      reload = true;
    }
  } catch(error) {
    console.error("Error updating animal weights:", error);
    OpenErrorModal();
  }
  if (reload) window.location.reload();
}

function FillProcedure(name, procedures) {
  const procedure = procedures.find(x => x.name == name);
  const dialog = document.getElementById("edit_modal");
  dialog.querySelector("#protocol_entry_uuid").value = procedure.uuid;
}

function RemoveDateSuggest(elem, durations) {
  elem.classList.remove("date_suggest");
  if (durations !== undefined) {
    try {
      const dialog = document.getElementById("edit_modal");
      const puuid = dialog.querySelector("#protocol_entry_uuid").value;
      console.log("Found puuid: ", puuid);
      let end_date = dialog.querySelector("#end_date");
      let copiedDate = new Date(elem.value);
      const day = new Date(elem.value).getDate();
      copiedDate.setDate(parseInt(day) + parseInt(durations[puuid])-1);
      end_date.value = copiedDate.toISOString().substring(0, 10);
      end_date.classList.remove("date_suggest");
    } 
    catch(e) {
      console.log("Could not set end-date: ", e)
    }
  }
}
