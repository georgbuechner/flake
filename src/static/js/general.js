async function UploadPyratData(user) 
{
  let user_infos = { "name": user.replace(" ", "-").toLowerCase()};
  let pyrat_csv = document.getElementById("pyrat_csv").files[0];
  console.log(pyrat_csv);
  let formData = new FormData();

  formData.append("csv", pyrat_csv);
  formData.append("user", JSON.stringify(user_infos));
  
  const ctrl = new AbortController();    // timeout
  setTimeout(() => ctrl.abort(), 5000);
  
  // Send request to server.
  try {
    // Send request:
    let r = await fetch('/upload/pyrat_csv', 
     {method: "POST", body: formData, signal: ctrl.signal}); 
    // Handle response:
    console.log('HTTP response code: ' + r.status); 
    if (r.status === 200)
      window.location=window.location;
    if (r.status === 409)
      alert("Animal with this id already exists!");
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}

function UpdateDates(date_string, surgery_start) {
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
  // TODO (activate this again!): alert("All dates have been auto filled based on protocol-specific information. You should double-check!");
}

function GenerateP9(protocol) {
  alert("Funcionality not yet implemented. Sorry :(");
}

function GenerateScoreSheet(animal_id) {
  alert("Funcionality not yet implemented. Sorry :(");
}

async function GenerateSurgerySheet(protocol, animal_id) {
  console.log("protocol: ", protocol, "animal_id: ", animal_id);
  var req = new XMLHttpRequest();
  req.open("POST", "/generate/surgery_sheet/"+protocol+"/"+animal_id, true);
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
      link.download = "surgery_sheet.docx";
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
  let data = {"anesthetic":[], "analgesic":[], "procedures":[], "post_procedures":[]};
  let general_entry = new Object();
  for (const id of ["start", "end", "experiment", "start_weight"]) {
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
            if (input.hasAttribute("convert") && input.getAttribute("convert") === "int")
              entry[input.id] = parseInt(input.value);
            else if (input.hasAttribute("convert") && input.getAttribute("convert") === "bool")
              entry[input.id] = (input.value === "yes") ? true : false;
            else 
              entry[input.id] = input.value;
          }
        }  
        // If avoid empty lines, check if data was added to entry, then add:
        if (Object.keys(entry).length > 0)
          data[key].push(entry);
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
    else
      alert("Something went wrong: Error code: " + r.status);
  } catch(e) {
    alert("Something went wrong: " + e);
  }
}
